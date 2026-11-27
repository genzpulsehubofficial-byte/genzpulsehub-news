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
def _base():
    try:
        if urllib.request.urlopen("https://genzpulsehub.dpdns.org/", timeout=10).status == 200:
            return "https://genzpulsehub.dpdns.org"
    except Exception:
        pass
    return "https://genzpulsehub.pages.dev"


SITE = {"en": _base(), "ml": _base() + "/ml"}   # re-checked at each restart (every ~8h)
TXT = {
    "en": {"live": "LIVE", "why": "WHY IT MATTERS", "next": "UP NEXT", "ad": "Advertise here → " + SITE["en"].replace("https://", "") + "/advertise",
           "intro": "You're watching GenZ Pulse Hub, live news for your generation. Here's what's happening."},
    "ml": {"live": "തത്സമയം", "why": "നിങ്ങളെ എങ്ങനെ ബാധിക്കും", "next": "അടുത്തത്",
           "ad": "പരസ്യം നൽകാം: " + SITE["en"].replace("https://", "") + "/advertise",
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


def overlay(s, upnext, ad, path):
    """Transparent TV-news overlay (1280x720): LIVE bug, category, lower third, up-next bar, ad ticker."""
    t = TXT[LANG]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    accent = COLOR.get(s.get("category", ""), "#ff3cac")
    for y in range(H - 330, H):                     # dark fade behind lower third
        a = int(215 * min(1, (y - (H - 330)) / 110))
        d.line([(0, y), (W, y)], fill=(8, 8, 16, a))
    d.rounded_rectangle([24, 20, 24 + tlen(d, t["live"], font(LANG, 26)) + 46, 58], 8, fill="#e10600")
    d.ellipse([34, 32, 46, 44], fill="white")
    put(d, (56, 22), t["live"], font(LANG, 26), "white")
    put(d, (W - 260, 22), "GenZ Pulse Hub", font("en", 28), "white")
    cat = (s.get("category") or "news").upper()
    cw = tlen(d, cat, font("en", 22)) + 30
    d.rounded_rectangle([40, H - 300, 40 + cw, H - 266], 8, fill=accent)
    put(d, (55, H - 298), cat, font("en", 22), "#0b0b14")
    y = H - 256
    for line in wrap(d, s["headline"], font(LANG, 40), W - 380)[:2]:
        put(d, (40, y), line, font(LANG, 40), "white"); y += 52
    why = s.get("why") or s.get("what") or ""
    if why:
        put(d, (40, y + 2), (wrap(d, why, font(LANG, 24, bold=False), W - 380) or [""])[0], font(LANG, 24, bold=False), "#d9d9e6")
    d.rectangle([0, H - 104, W, H - 64], fill=(27, 27, 46, 235))
    put(d, (24, H - 100), t["next"] + ":", font(LANG, 22), accent)
    put(d, (24 + tlen(d, t["next"] + ":", font(LANG, 22)) + 10, H - 100), (upnext or "")[:80], font(LANG, 22, bold=False), "white")
    d.rectangle([0, H - 64, W, H], fill=accent)
    put(d, (24, H - 54), ad, font(LANG, 26), "#0b0b14")
    if s.get("source"):
        st = "Source: " + s["source"]
        put(d, (W - 24 - tlen(d, st, font("en", 18, bold=False)), H - 128), st, font("en", 18, bold=False), "#b0b0c8")
    img.save(path)


def background(s, need, tmp):
    """Landscape stock footage for the story (Pixabay), else a moving brand gradient."""
    try:
        import render_v2
        clips = render_v2.pexels_clips([q for q in _queries(s)], need, tmp) if (render_v2.PIXABAY or render_v2.PEXELS) else []
    except Exception as e:
        log("footage", e); clips = []
    out = os.path.join(tmp, "bg.mp4")
    norm = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1"
    if clips:
        parts = []
        for i, c in enumerate(clips):
            p = os.path.join(tmp, f"n{i}.mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", c, "-t", "8", "-an", "-vf", norm, "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "26", p], check=True)
            parts.append(p)
        lst = os.path.join(tmp, "bg.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", lst,
                        "-t", f"{need:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", out], check=True)
        return out
    c = COLOR.get(s.get("category", ""), "#ff3cac").lstrip("#")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"gradients=s={W}x{H}:c0=0x0b0b14:c1=0x{c}:c2=0x1b1035:n=3:speed=0.015:r=30", "-t", f"{need:.2f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", out], check=True)
    return out


def _queries(s):
    import re
    tags = [re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t) for t in (s.get("tags_en") or s.get("tags") or [])
            if re.match(r"^[A-Za-z0-9 &-]+$", t)]
    return tags[:3] + [{"jobs": "office", "money": "money", "tech": "technology", "sports": "stadium",
                        "entertainment": "cinema", "health": "healthy", "kerala": "kerala"}.get(s.get("category"), "city")]


def segment(s, say, upnext, ad, out, offset):
    import render_v2
    tmp = tempfile.mkdtemp(dir=WORK)
    try:
        mp3 = os.path.join(tmp, "v.mp3")
        render_v2.voice(say, LANG, mp3)
        total = dur(mp3) + 1.2
        bg = background(s, total, tmp)
        ov = os.path.join(tmp, "ov.png"); overlay(s, upnext, ad, ov)
        masc = render_v2.mascot_track(mp3, total, COLOR.get(s.get("category", ""), "#ff3cac"), tmp)
        mw = render_v2.MW
        fc = (f"[0:v]eq=brightness=-0.12:saturation=1.1[b];[b][1:v]overlay=0:0[o];"
              f"[2:v]format=rgba,fps=30,scale={int(mw * 0.8)}:-1[m];"
              f"[o][m]overlay=x=W-{int(mw * 0.8)}-20:y=H-{int(mw * 0.8)}-110+6*sin(2*PI*t*1.3):eof_action=pass[v]")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", bg, "-loop", "1", "-i", ov,
                        "-f", "concat", "-safe", "0", "-i", masc, "-i", mp3, "-filter_complex", fc,
                        "-map", "[v]", "-map", "3:a", "-t", f"{total:.2f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
                        "-b:v", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
                        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-af", "apad",
                        "-output_ts_offset", f"{offset:.3f}", "-mpegts_flags", "+resend_headers", "-f", "mpegts", out],
                       check=True)
    finally:
        subprocess.run(["rm", "-rf", tmp])


def slim_overlay(s, upnext, ad, path):
    """Minimal live chrome on top of the explainer look: LIVE bug, brand, up-next + ad ticker."""
    t = TXT[LANG]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    accent = COLOR.get(s.get("category", ""), "#4ee0d0")
    d.rounded_rectangle([24, 20, 24 + tlen(d, t["live"], font(LANG, 24)) + 44, 56], 8, fill="#e10600")
    d.ellipse([34, 32, 44, 42], fill="white")
    put(d, (54, 22), t["live"], font(LANG, 24), "white")
    d.rectangle([0, H - 72, W, H - 40], fill=(8, 10, 16, 210))
    put(d, (20, H - 70), t["next"] + ":", font(LANG, 20), accent)
    put(d, (20 + tlen(d, t["next"] + ":", font(LANG, 20)) + 10, H - 70), (upnext or "")[:90], font(LANG, 20, bold=False), "white")
    d.rectangle([0, H - 40, W, H], fill=accent)
    put(d, (20, H - 36), ad, font(LANG, 22), "#0b0b14")
    img.save(path)


def segment_explainer(s, upnext, ad, out, offset):
    sys.path.insert(0, os.path.join(ROOT, "shorts"))
    import explainer
    tmp = tempfile.mkdtemp(dir=WORK)
    try:
        mp4 = explainer.build(LANG, s, os.path.join(tmp, "x.mp4"), W=W, H=H - 72, tmp=os.path.join(tmp, "w"))
        ov = os.path.join(tmp, "ov.png"); slim_overlay(s, upnext, ad, ov)
        fc = f"[0:v]pad={W}:{H}:0:0:black[p];[p][1:v]overlay=0:0[v]"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-loop", "1", "-i", ov, "-filter_complex", fc,
                        "-map", "[v]", "-map", "0:a", "-shortest",
                        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
                        "-b:v", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
                        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                        "-output_ts_offset", f"{offset:.3f}", "-mpegts_flags", "+resend_headers", "-f", "mpegts", out],
                       check=True)
    finally:
        subprocess.run(["rm", "-rf", tmp])


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
                ts = os.path.join(WORK, f"{n % 3}.ts")
                try:
                    say = s.get("_say") or s.get("say") or ". ".join(x for x in (s["headline"], s.get("what"), s.get("why")) if x)
                    nxt = seq[i + 1]["headline"] if i + 1 < len(seq) else (items[0]["headline"] if items else "")
                    if s.get("_say"):
                        segment(s, say, nxt, ad, ts, offset)
                    else:
                        try:
                            segment_explainer(s, nxt, ad, ts, offset)
                        except Exception as e:
                            log("explainer failed, classic segment", e)
                            segment(s, say, nxt, ad, ts, offset)
                    offset += dur(ts)
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
