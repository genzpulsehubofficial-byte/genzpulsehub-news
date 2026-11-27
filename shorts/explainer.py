"""Explainer style (cinematic storytelling): full-bleed dark-graded footage per beat with a slow push-in,
big condensed chapter title with one accent word + underline, short subtitle phrases with the key word
highlighted, small SOURCE chip, brand + category on the cover. No mascot, no boxes.
Works for vertical shorts (1080x1920) and the 16:9 live stream (1920x1080)."""
import os
import re
import subprocess
import urllib.request

from PIL import Image, ImageDraw, ImageFont

from render import COLOR, dur, font, put, tlen
import render_v2 as v2

COND = "/tmp/gph_Oswald.ttf"
SAY_END = {"en": "Follow for more stories like this.", "ml": "ഇതുപോലുള്ള കൂടുതൽ കഥകൾക്ക് ഫോളോ ചെയ്യൂ."}
END_T = {"en": ("FOLLOW FOR", "MORE"), "ml": ("FOLLOW FOR", "MORE")}


def cond(size):
    if not os.path.exists(COND):
        try:
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/oswald/Oswald%5Bwght%5D.ttf", COND)
        except Exception:
            pass
    try:
        f = ImageFont.truetype(COND, size)
        try:
            f.set_variation_by_name("Bold")
        except Exception:
            pass
        return f
    except Exception:
        return font("en", size)


def _beats(s, lang):
    b = s.get("beats")
    if b and b.get("beats"):
        return b["cover"], b.get("cover_accent", ""), [{"title": x["title"], "accent": x.get("accent", ""),
                                                         "query": x["query"], "say": x[lang]} for x in b["beats"]]
    # older stories: build beats from the existing script
    say = s.get("say") or " ".join(x for x in (s.get("hook"), s.get("what"), s.get("why")) if x)
    sents = [x.strip() for x in re.findall(r"[^.?!।]+[.?!।]?", say) if x.strip()]
    titles = ["WHAT HAPPENED", "THE DETAILS", "BUT WAIT...", "WHY IT MATTERS", "WHAT NEXT"]
    n = min(5, max(2, len(sents) // 2))
    per = -(-len(sents) // n)
    q = (s.get("tags_en") or s.get("tags") or ["news"])
    beats = [{"title": titles[i] if i else "", "accent": titles[i].split()[-1] if i else "",
              "query": re.sub(r"(?<=[a-z])(?=[A-Z])", " ", q[i % len(q)]), "say": " ".join(sents[i * per:(i + 1) * per])}
             for i in range(n) if sents[i * per:(i + 1) * per]]
    return "", "", beats


def _shadow_text(d, xy, text, f, fill):
    for dx, dy in ((0, 4), (2, 5), (-2, 5)):
        d.text((xy[0] + dx, xy[1] + dy), text, font=f, fill=(0, 0, 0, 150))
    d.text(xy, text, font=f, fill=fill)


def title_png(title, accent, col, W, H, path, cover=False, cat="", src=""):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    vertical = H > W
    if title:
        size = (118 if cover else 104) if vertical else 92
        f = cond(size)
        words, lines, cur = title.split(), [], ""
        maxw = W * (0.84 if vertical else 0.7)
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) > maxw and cur:
                lines.append(cur); cur = w
            else:
                cur = t
        lines.append(cur)
        lh = int(size * 1.08)
        y0 = int(H * (0.52 if cover else 0.27)) - len(lines) * lh // 2 if vertical else int(H * 0.30) - len(lines) * lh // 2
        acc = accent.upper().strip(".?!,")
        for i, ln in enumerate(lines):
            x = (W - d.textlength(ln, font=f)) / 2 if not cover else W * 0.08
            for w in ln.split(" "):
                c = col if acc and w.upper().strip(".?!,") == acc else "white"
                _shadow_text(d, (x, y0 + i * lh), w, f, c)
                x += d.textlength(w + " ", font=f)
        ly = y0 + len(lines) * lh + 12
        if cover:
            d.rectangle([W * 0.08, y0 - 40, W * 0.08 + 70, y0 - 32], fill=col)
        else:   # wavy underline
            cx, half = W / 2, min(W * 0.32, 300)
            pts = [(cx - half + i * 6, ly + 6 * __import__("math").sin(i / 3)) for i in range(int(2 * half / 6))]
            d.line(pts, fill=col, width=5)
    sm = cond(30 if vertical else 26)
    if cover:   # brand top-left, category pill top-right
        d.ellipse([60, 80, 96, 116], outline="white", width=3)
        d.text((112, 80), "GENZ PULSE HUB", font=sm, fill="white")
        if cat:
            tw = d.textlength(cat, font=sm)
            d.rounded_rectangle([W - 90 - tw, 76, W - 60, 122], 23, outline=col, width=3)
            d.text((W - 75 - tw, 80), cat, font=sm, fill=col)
        d.text((W * 0.08, H * 0.52 + 200 if vertical else H * 0.72), "@genzpulsehubnews", font=sm, fill=(255, 255, 255, 220))
    if src:
        tag = "SOURCE  " + src.upper()[:40]
        tf = cond(22 if vertical else 20)
        tw = d.textlength(tag, font=tf)
        y = int(H * (0.585 if vertical else 0.80))
        d.rounded_rectangle([(W - tw) / 2 - 14, y, (W + tw) / 2 + 14, y + 36], 6, fill=(10, 14, 20, 200), outline=(120, 220, 230, 160))
        d.text(((W - tw) / 2, y + 4), tag, font=tf, fill=(200, 240, 245))
    img.save(path)


def sub_png(words, lang, col, W, H, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    if words:
        vertical = H > W
        f = font(lang, 58 if vertical else 50)
        key = max(range(len(words)), key=lambda i: len(words[i]))
        line = " ".join(words)
        x = (W - tlen(d, line, f)) / 2
        y = int(H * (0.63 if vertical else 0.86))
        for i, w in enumerate(words):
            for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (0, 5)):
                put(d, (x + dx, y + dy), w, f, "black")
            put(d, (x, y), w, f, col if i == key and len(words) > 1 else "white")
            x += tlen(d, w + " ", f)
    img.save(path)


def end_png(lang, col, W, H, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 120)); d = ImageDraw.Draw(img)
    f = cond(130 if H > W else 110)
    a, b = END_T[lang]
    for i, (t, c) in enumerate(((a, "white"), (b, col))):
        _shadow_text(d, ((W - d.textlength(t, font=f)) / 2, H * 0.40 + i * 150), t, f, c)
    sm = cond(40)
    t = "@genzpulsehubnews" if lang == "en" else "@genzpulsehubmalayalam"
    d.text(((W - d.textlength(t, font=sm)) / 2, H * 0.40 + 330), t, font=sm, fill="white")
    img.save(path)


def footage(q, need, W, H, tmp, i, fallback):
    clips = v2.pixabay_clips([q, fallback], min(need, 7), os.path.join(tmp)) if v2.PIXABAY else []
    out = os.path.join(tmp, f"scene{i}.mp4")
    grade = (f"scale={int(W*1.12)}:{int(H*1.12)}:force_original_aspect_ratio=increase,"
             f"crop={int(W*1.12)}:{int(H*1.12)},fps=30,"
             f"scale=w='{W}+{int(W*0.12)}*t/{need:.2f}':h=-2:eval=frame,crop={W}:{H},setsar=1,"
             f"eq=brightness=-0.10:contrast=1.08:saturation=0.85,vignette=PI/4.2")
    src = clips[0] if clips else None
    if src:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", src]
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
               f"gradients=s={W}x{H}:c0=0x05080c:c1=0x10202a:c2=0x050a10:n=3:speed=0.01:r=30"]
    try:
        subprocess.run(cmd + ["-t", f"{need:.2f}", "-an", "-vf", grade, "-c:v", "libx264", "-preset", "veryfast",
                              "-crf", "24", "-pix_fmt", "yuv420p", out], check=True)
    except subprocess.CalledProcessError:   # simple grade if the push-in filter fails
        subprocess.run(cmd + ["-t", f"{need:.2f}", "-an", "-vf",
                              f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1,"
                              f"eq=brightness=-0.10:saturation=0.85,vignette=PI/4.2",
                              "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", out], check=True)
    return out


def scene(i, b, lang, s, col, W, H, tmp, cover=None, end=False):
    say = b["say"].strip() + ((" " + SAY_END[lang]) if end else "")
    mp3 = os.path.join(tmp, f"v{i}.mp3")
    words = v2.voice(say, lang, mp3)
    total = dur(mp3) + 0.35
    bg = footage(b["query"], total, W, H, tmp, i, v2.FALLBACK_Q.get(s.get("category", ""), "city night"))
    tp = os.path.join(tmp, f"t{i}.png")
    if cover:
        title_png(cover[0], cover[1], col, W, H, tp, cover=True, cat=(s.get("category") or "news").upper(), src=s.get("source", ""))
    else:
        title_png(b["title"], b["accent"], col, W, H, tp, src=s.get("source", "") if i == 1 else "")
    # subtitle phrases (3 words), timed to the voice
    lst, t, n = ["ffconcat version 1.0"], 0.0, 0
    blank = os.path.join(tmp, "blank.png")
    if not os.path.exists(blank):
        Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    groups = [words[k:k + 3] for k in range(0, len(words), 3)]
    for gi, g in enumerate(groups):
        a = g[0][0]; e = groups[gi + 1][0][0] if gi + 1 < len(groups) else total
        if a > t + 0.01:
            lst += [f"file '{blank}'", f"duration {a - t:.3f}"]
        p = os.path.join(tmp, f"s{i}_{n}.png"); n += 1
        sub_png([w for _, _, w in g], lang, col, W, H, p)
        lst += [f"file '{p}'", f"duration {max(e - a, 0.05):.3f}"]; t = e
    lst += [f"file '{blank}'", "duration 0.1", f"file '{blank}'"]
    caps = os.path.join(tmp, f"caps{i}.txt"); open(caps, "w").write("\n".join(lst) + "\n")
    extra, fc = [], (f"[1:v]format=rgba,fade=in:st=0:d=0.4:alpha=1[ti];[0:v][ti]overlay=0:0[a];"
                     f"[3:v]format=rgba[c];[a][c]overlay=0:0:eof_action=pass[b]")
    last = "[b]"
    if end:
        ep = os.path.join(tmp, "end.png"); end_png(lang, col, W, H, ep)
        extra = ["-loop", "1", "-i", ep]
        st = max(total - 2.6, 0.5)
        fc += f";[4:v]format=rgba,fade=in:st={st:.2f}:d=0.4:alpha=1[e];[b][e]overlay=0:0:enable='gte(t,{st:.2f})'[z]"
        last = "[z]"
    out = os.path.join(tmp, f"sc{i}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", bg, "-loop", "1", "-i", tp, "-i", mp3,
                    "-f", "concat", "-safe", "0", "-i", caps] + extra +
                   ["-filter_complex", fc + f";{last}fade=in:st=0:d=0.25[v]", "-map", "[v]", "-map", "2:a",
                    "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                    "-r", "30", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-af", "apad", out], check=True)
    return out


def build(lang, s, out, W=1080, H=1920, tmp=None):
    tmp = os.path.abspath(tmp or (out + "_x")); os.makedirs(tmp, exist_ok=True)
    col = COLOR.get(s.get("category", ""), "#4ee0d0")
    cover, cacc, beats = _beats(s, lang)
    if not beats:
        raise RuntimeError("no beats")
    hook = cover or (s.get("headline") or "").upper()
    parts = []
    for i, b in enumerate(beats):
        parts.append(scene(i, b, lang, s, col, W, H, tmp,
                           cover=(hook if cover else "", cacc) if i == 0 else None, end=(i == len(beats) - 1)))
    lst = os.path.join(tmp, "all.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    "-movflags", "+faststart", out], check=True)
    subprocess.run(["rm", "-rf", tmp])
    return out


def render(lang, s, outdir):
    os.makedirs(outdir, exist_ok=True)
    return build(lang, s, os.path.join(outdir, f"{s['id']}.mp4"))
