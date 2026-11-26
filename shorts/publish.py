"""Publish rendered Shorts/Reels: YouTube Shorts, Instagram Reels, Facebook Reels — each language to its own accounts.
Skips any platform whose credentials are not set yet (logs it). Records results in data/posted.json.
"""
import json
import os
import subprocess
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "out", "shorts")
G = "https://graph.facebook.com/v21.0"
PAGES = {"en": "61596319547043", "ml": "61596419862358"}     # profile ids; real page ids resolved via token
BIZ = "932757405756172"
IG_IDS = {"en": "17841409013887055", "ml": "17841440794138461"}  # fallback ids from Business Settings
IG_USERS = {"en": "genzpulsehubnews", "ml": "genzpulsehubmalayalam"}
PAGE_NAMES = {"en": "GenZ Pulse Hub", "ml": "GenZ Pulse Hub Malayalam"}
def _base():
    """Use the custom domain automatically once it is live; otherwise the always-working pages.dev."""
    try:
        if requests.get("https://genzpulsehub.dpdns.org/", timeout=10).status_code == 200:
            return "https://genzpulsehub.dpdns.org"
    except Exception:
        pass
    return "https://genzpulsehub.pages.dev"


_B = _base()
SITE = {"en": _B, "ml": _B + "/ml"}
YT_LIVE = {"en": "https://youtube.com/@genzpulsehubnews", "ml": "https://youtube.com/@genzpulsehubmalayalam"}
MEDIA_BASE = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")


def env(k):
    return os.environ.get(k, "").strip()


def discord(msg):
    if env("DISCORD_WEBHOOK_URL"):
        requests.post(env("DISCORD_WEBHOOK_URL"), timeout=15, json={"content": ("@everyone " + msg)[:1900],
                      "username": "GenZ Pulse Hub", "allowed_mentions": {"parse": ["everyone"]}})


def caption(lang, s, platform):
    tags = " ".join("#" + t.replace(" ", "") for t in (s.get("tags") or [])[:5])
    base = f"{s['headline']}\n\n{s['hook']}\n\n"
    if lang == "en":
        cta = f"Full story 👉 {SITE[lang]}/news/{s['id']}/\nMore news daily 👉 {YT_LIVE[lang]}"
        tags += " #GenZ #IndiaNews #GenZPulseHub"
    else:
        cta = f"മുഴുവൻ വാർത്ത 👉 {SITE[lang]}/news/{s['id']}/\nകൂടുതൽ വാർത്തകൾ 👉 {YT_LIVE[lang]}"
        tags += " #MalayalamNews #KeralaNews #GenZPulseHub"
    if platform == "ig":
        cta = "Full story: link in bio 🔗" if lang == "en" else "മുഴുവൻ വാർത്ത: ബയോയിലെ ലിങ്ക് 🔗"
    return f"{base}{cta}\n\nSource: {s['source']}\n{tags}"[:2150]


# ---------------- YouTube ----------------
def yt_token(lang):
    cid, sec, ref = env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET"), env(f"YT_REFRESH_{lang.upper()}")
    if not (cid and sec and ref):
        return None
    r = requests.post("https://oauth2.googleapis.com/token", data={"client_id": cid.strip(), "client_secret": sec.strip(),
                      "refresh_token": ref.strip(), "grant_type": "refresh_token"}, timeout=30)
    if not r.ok:
        try: err = r.json()
        except Exception: err = {}
        shape = f"id={len(cid.strip())}ch/{'ok' if cid.strip().endswith('.apps.googleusercontent.com') else 'bad'} " \
                f"secret={len(sec.strip())}ch/{'ok' if sec.strip().startswith('GOCSPX') else 'bad'} " \
                f"refresh={len(ref.strip())}ch/{'ok' if ref.strip().startswith('1//') else 'bad'}"
        raise RuntimeError(f"token {r.status_code} {err.get('error')}: {err.get('error_description')} [{shape}]")
    return r.json()["access_token"]


def youtube(lang, s, path):
    tok = yt_token(lang)
    if not tok:
        return "skipped (no YouTube login yet)"
    meta = {"snippet": {"title": (s["headline"][:90] + " #Shorts"), "description": caption(lang, s, "yt"),
                        "tags": (s.get("tags") or [])[:10] + ["GenZ", "news", "shorts"],
                        "categoryId": "25", "defaultLanguage": lang, "defaultAudioLanguage": lang},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": True}}
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                      headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                               "X-Upload-Content-Type": "video/mp4"}, json=meta, timeout=60)
    r.raise_for_status()
    up = requests.put(r.headers["Location"], data=open(path, "rb"), headers={"Content-Type": "video/mp4"}, timeout=600)
    up.raise_for_status()
    return "https://youtube.com/shorts/" + up.json()["id"]


# ---------------- media hosting (Cloudflare R2, public) ----------------
def host(path, key):
    if not MEDIA_BASE:
        return None
    subprocess.run(["npx", "-y", "wrangler@4", "r2", "object", "put", f"genzpulsehub-media/{key}", "--file", path,
                    "--content-type", "video/mp4", "--remote"], check=True, capture_output=True)
    return f"{MEDIA_BASE}/{key}"


# ---------------- Meta ----------------
_pages = None


def meta_pages():
    global _pages
    if _pages is None:
        tok = env("META_TOKEN")
        _pages = {}
        if tok:
            r = requests.get(f"{G}/me/accounts", params={"access_token": tok, "limit": 50,
                             "fields": "id,name,access_token,instagram_business_account"}, timeout=30).json()
            print("meta pages seen:", [(p.get("name"), bool(p.get("instagram_business_account"))) for p in r.get("data", [])], "err:", str(r.get("error", ""))[:200])
            for p in r.get("data", []):
                for lang, name in PAGE_NAMES.items():
                    if p["name"] == name:
                        _pages[lang] = p
            # Fallback: find Instagram accounts by username (page link not always exposed)
            igs = {}
            for path in (f"{BIZ}/owned_instagram_accounts", f"{BIZ}/instagram_accounts"):
                j = requests.get(f"{G}/{path}", params={"access_token": tok, "fields": "id,username", "limit": 50}, timeout=30).json()
                for a in j.get("data", []):
                    igs[a.get("username", "").lower()] = a["id"]
                if j.get("error"):
                    print("ig lookup", path, str(j["error"].get("message"))[:150])
            for lang, p in _pages.items():
                cand = [p.get("instagram_business_account"), p.get("connected_instagram_account")]
                if not any(cand):
                    j = requests.get(f"{G}/{p['id']}", params={"access_token": p["access_token"],
                                     "fields": "instagram_business_account,connected_instagram_account"}, timeout=30).json()
                    cand = [j.get("instagram_business_account"), j.get("connected_instagram_account")]
                c = next((x for x in cand if x), None)
                if not c and IG_USERS[lang] in igs:
                    c = {"id": igs[IG_USERS[lang]]}
                if not c and IG_IDS.get(lang):
                    c = {"id": IG_IDS[lang]}
                    p["ig_token"] = tok   # system-user token has direct IG asset access
                if c:
                    p["instagram_business_account"] = c
            print("ig found:", {l: bool(p.get("instagram_business_account")) for l, p in _pages.items()}, "| biz ig usernames:", list(igs))
    return _pages


def instagram(lang, s, path):
    p = meta_pages().get(lang)
    if not p or not p.get("instagram_business_account"):
        return "skipped (Instagram not linked to Page / no Meta token)"
    ig, tok = p["instagram_business_account"]["id"], p.get("ig_token") or p["access_token"]
    c = requests.post(f"{G}/{ig}/media", data={"media_type": "REELS", "upload_type": "resumable", "share_to_feed": "true",
                      "caption": caption(lang, s, "ig"), "access_token": tok}, timeout=60).json()
    if "id" not in c:
        raise RuntimeError(str(c)[:300])
    data = open(path, "rb").read()
    up = requests.post(c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{c['id']}",
                       headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(data))},
                       data=data, timeout=300).json()
    if not up.get("success"):
        raise RuntimeError("upload " + str(up)[:300])
    for _ in range(60):
        st = requests.get(f"{G}/{c['id']}", params={"fields": "status_code,status", "access_token": tok}, timeout=30).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError("IG processing error " + str(st)[:200])
        time.sleep(10)
    pub = requests.post(f"{G}/{ig}/media_publish", data={"creation_id": c["id"], "access_token": tok}, timeout=60).json()
    if "id" not in pub:
        raise RuntimeError(str(pub)[:300])
    return "ig:" + pub["id"]


def facebook(lang, s, path):
    p = meta_pages().get(lang)
    if not p:
        return "skipped (Page not found for Meta token)"
    tok, pid = p["access_token"], p["id"]
    st = requests.post(f"{G}/{pid}/video_reels", data={"upload_phase": "start", "access_token": tok}, timeout=60).json()
    if "video_id" not in st:
        raise RuntimeError(str(st)[:300])
    vid = st["video_id"]
    data = open(path, "rb").read()
    up = requests.post(f"https://rupload.facebook.com/video-upload/v21.0/{vid}",
                       headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(data))},
                       data=data, timeout=300).json()
    if not up.get("success"):
        raise RuntimeError("upload " + str(up)[:300])
    fin = requests.post(f"{G}/{pid}/video_reels", data={"upload_phase": "finish", "video_id": vid,
                        "video_state": "PUBLISHED", "description": caption(lang, s, "fb"), "access_token": tok}, timeout=60).json()
    if not fin.get("success"):
        raise RuntimeError(str(fin)[:300])
    return "fb:" + vid


# ---------- pacing: post as much as each platform safely allows, ramping up daily ----------
RAMP_P = os.path.join(DATA, "ramp.json")
YT_PER_CHANNEL_DAY = 3          # free YouTube quota ~6 uploads/day shared by both channels
YT_GAP_H = 4
BLOCK_WORDS = ("limit", "block", "spam", "too many", "rate", "restricted", "temporarily")


def load_ramp():
    today = time.strftime("%Y-%m-%d")
    r = json.load(open(RAMP_P)) if os.path.exists(RAMP_P) else {"cap": 30, "day": today, "counts": {}, "pause": {},
                                                                  "blocked_today": False, "last_yt": {}}
    if r.get("day") != today:                      # new day: ramp up unless something got blocked
        old = r.get("cap", 30)
        r["cap"] = max(15, int(old * 0.7)) if r.get("blocked_today") else min(95, old + 5)
        if r["cap"] != old:
            discord(f"📈 Reels/Shorts daily cap per Instagram/Facebook account: {old} → {r['cap']}"
                    + (" (stepped down after a platform limit)" if r.get("blocked_today") else ""))
        r.update(day=today, counts={}, blocked_today=False)
    return r


def allowed(r, lang, plat):
    if time.time() < r.get("pause", {}).get(f"{lang}:{plat}", 0):
        return False
    n = r["counts"].get(lang, {}).get(plat, 0)
    if plat == "youtube":
        last = r.get("last_yt", {}).get(lang, 0)
        return n < YT_PER_CHANNEL_DAY and time.time() - last > YT_GAP_H * 3600
    return n < min(r["cap"], 95)


def note(r, lang, plat, result):
    if str(result).startswith(("https://", "ig:", "fb:")):
        r["counts"].setdefault(lang, {})[plat] = r["counts"].get(lang, {}).get(plat, 0) + 1
        if plat == "youtube":
            r.setdefault("last_yt", {})[lang] = time.time()
    elif str(result).startswith("error") and any(w in str(result).lower() for w in BLOCK_WORDS):
        r["blocked_today"] = True
        r.setdefault("pause", {})[f"{lang}:{plat}"] = time.time() + 6 * 3600
        discord(f"🛑 {plat} ({lang}) hit a platform limit; pausing it 6h and lowering tomorrow's cap.")


def main():
    print("media base set:", bool(MEDIA_BASE), "| meta token set:", bool(env("META_TOKEN")))
    made_p = os.path.join(OUT, "made.json")
    if not os.path.exists(made_p):
        print("nothing rendered"); return
    made = json.load(open(made_p))
    posted_p = os.path.join(DATA, "posted.json")
    posted = json.load(open(posted_p)) if os.path.exists(posted_p) else {}
    ramp = load_ramp()
    for m in made:
        lang, s, path = m["lang"], m["story"], m["path"]
        res = {}
        for name, fn in (("youtube", lambda: youtube(lang, s, path)), ("instagram", lambda: instagram(lang, s, path)),
                         ("facebook", lambda: facebook(lang, s, path))):
            if not allowed(ramp, lang, name):
                res[name] = "skipped (daily cap/pause)"; continue
            try:
                res[name] = fn()
            except Exception as e:
                res[name] = f"error: {str(e)[:200]}"
                if not any(w in str(e).lower() for w in BLOCK_WORDS):
                    discord(f"⚠️ {name} post failed ({lang}): {str(e)[:200]}")
            note(ramp, lang, name, res[name])
        if any(str(v).startswith(("https://", "ig:", "fb:")) for v in res.values()):
            posted.setdefault(lang, {})[s["id"]] = {"at": time.strftime("%Y-%m-%d %H:%M"), **res}
        print(lang, s["id"], json.dumps(res))
    # keep last 300 per language
    for lang in posted:
        posted[lang] = dict(list(posted[lang].items())[-300:])
    json.dump(posted, open(posted_p, "w"), ensure_ascii=False, indent=1)
    json.dump(ramp, open(RAMP_P, "w"), indent=1)


if __name__ == "__main__":
    main()
