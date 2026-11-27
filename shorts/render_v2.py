"""Shorts/Reels v2: retention-style vertical video (ideas from MoneyPrinterTurbo & viral short-form practice).

- Moving background: free stock clips from Pexels matched to the story (PEXELS_API_KEY); falls back to
  an animated brand background, so it always works.
- Word-by-word captions (current word highlighted), timed from edge-tts word boundaries; gTTS fallback is
  estimated timing. Big hook headline panel, top progress bar, follow/subscribe end card.
- No background music (avoids copyright claims).
"""
import asyncio
import json
import os
import random
import re
import subprocess
import urllib.parse
import urllib.request

import edge_tts
from PIL import Image, ImageDraw

from render import COLOR, VOICE, dur, font, put, tlen, wrap

W, H = 1080, 1920
PEXELS = os.environ.get("PEXELS_API_KEY", "")
PIXABAY = os.environ.get("PIXABAY_API_KEY", "")
END = {"en": "Follow for daily news", "ml": "ദിവസവും വാർത്തകൾക്ക് ഫോളോ ചെയ്യൂ"}
SAY_END = {"en": "Follow for more.", "ml": "കൂടുതൽ വാർത്തകൾക്ക് ഫോളോ ചെയ്യൂ."}
_FONTNAME_UNUSED = {"en": "Noto Sans", "ml": "Noto Sans Malayalam"}
FALLBACK_Q = {"headlines": "city crowd", "jobs": "office work", "money": "money cash", "tech": "technology",
              "exams": "students study", "trending": "people phone", "entertainment": "cinema lights",
              "health": "healthy lifestyle", "sports": "stadium sports", "kerala": "kerala"}


# ---------- voice + word timings ----------
async def _edge_words(text, voice, path, rate, pitch="+0Hz"):
    words = []
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    except TypeError:  # older edge-tts
        comm = edge_tts.Communicate(text, voice, rate=rate)
    with open(path, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
    return words


PAUSE = {".": 0.45, "?": 0.45, "!": 0.45, "।": 0.45, ":": 0.3, ";": 0.3, ",": 0.2, "-": 0.15}
RATE = {"en": "+8%", "ml": "-6%"}   # Malayalam a little slower = clearer, more natural


def _chunks(text):
    """Split at punctuation so every comma / full stop gets a real pause."""
    t = re.sub(r"(?<=\d)([.,])(?=\d)", lambda m: "\x00" if m.group(1) == "," else "\x01", text.replace(" - ", ", "))
    parts = [p.replace("\x00", ",").replace("\x01", ".") for p in re.findall(r"[^.?!।:;,]+[.?!।:;,]*", t)]
    out = []
    for p in parts:
        p = p.strip()
        if p:
            out.append((p, PAUSE.get(p[-1], 0.1)))
    return out or [(text, 0.1)]


def _silence(sec, path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", f"{sec:.2f}", "-c:a", "libmp3lame", "-b:a", "48k", path], check=True)


def voice(text, lang, path, pitch="+0Hz"):
    try:
        tmp = path + "_parts"; os.makedirs(tmp, exist_ok=True)
        files, words, t = [], [], 0.0
        for i, (chunk, gap) in enumerate(_chunks(text)):
            a = os.path.join(tmp, f"c{i}.mp3")
            ws = asyncio.run(_edge_words(chunk, VOICE[lang], a, RATE[lang], pitch))
            if os.path.getsize(a) < 500:
                raise RuntimeError("empty chunk")
            d = dur(a)
            words += [(t + s, t + e, w) for s, e, w in (ws or estimate(chunk, d))]
            sp = os.path.join(tmp, f"s{i}.mp3"); _silence(gap, sp)
            files += [a, sp]; t += d + gap
        lst = os.path.join(tmp, "list.txt")
        open(lst, "w").write("".join(f"file '{os.path.abspath(f)}'\n" for f in files))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c:a", "libmp3lame", "-b:a", "96k", "-ar", "24000", "-ac", "1", path], check=True)
        if os.path.getsize(path) > 1000:
            return words
    except Exception as e:
        print("edge-tts failed:", str(e)[:80])
    from gtts import gTTS
    gTTS(text, lang=lang, tld="co.in" if lang == "en" else "com").save(path)
    return estimate(text, dur(path))


def estimate(text, total):
    ws = text.split()
    n = sum(len(w) + 1 for w in ws) or 1
    t, out = 0.15, []
    for w in ws:
        d = (len(w) + 1) / n * (total - 0.3)
        out.append((t, t + d, w)); t += d
    return out


# ---------- background ----------
def _download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (GenZPulseHub)"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())


def pixabay_clips(queries, need, tmp):
    got, total = [], 0.0
    for q in queries:
        try:
            u = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(
                {"key": PIXABAY, "q": q[:90], "per_page": 12, "safesearch": "true", "video_type": "film"})
            hits = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "gph"}), timeout=20)).get("hits", [])
        except Exception as e:
            print("pixabay", q, str(e)[:80]); continue
        print("pixabay", q, len(hits), "hits")
        random.shuffle(hits)
        for h in hits:
            v = h.get("videos", {})
            f = v.get("medium") or v.get("large") or v.get("small")
            if not f or not f.get("url"):
                continue
            p = os.path.join(tmp, f"bg{len(got)}.mp4")
            try:
                _download(f["url"], p)
            except Exception as e:
                print("pixabay download", str(e)[:80]); continue
            got.append(p); total += min(dur(p), 7)
            break
        if total >= need:
            break
    return got


def pexels_clips(queries, need, tmp):
    if not PEXELS:
        return pixabay_clips(queries, need, tmp) if PIXABAY else []
    got, total = [], 0.0
    for q in queries:
        try:
            req = urllib.request.Request(
                "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
                    {"query": q, "orientation": "portrait", "per_page": 8, "size": "medium"}),
                headers={"Authorization": PEXELS, "User-Agent": "gph"})
            vids = json.load(urllib.request.urlopen(req, timeout=20)).get("videos", [])
        except Exception as e:
            print("pexels", q, str(e)[:80]); continue
        random.shuffle(vids)
        for v in vids:
            files = sorted([f for f in v.get("video_files", []) if f.get("height") and f["height"] >= 1280
                            and f.get("width", 0) < f["height"]], key=lambda f: f["height"])
            if not files:
                continue
            p = os.path.join(tmp, f"bg{len(got)}.mp4")
            try:
                _download(files[0]["link"], p)
            except Exception:
                continue
            got.append(p); total += min(dur(p), 7)
            break
        if total >= need:
            break
    return got


def background(s, lang, need, tmp):
    tags = [re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t) for t in (s.get("tags_en") or s.get("tags") or [])
            if re.match(r"^[A-Za-z0-9 &-]+$", t)]
    stop = {"the", "and", "for", "with", "from", "into", "over", "after", "this", "that", "your", "hold", "holds",
            "says", "said", "new", "will", "has", "have", "are", "is", "in", "on", "of", "to", "a", "an", "at"}
    head = s.get("headline", "") if lang == "en" else " ".join(tags)
    kw = [w for w in re.findall(r"[A-Za-z]{3,}", head) if w.lower() not in stop][:3]
    qs = ([" ".join(kw)] if kw else []) + tags[:3] + [FALLBACK_Q.get(s.get("category", ""), "news")]
    clips = pexels_clips(qs, need, tmp)
    out = os.path.join(tmp, "bg.mp4")
    norm = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1"
    if clips:
        parts = []
        for i, c in enumerate(clips):
            p = os.path.join(tmp, f"n{i}.mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", c, "-t", "7", "-an", "-vf", norm,
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", p], check=True)
            parts.append(p)
        lst = os.path.join(tmp, "bg.txt")
        open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-f", "concat", "-safe", "0",
                        "-i", lst, "-t", f"{need:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                        out], check=True)
        return out
    # fallback: slow-moving brand gradient
    c = COLOR.get(s.get("category", ""), "#ff3cac").lstrip("#")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"gradients=s=1080x1920:c0=0x0b0b14:c1=0x{c}:c2=0x1b1035:n=3:speed=0.015:r=30",
                    "-t", f"{need:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", out], check=True)
    return out


# ---------- overlays ----------
def top_panel(s, lang, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    accent = COLOR.get(s.get("category", ""), "#ff3cac")
    for yy in range(0, 700):   # dark panel fading out, no hard edge
        a = 175 if yy < 520 else int(175 * (700 - yy) / 180)
        d.line([(0, yy), (W, yy)], fill=(8, 8, 16, a))
    cat = (s.get("category") or "news").upper()
    if s.get("breaking"):
        cat = "BREAKING · " + cat
    bw = tlen(d, cat, font("en", 34)) + 44
    d.rounded_rectangle([56, 110, 56 + bw, 166], 14, fill=accent)
    put(d, (78, 116), cat, font("en", 34), "#0b0b14")
    y = 196
    for line in wrap(d, s["headline"], font(lang, 64), W - 112)[:4]:
        put(d, (56, y), line, font(lang, 64), "white"); y += 84
    put(d, (56, H - 150), "GenZ Pulse Hub", font("en", 34), "white")
    img.save(path)


def cap_png(words_in_group, hi, lang, path, end_text=None):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if words_in_group:
        f = font(lang, 80 if lang == "en" else 70)
        line = " ".join(words_in_group)
        lines = wrap(d, line, f, W - 140)
        y = 1110 - (len(lines) - 1) * 50
        idx = 0
        for ln in lines:
            ws = ln.split(" ")
            x = (W - tlen(d, ln, f)) / 2
            for w in ws:
                col = "#FFE600" if idx == hi else "white"
                for dx, dy in ((-4, 0), (4, 0), (0, -4), (0, 4), (-3, -3), (3, 3), (-3, 3), (3, -3), (0, 6)):
                    put(d, (x + dx, y + dy), w, f, "black")
                put(d, (x, y), w, f, col)
                x += tlen(d, w, f); idx += 1
            y += 100
    if end_text:
        f = font(lang, 64 if lang == "en" else 56)
        lines = wrap(d, end_text, f, W - 160)
        y = 1560 - len(lines) * 104
        for ln in lines:
            wdt = tlen(d, ln, f)
            d.rounded_rectangle([(W - wdt) / 2 - 30, y - 12, (W + wdt) / 2 + 20, y + 84], 20, fill=(10, 10, 20, 225))
            put(d, ((W - wdt) / 2, y), ln, f, "white"); y += 104
    img.save(path)


def captions(words, lang, total, tmp):
    """Pre-render caption frames (Pillow+RAQM shapes Malayalam correctly) and return an ffconcat list."""
    events, t = [], 0.0
    groups = [words[i:i + 3] for i in range(0, len(words), 3)]
    for g in groups:
        for j, (a, b, _) in enumerate(g):
            end = g[j + 1][0] if j + 1 < len(g) else b + 0.12
            events.append((a, end, [w for _, _, w in g], j))
    lst = ["ffconcat version 1.0"]
    blank = os.path.join(tmp, "blank.png"); Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    endstart = total - 2.4
    n = 0
    for a, e, ws, j in events:
        if a >= endstart:
            break
        e = min(e, endstart)
        if a > t + 0.01:
            lst += [f"file '{blank}'", f"duration {a - t:.3f}"]
        p = os.path.join(tmp, f"c{n}.png"); n += 1
        cap_png(ws, j, lang, p)
        lst += [f"file '{p}'", f"duration {max(e - a, 0.04):.3f}"]
        t = e
    p = os.path.join(tmp, "end.png"); cap_png([], -1, lang, p, END[lang])
    lst += [f"file '{p}'", f"duration {max(total - t, 0.5):.3f}", f"file '{p}'"]
    path = os.path.join(tmp, "caps.txt"); open(path, "w").write("\n".join(lst) + "\n")
    return path


# ---------- mascot "Pulse" (original character): blinks, bobs, lip-syncs to the voice ----------
MW = 340


def mascot_sprites(accent, tmp):
    out = {}
    for mouth in (0, 1, 2):
        for blink in (0, 1):
            im = Image.new("RGBA", (MW, MW), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            d.ellipse([40, 300, 300, 336], fill=(0, 0, 0, 90))                           # shadow
            d.rounded_rectangle([70, 70, 270, 290], 90, fill="#f4f1ff", outline="#0b0b14", width=8)  # head
            d.arc([40, 40, 300, 250], 200, 340, fill=accent, width=22)                    # headphone band
            d.rounded_rectangle([42, 150, 92, 240], 22, fill=accent, outline="#0b0b14", width=6)
            d.rounded_rectangle([248, 150, 298, 240], 22, fill=accent, outline="#0b0b14", width=6)
            d.line([(170, 70), (170, 30)], fill="#0b0b14", width=8); d.ellipse([152, 12, 188, 48], fill=accent)
            for ex in (130, 210):                                                         # eyes
                if blink:
                    d.line([(ex - 18, 160), (ex + 18, 160)], fill="#0b0b14", width=8)
                else:
                    d.ellipse([ex - 18, 140, ex + 18, 180], fill="#0b0b14"); d.ellipse([ex - 6, 146, ex + 4, 156], fill="white")
            d.ellipse([92, 190, 118, 208], fill=(255, 120, 150, 140)); d.ellipse([222, 190, 248, 208], fill=(255, 120, 150, 140))
            if mouth == 0:
                d.arc([140, 200, 200, 240], 20, 160, fill="#0b0b14", width=8)
            else:
                h = 16 if mouth == 1 else 34
                d.rounded_rectangle([145, 212, 195, 212 + h], 14, fill="#3a0d1a", outline="#0b0b14", width=6)
            p = os.path.join(tmp, f"m{mouth}{blink}.png"); im.save(p); out[(mouth, blink)] = p
    return out


def mascot_track(mp3, total, accent, tmp):
    import array
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", mp3, "-ac", "1", "-ar", "3000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    a = array.array("h"); a.frombytes(raw[: len(raw) // 2 * 2])
    fps, per = 15, 200
    sprites = mascot_sprites(accent, tmp)
    frames = int(total * fps)
    seq = []
    for i in range(frames):
        win = a[i * per:(i + 1) * per]
        rms = (sum(x * x for x in win) / len(win)) ** 0.5 if len(win) else 0
        mouth = 0 if rms < 600 else (1 if rms < 2600 else 2)
        blink = 1 if (i % 52) in (0, 1) else 0
        seq.append(sprites[(mouth, blink)])
    lst = ["ffconcat version 1.0"]
    i = 0
    while i < len(seq):
        j = i
        while j + 1 < len(seq) and seq[j + 1] == seq[i]:
            j += 1
        lst += [f"file '{seq[i]}'", f"duration {(j - i + 1) / fps:.3f}"]
        i = j + 1
    lst.append(f"file '{seq[-1]}'")
    path = os.path.join(tmp, "mascot.txt"); open(path, "w").write("\n".join(lst) + "\n")
    return path


def render(lang, s, outdir):
    os.makedirs(outdir, exist_ok=True)
    tmp = os.path.abspath(os.path.join(outdir, "v2_" + s["id"])); os.makedirs(tmp, exist_ok=True)
    body = s.get("say") or " ".join(x.strip() for x in (s.get("hook") or s["headline"], s.get("what", ""),
                                                        s.get("why", "")) if x)
    say = body.strip() + " " + SAY_END[lang]
    mp3 = os.path.join(tmp, "v.mp3")
    words = voice(say, lang, mp3)
    total = dur(mp3) + 0.6
    bg = background(s, lang, total, tmp)
    top = os.path.join(tmp, "top.png"); top_panel(s, lang, top)
    caps = captions(words, lang, total, tmp)
    accent_hex = COLOR.get(s.get("category", ""), "#ff3cac")
    masc = mascot_track(mp3, total, accent_hex, tmp)
    out = os.path.join(outdir, f"{s['id']}.mp4")
    accent = COLOR.get(s.get("category", ""), "#ff3cac").lstrip("#")
    vf = (f"[0:v]eq=brightness=-0.18:saturation=1.15[b];[b][1:v]overlay=0:0[o];"
          f"[o]drawbox=x=0:y=0:w=iw*t/{total:.2f}:h=14:color=0x{accent}:t=fill[p];"
          f"[3:v]format=rgba[c];[p][c]overlay=0:0:eof_action=pass[q];"
          f"[4:v]format=rgba,fps=30[m];[q][m]overlay=x=W-{MW}-30:y=H-{MW}-210+10*sin(2*PI*t*1.3):eof_action=pass[v]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", bg, "-loop", "1", "-i", top, "-i", mp3,
                    "-f", "concat", "-safe", "0", "-i", caps, "-f", "concat", "-safe", "0", "-i", masc,
                    "-filter_complex", vf, "-map", "[v]", "-map", "2:a", "-t", f"{total:.2f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-af", "apad", "-movflags", "+faststart", out],
                   check=True)
    subprocess.run(["rm", "-rf", tmp])
    return out
