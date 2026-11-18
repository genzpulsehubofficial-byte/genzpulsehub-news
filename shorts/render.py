"""Render vertical (1080x1920) news Shorts/Reels with AI voice. Free: edge-tts + Pillow + FFmpeg.

Usage: python shorts/render.py  -> renders the best unposted stories into out/shorts/<lang>/<id>.mp4
"""
import asyncio
import json
import os
import subprocess
import sys
import textwrap

import edge_tts
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "out", "shorts")
W, H = 1080, 1920
VOICE = {"en": "en-IN-NeerjaNeural", "ml": "ml-IN-SobhanaNeural"}
FONT = {"en": "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "ml": "/usr/share/fonts/truetype/noto/NotoSansMalayalam-Bold.ttf"}
FONT_REG = {"en": "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "ml": "/usr/share/fonts/truetype/noto/NotoSansMalayalam-Regular.ttf"}
COLOR = {"headlines": "#ff3cac", "jobs": "#ffd60a", "money": "#2ee59d", "tech": "#00c2ff", "exams": "#ff8a00",
         "trending": "#c77dff", "entertainment": "#ff5d8f", "health": "#7bdff2", "sports": "#80ed99", "kerala": "#00f5d4"}
CTA = {"en": ("Watch more on YouTube", "Full story: genzpulsehub.dpdns.org"),
       "ml": ("കൂടുതൽ YouTube-ൽ കാണുക", "മുഴുവൻ വാർത്ത: genzpulsehub.dpdns.org/ml")}
WHY = {"en": "WHY IT MATTERS TO YOU", "ml": "നിങ്ങളെ എങ്ങനെ ബാധിക്കും"}
PER_RUN = int(os.environ.get("SHORTS_PER_RUN", "1"))


def font(lang, size, bold=True):
    try:
        eng = ImageFont.Layout.RAQM if ImageFont.core.HAVE_RAQM else ImageFont.Layout.BASIC
        f = ImageFont.truetype((FONT if bold else FONT_REG)[lang], size, layout_engine=eng)
        if lang == "ml":
            f._ml = True
            f._en = ImageFont.truetype((FONT if bold else FONT_REG)["en"], size, layout_engine=eng)
        return f
    except Exception:
        return ImageFont.load_default()


def bg():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):                       # purple -> navy gradient
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(26 * (1 - t) + 5 * t), int(5 * (1 - t) + 33 * t), int(51 * (1 - t) + 61 * t)))
    return img


def _is_ml(w):
    return any("\u0d00" <= ch <= "\u0d7f" for ch in w)


def _wf(f, w):
    """Per-word font: Malayalam words use the Malayalam font, everything else the Latin font."""
    if getattr(f, "_ml", False) and not _is_ml(w):
        return f._en
    return f


def put(d, xy, text, f, fill):
    x, y = xy
    for w in text.split(" "):
        wf = _wf(f, w)
        d.text((x, y), w, font=wf, fill=fill)
        x += d.textlength(w + " ", font=wf)


def tlen(d, text, f):
    return sum(d.textlength(w + " ", font=_wf(f, w)) for w in text.split(" "))


def wrap(d, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tlen(d, t, f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def frame(lang, s, scene):
    img = bg()
    d = ImageDraw.Draw(img)
    c = COLOR.get(s["category"], "#00f5d4")
    # brand bar
    d.text((60, 70), "GenZ Pulse Hub", font=font("en", 52), fill="#ffd60a")
    d.rounded_rectangle((60, 150, 60 + 30 + d.textlength(s["category"].upper(), font=font("en", 34)), 205), 12, fill=c)
    d.text((75, 155), s["category"].upper(), font=font("en", 34), fill="#140c28")
    # pulse line
    pts = [(0, 1500), (380, 1500), (430, 1420), (500, 1600), (560, 1460), (600, 1500), (W, 1500)]
    d.line(pts, fill="#00f5d4", width=8, joint="curve")
    y = 300
    if scene == "hook":
        for ln in wrap(d, s["headline"], font(lang, 78), W - 120)[:6]:
            put(d, (60, y), ln, font(lang, 78), "#ffffff"); y += 100
        y += 30
        for ln in wrap(d, s["hook"], font(lang, 50, False), W - 120)[:5]:
            put(d, (60, y), ln, font(lang, 50, False), "#00f5d4"); y += 68
    elif scene == "what":
        for ln in wrap(d, s["what"], font(lang, 54, False), W - 120)[:14]:
            put(d, (60, y), ln, font(lang, 54, False), "#ffffff"); y += 74
    elif scene == "why":
        put(d, (60, y), WHY[lang], font(lang, 46), "#ffd60a"); y += 90
        for ln in wrap(d, s["why"], font(lang, 58), W - 120)[:12]:
            put(d, (60, y), ln, font(lang, 58), "#ffffff"); y += 80
    else:  # cta
        y = 700
        for t, f, col in ((CTA[lang][0], font(lang, 64), "#ffffff"), (CTA[lang][1], font(lang, 40, False), "#00f5d4")):
            for ln in wrap(d, t, f, W - 120):
                put(d, ((W - tlen(d, ln, f)) / 2, y), ln, f, col); y += 90
        d.text((60, 1650), f"Source: {s['source']}", font=font("en", 30, False), fill="#bbbbbb")
    d.text((60, H - 120), f"Source: {s['source']}  ·  AI-assisted rewrite", font=font("en", 28, False), fill="#9a8fb8")
    return img


async def _edge(text, voice, path):
    await edge_tts.Communicate(text, voice, rate="+8%").save(path)


def tts_file(text, lang, path):
    """Microsoft neural voice first; Google TTS as free fallback."""
    try:
        asyncio.run(_edge(text, VOICE[lang], path))
        if os.path.getsize(path) > 1000:
            return "edge"
    except Exception as e:
        print("edge-tts failed, using gTTS:", str(e)[:80])
    from gtts import gTTS
    gTTS(text, lang=lang, tld="co.in" if lang == "en" else "com").save(path)
    return "gtts"


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 3)


def render(lang, s, outdir):
    os.makedirs(outdir, exist_ok=True)
    tmp = os.path.join(outdir, "tmp_" + s["id"])
    os.makedirs(tmp, exist_ok=True)
    scenes = [("hook", f"{s['headline']}. {s['hook']}"), ("what", s["what"]), ("why", s["why"]),
              ("cta", CTA[lang][0] + ".")]
    parts = []
    for i, (name, text) in enumerate(scenes):
        a, im, v = f"{tmp}/{i}.mp3", f"{tmp}/{i}.png", f"{tmp}/{i}.mp4"
        tts_file(text, lang, a)
        frame(lang, s, name).save(im)
        d = dur(a) + 0.35
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", im, "-i", a, "-t", f"{d:.2f}",
                        "-vf", "zoompan=z='min(zoom+0.0006,1.06)':d=1:s=1080x1920:fps=30,format=yuv420p",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-ar", "44100",
                        "-af", "apad", "-shortest", v], check=True)
        parts.append(v)
    lst = f"{tmp}/list.txt"
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    out = os.path.join(outdir, f"{s['id']}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", out], check=True)
    subprocess.run(["rm", "-rf", tmp])
    return out


def pick(lang, posted):
    items = json.load(open(os.path.join(DATA, f"latest_{lang}.json")))
    if lang == "en":
        items = [i for i in items if i.get("category") != "kerala"]
    pri = {"breaking": 3}
    items.sort(key=lambda i: (-(i.get("breaking") * 3), i["created"]), reverse=False)
    return [i for i in sorted(items, key=lambda i: i["created"], reverse=True) if i["id"] not in posted][:PER_RUN]


def main():
    posted = json.load(open(os.path.join(DATA, "posted.json"))) if os.path.exists(os.path.join(DATA, "posted.json")) else {}
    made = []
    for lang in ("en", "ml"):
        for s in pick(lang, posted.get(lang, {})):
            try:
                p = render(lang, s, os.path.join(OUT, lang))
                made.append({"lang": lang, "id": s["id"], "path": p, "story": s})
                print("rendered", lang, s["id"], p)
            except Exception as e:
                print("render failed", lang, s["id"], e, file=sys.stderr)
    json.dump(made, open(os.path.join(OUT, "made.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    main()
