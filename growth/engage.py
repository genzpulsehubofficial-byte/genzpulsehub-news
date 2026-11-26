"""Auto-replies on Instagram + Facebook comments (runs from GitHub Actions every 30 min; free AI only).

For each new comment on our recent posts:
  question/opinion about the news -> short, friendly, neutral reply (same language)
  praise                           -> thanks + "follow for daily news"
  ad / promotion / collab enquiry  -> price + booking link
  spam, abuse, hate, scam links    -> hidden
  anything risky (medical/legal/money advice, private people, politics fights) -> no reply
State in data/replied.json so nothing is answered twice.
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shorts"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import requests  # noqa: E402
from publish import G, IG_IDS, SITE, discord, env, meta_pages, yt_token  # noqa: E402
from ai import ask  # noqa: E402

STATE_P = os.path.join(ROOT, "data", "replied.json")
MAX_PER_RUN = 40
PROMPT = """You manage comments for "GenZ Pulse Hub", a neutral news page for Indian Gen Z and teens.
Classify each comment and write a reply when useful. Rules: be short (max 25 words), friendly, Gen Z tone,
same language as the comment (Malayalam if Malayalam), neutral on politics, never argue, never give medical,
legal or financial advice, never share private info, no promises. If unsure, choose "skip".
Ad/promo/collab enquiry -> reply with: ads start at ₹199 (website banner), book at {ads}.
Praise -> thank them and invite them to follow for daily news.

Return ONLY JSON list: [{{"id": "...", "action": "reply"|"hide"|"skip", "reply": "..."}}]
Use "hide" only for spam, scam links, abuse, hate or sexual content.

COMMENTS:
{comments}
"""


def load():
    try:
        return json.load(open(STATE_P))
    except Exception:
        return {"done": {}}


def get(path, **params):
    try:
        return requests.get(f"{G}/{path}", params=params, timeout=30).json()
    except Exception as e:
        return {"error": str(e)}


def post(path, **data):
    try:
        return requests.post(f"{G}/{path}", data=data, timeout=30).json()
    except Exception as e:
        return {"error": str(e)}


def collect(state):
    """Return list of new comments: {id, text, lang, kind ('ig'|'fb'), token, page_name}."""
    out = []
    tok = env("META_TOKEN")
    pages = meta_pages()
    for lang, p in pages.items():
        ptok = p["access_token"]
        # Instagram
        ig = (p.get("instagram_business_account") or {}).get("id") or IG_IDS.get(lang)
        if ig:
            media = get(f"{ig}/media", fields="id,comments_count,timestamp", limit=25, access_token=p.get("ig_token") or tok)
            for m in media.get("data", []):
                if not m.get("comments_count"):
                    continue
                cs = get(f"{m['id']}/comments", fields="id,text,username,timestamp", limit=50,
                         access_token=p.get("ig_token") or tok)
                for c in cs.get("data", []):
                    if c["id"] in state["done"] or c.get("username", "").lower().startswith("genzpulsehub"):
                        continue
                    out.append({"id": c["id"], "text": c.get("text", ""), "lang": lang, "kind": "ig",
                                "token": p.get("ig_token") or tok})
        # Facebook (page posts incl. reels)
        feed = get(f"{p['id']}/posts", fields="id,comments.limit(50){id,message,from}", limit=25, access_token=ptok)
        for f in feed.get("data", []):
            for c in (f.get("comments") or {}).get("data", []):
                if c["id"] in state["done"] or (c.get("from") or {}).get("id") == p["id"]:
                    continue
                out.append({"id": c["id"], "text": c.get("message", ""), "lang": lang, "kind": "fb", "token": ptok})
    # YouTube (needs the youtube.force-ssl permission on the refresh token)
    YT = "https://www.googleapis.com/youtube/v3"
    for lang, ch in (("en", "UCrpJDlRnVJyC4EguHKJxHKg"), ("ml", "UC3dW_vEz432vsb6uqlCVHAw")):
        t = yt_token(lang)
        if not t:
            continue
        r = requests.get(f"{YT}/commentThreads", params={"part": "snippet", "allThreadsRelatedToChannelId": ch,
                         "maxResults": 50, "order": "time"}, headers={"Authorization": f"Bearer {t}"}, timeout=30).json()
        if "error" in r:
            print("youtube comments:", str(r["error"].get("message"))[:120]); continue
        for th in r.get("items", []):
            top = th["snippet"]["topLevelComment"]
            sn = top["snippet"]
            if top["id"] in state["done"] or th["snippet"].get("totalReplyCount", 0) > 0 \
                    or sn.get("authorChannelId", {}).get("value") == ch:
                continue
            out.append({"id": top["id"], "text": sn.get("textOriginal", ""), "lang": lang, "kind": "yt", "token": t})
    return out


def yt_act(c, act, text=""):
    YT = "https://www.googleapis.com/youtube/v3"
    h = {"Authorization": f"Bearer {c['token']}"}
    if act == "reply":
        r = requests.post(f"{YT}/comments?part=snippet", headers=h, timeout=30,
                          json={"snippet": {"parentId": c["id"], "textOriginal": text[:300]}}).json()
        return "id" in r
    r = requests.post(f"{YT}/comments/setModerationStatus", headers=h, timeout=30,
                      params={"id": c["id"], "moderationStatus": "heldForReview"})
    return r.status_code == 204


def main():
    if not env("META_TOKEN"):
        print("no META_TOKEN"); return
    state = load()
    new = collect(state)[:MAX_PER_RUN]
    print("new comments:", len(new))
    if not new:
        return
    by_id = {c["id"]: c for c in new}
    stats = {"reply": 0, "hide": 0, "skip": 0}
    for i in range(0, len(new), 15):
        batch = new[i:i + 15]
        txt = json.dumps([{"id": c["id"], "comment": c["text"][:400]} for c in batch], ensure_ascii=False)
        try:
            raw, _ = ask(PROMPT.format(ads=SITE["en"] + "/advertise/", comments=txt))
            raw = raw[raw.find("["): raw.rfind("]") + 1]
            decisions = json.loads(raw)
        except Exception as e:
            print("ai failed:", str(e)[:120]); continue
        for d in decisions:
            c = by_id.get(str(d.get("id")))
            if not c:
                continue
            act = d.get("action", "skip")
            if c["kind"] == "yt" and act in ("reply", "hide"):
                if act == "reply" and not d.get("reply"):
                    continue
                if not yt_act(c, act, d.get("reply", "")):
                    print("youtube action failed"); continue
            elif act == "reply" and d.get("reply"):
                r = post(f"{c['id']}/replies" if c["kind"] == "ig" else f"{c['id']}/comments",
                         message=d["reply"][:300], access_token=c["token"])
                if "id" not in r:
                    print("reply failed", str(r)[:150]); continue
            elif act == "hide":
                r = post(c["id"], hide="true" if c["kind"] == "ig" else "", is_hidden="true", access_token=c["token"])
            stats[act] = stats.get(act, 0) + 1
            state["done"][c["id"]] = int(time.time())
            time.sleep(1.5)
    # forget entries older than 30 days
    cut = time.time() - 30 * 86400
    state["done"] = {k: v for k, v in state["done"].items() if v > cut}
    json.dump(state, open(STATE_P, "w"))
    print("done:", stats)


if __name__ == "__main__":
    main()
