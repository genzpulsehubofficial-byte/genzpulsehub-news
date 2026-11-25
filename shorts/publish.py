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
PAGE_NAMES = {"en": "GenZ Pulse Hub", "ml": "GenZ Pulse Hub Malayalam"}
SITE = {"en": "https://genzpulsehub.dpdns.org", "ml": "https://genzpulsehub.dpdns.org/ml"}
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
            for p in r.get("data", []):
                for lang, name in PAGE_NAMES.items():
                    if p["name"] == name:
                        _pages[lang] = p
    return _pages


def instagram(lang, s, url):
    p = meta_pages().get(lang)
    if not p or not p.get("instagram_business_account") or not url:
        return "skipped (no Meta login / media URL yet)"
    ig, tok = p["instagram_business_account"]["id"], p["access_token"]
    c = requests.post(f"{G}/{ig}/media", data={"media_type": "REELS", "video_url": url, "share_to_feed": "true",
                      "caption": caption(lang, s, "ig"), "access_token": tok}, timeout=60).json()
    if "id" not in c:
        raise RuntimeError(str(c)[:300])
    for _ in range(40):
        st = requests.get(f"{G}/{c['id']}", params={"fields": "status_code", "access_token": tok}, timeout=30).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError("IG processing error")
        time.sleep(10)
    pub = requests.post(f"{G}/{ig}/media_publish", data={"creation_id": c["id"], "access_token": tok}, timeout=60).json()
    return "ig:" + pub.get("id", str(pub)[:120])


def facebook(lang, s, url):
    p = meta_pages().get(lang)
    if not p or not url:
        return "skipped (no Meta login / media URL yet)"
    tok, pid = p["access_token"], p["id"]
    st = requests.post(f"{G}/{pid}/video_reels", data={"upload_phase": "start", "access_token": tok}, timeout=60).json()
    vid = st["video_id"]
    up = requests.post(f"https://rupload.facebook.com/video-upload/v21.0/{vid}",
                       headers={"Authorization": f"OAuth {tok}", "file_url": url}, timeout=120).json()
    if not up.get("success"):
        raise RuntimeError(str(up)[:300])
    fin = requests.post(f"{G}/{pid}/video_reels", data={"upload_phase": "finish", "video_id": vid,
                        "video_state": "PUBLISHED", "description": caption(lang, s, "fb"), "access_token": tok}, timeout=60).json()
    return "fb:" + str(fin.get("success", fin))[:80]


def main():
    made_p = os.path.join(OUT, "made.json")
    if not os.path.exists(made_p):
        print("nothing rendered"); return
    made = json.load(open(made_p))
    posted_p = os.path.join(DATA, "posted.json")
    posted = json.load(open(posted_p)) if os.path.exists(posted_p) else {}
    for m in made:
        lang, s, path = m["lang"], m["story"], m["path"]
        res = {}
        try:
            url = host(path, f"{lang}/{s['id']}.mp4")
        except Exception as e:
            url, res["media"] = None, f"error: {e}"
        for name, fn in (("youtube", lambda: youtube(lang, s, path)), ("instagram", lambda: instagram(lang, s, url)),
                         ("facebook", lambda: facebook(lang, s, url))):
            try:
                res[name] = fn()
            except Exception as e:
                res[name] = f"error: {str(e)[:200]}"
                discord(f"⚠️ {name} post failed ({lang}): {str(e)[:200]}")
        if any(str(v).startswith(("https://", "ig:", "fb:")) for v in res.values()):
            posted.setdefault(lang, {})[s["id"]] = {"at": time.strftime("%Y-%m-%d %H:%M"), **res}
        print(lang, s["id"], json.dumps(res))
    # keep last 300 per language
    for lang in posted:
        posted[lang] = dict(list(posted[lang].items())[-300:])
    json.dump(posted, open(posted_p, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
