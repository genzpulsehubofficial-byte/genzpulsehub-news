"""GenZ Pulse Hub 24/7 live stream engine (runs on the Oracle VM, one process per language).

Loop: latest stories -> 1280x720 slide + AI voice -> MPEG-TS segment with continuous timestamps
-> one ffmpeg that copies the feed to YouTube + Facebook (tee muxer). Restarts every ~7h50m
(Facebook ends any single live after 8h). Keys come from /etc/gph.env:
  YT_KEY_EN, YT_KEY_ML, FB_KEY_EN, FB_KEY_ML, DISCORD_WEBHOOK_URL (optional)
"""
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shorts"))
from render import COLOR, dur, font, put, tlen, tts_file, wrap  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

LANG = sys.argv[1] if len(sys.argv) > 1 else "en"
W, H = 1280, 720
CYCLE = int(os.environ.get("STREAM_CYCLE_SEC", str(7 * 3600 + 50 * 60)))
ADS_API = "https://genzpulsehub-ads.genzpulsehub-official.workers.dev/api/active"
SITE = {"en": "https://genzpulsehub.pages.dev", "ml": "https://genzpulsehub.pages.dev/ml"}
TXT = {
    "en": {"live": "LIVE", "why": "WHY IT MATTERS", "next": "UP NEXT", "ad": "Advertise here → " + SITE["en"] + "/advertise",
           "intro": "You're watching GenZ Pulse Hub, live news for your generation. Here's what's happening."},
    "ml": {"live": "തത്സമയം", "why": "നിങ്ങളെ എങ്ങനെ ബാധിക്കും", "next": "അടുത്തത്",
           "ad": "പരസ്യം നൽകാം → " + SITE["en"] + "/advertise",
           "intro": "നിങ്ങൾ കാണുന്നത് ജെൻ സി പൾസ് ഹബ് തത്സമയ വാർത്തകൾ. ഇതാ ഇപ്പോഴത്തെ വാർത്തകൾ."},
}
WORK = os.path.join(tempfile.gettempdir(), f"gph-{LANG}")
os.makedirs(WORK, exist_ok=True)


def log(*a):
    print(time.strftime("%H:%M:%S"), LANG, *a, flush=True)


def discord(msg):
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not hook:
        return
    try:
        req = urllib.request.Request(hook, data=json.dumps({"content": f"@everyone [stream {LANG}] {msg}"}).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "gph"})
        urllib.request.urlopen(req, timeout=15)
    except Exception:
        pass


FB_PAGE = {"en": "GenZ Pulse Hub", "ml": "GenZ Pulse Hub Malayalam"}
G = "https://graph.facebook.com/v21.0"
_fb = {"id": None, "tok": None, "ok_once": False, "next_try": 0}


def _graph(path, data=None, method=None):
    import urllib.parse
    req = urllib.request.Request(G + path, data=urllib.parse.urlencode(data).encode() if data else None, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        return json.load(e)


def fb_start():
    """Create a Facebook live via the API (needs Page 60+ days old & 100+ followers). Retries every 6h until allowed."""
    tok = os.environ.get("META_TOKEN")
    if not tok or time.time() < _fb["next_try"]:
        return None
    pages = _graph(f"/me/accounts?fields=name,id,access_token&access_token={tok}").get("data", [])
    p = next((x for x in pages if x["name"] == FB_PAGE[LANG]), None)
    if not p:
        return None
    lv = _graph(f"/{p['id']}/live_videos", {"status": "LIVE_NOW", "access_token": p["access_token"],
                "title": "GenZ Pulse Hub LIVE" + (" Malayalam" if LANG == "ml" else ""),
                "description": "24/7 news for your generation. Full stories: " + SITE[LANG]})
    url = lv.get("secure_stream_url") or lv.get("stream_url")
    if not url:
        log("facebook live not allowed yet:", str(lv.get("error", {}).get("message"))[:120])
        _fb["next_try"] = time.time() + 6 * 3600
        return None
    _fb.update(id=lv["id"], tok=p["access_token"])
    if not _fb["ok_once"]:
        _fb["ok_once"] = True
        discord("✅ Facebook live started automatically.")
    return url


def fb_stop():
    if _fb["id"]:
        _graph(f"/{_fb['id']}", {"end_live_video": "true", "access_token": _fb["tok"]})
        _fb["id"] = None


def outputs():
    o = []
    yt, fb = os.environ.get(f"YT_KEY_{LANG.upper()}"), os.environ.get(f"FB_KEY_{LANG.upper()}")
    if yt:
        o.append(f"[f=flv:onfail=ignore]rtmp://a.rtmp.youtube.com/live2/{yt}")
    if fb:
        o.append(f"[f=flv:onfail=ignore]rtmps://live-api-s.facebook.com:443/rtmp/{fb}")
    else:
        url = fb_start()
        if url:
            o.append(f"[f=flv:onfail=ignore]{url}")
    return o


def stories():
    subprocess.run(["git", "-C", ROOT, "pull", "-q"], capture_output=True)
    try:
        items = json.load(open(os.path.join(ROOT, "data", f"latest_{LANG}.json")))
    except Exception:
        items = []
    return [s for s in items if s.get("headline")][:25]


def ad_text():
    try:
        with urllib.request.urlopen(f"{ADS_API}?placement=ticker&lang={LANG}", timeout=10) as r:
            ads = json.load(r)
        ads = ads.get("ads", ads) if isinstance(ads, dict) else ads
        if ads:
            a = random.choice(ads)
            return "Sponsored: " + (a.get("text") or a.get("headline") or "")[:110]
    except Exception:
        pass
    return TXT[LANG]["ad"]


def slide(s, upnext, ad, path):
    t = TXT[LANG]
    img = Image.new("RGB", (W, H), "#0b0b14")
    d = ImageDraw.Draw(img)
    accent = COLOR.get(s.get("category", ""), "#ff3cac")
    for y in range(H):  # soft vertical gradient
        d.line([(0, y), (W, y)], fill=(11 + y // 40, 11, 20 + y // 20))
    d.rectangle([0, 0, W, 64], fill="#12121f")
    d.rounded_rectangle([24, 14, 24 + tlen(d, t["live"], font(LANG, 26)) + 44, 52], 8, fill="#e10600")
    d.ellipse([34, 26, 46, 38], fill="white")
    put(d, (54, 16), t["live"], font(LANG, 26), "white")
    put(d, (W - 330, 16), "GenZ Pulse Hub", font("en", 28), "white")
    d.rectangle([0, 64, 10, H - 120], fill=accent)
    cat = (s.get("category") or "news").upper()
    put(d, (48, 92), cat, font("en", 24), accent)
    y = 132
    for line in wrap(d, s["headline"], font(LANG, 46), W - 110)[:3]:
        put(d, (48, y), line, font(LANG, 46), "white"); y += 62
    y += 12
    for line in wrap(d, s.get("what", ""), font(LANG, 28, bold=False), W - 110)[:4]:
        put(d, (48, y), line, font(LANG, 28, bold=False), "#d9d9e6"); y += 40
    y += 14
    put(d, (48, y), t["why"], font(LANG, 24), accent); y += 38
    for line in wrap(d, s.get("why", ""), font(LANG, 28, bold=False), W - 110)[:3]:
        put(d, (48, y), line, font(LANG, 28, bold=False), "#ffffff"); y += 40
    d.rectangle([0, H - 120, W, H - 64], fill="#1b1b2e")
    put(d, (24, H - 112), t["next"] + ":", font(LANG, 22), accent)
    nx = (upnext or "")[:90]
    put(d, (24 + tlen(d, t["next"] + ":", font(LANG, 22)) + 12, H - 112), nx, font(LANG, 22, bold=False), "white")
    d.rectangle([0, H - 64, W, H], fill=accent)
    put(d, (24, H - 52), ad, font(LANG, 26), "#0b0b14")
    src = s.get("source")
    if src:
        put(d, (W - 24 - tlen(d, "Source: " + src, font("en", 18, bold=False)), H - 150), "Source: " + src,
            font("en", 18, bold=False), "#8a8aa3")
    img.save(path)


def segment(png, mp3, out, offset):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", png, "-i", mp3,
                    "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                    "-r", "30", "-g", "60", "-b:v", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                    "-af", "apad=pad_dur=1.5", "-shortest", "-output_ts_offset", f"{offset:.3f}",
                    "-mpegts_flags", "+resend_headers", "-f", "mpegts", out], check=True)


def run_cycle(outs):
    fifo = os.path.join(WORK, "feed.ts")
    if os.path.exists(fifo):
        os.remove(fifo)
    os.mkfifo(fifo)
    cmd = ["ffmpeg", "-loglevel", "warning", "-re", "-f", "mpegts", "-i", fifo, "-c", "copy", "-map", "0",
           "-flvflags", "no_duration_filesize", "-f", "tee", "|".join(outs)]
    proc = subprocess.Popen(cmd)
    start, offset, n = time.time(), 1.0, 0
    with open(fifo, "wb") as feed:
        while time.time() - start < CYCLE and proc.poll() is None:
            items = stories()
            if not items:
                time.sleep(30); continue
            ad = ad_text()
            seq = [{"headline": "GenZ Pulse Hub", "what": TXT[LANG]["intro"], "why": "", "category": "trending",
                    "_say": TXT[LANG]["intro"]}] + items
            for i, s in enumerate(seq):
                if time.time() - start >= CYCLE or proc.poll() is not None:
                    break
                png, mp3, ts = (os.path.join(WORK, f"{n % 3}.{e}") for e in ("png", "mp3", "ts"))
                try:
                    say = s.get("_say") or ". ".join(x for x in (s.get("hook"), s["headline"], s.get("what"), s.get("why")) if x)
                    tts_file(say, LANG, mp3)
                    nxt = seq[i + 1]["headline"] if i + 1 < len(seq) else (items[0]["headline"] if items else "")
                    slide(s, nxt, ad, png)
                    segment(png, mp3, ts, offset)
                    offset += dur(ts) or (dur(mp3) + 1.5)
                    with open(ts, "rb") as f:
                        feed.write(f.read())
                    feed.flush(); n += 1
                except BrokenPipeError:
                    break
                except Exception as e:
                    log("segment error", e)
    try:
        proc.terminate(); proc.wait(timeout=20)
    except Exception:
        proc.kill()
    return proc.returncode


def main():
    fails = 0
    while True:
        outs = outputs()
        if not outs:
            log("no stream keys yet; waiting"); time.sleep(300); continue
        log("starting cycle ->", len(outs), "destinations")
        t0 = time.time()
        try:
            run_cycle(outs)
        finally:
            fb_stop()
        if time.time() - t0 < 600:
            fails += 1
            if fails in (3, 10):
                discord(f"stream keeps stopping early ({fails} times). Check stream keys / platform status.")
            time.sleep(min(300, 20 * fails))
        else:
            fails = 0


if __name__ == "__main__":
    main()
