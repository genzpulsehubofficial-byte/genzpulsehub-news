"""Builds the static website (EN at /, ML at /ml) from data/ into public/."""
import glob
import html
import json
import os
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "public")
def _site():
    if os.environ.get("SITE_URL"):
        return os.environ["SITE_URL"]
    try:
        import urllib.request
        if urllib.request.urlopen("https://genzpulsehub.dpdns.org/", timeout=10).status == 200:
            return "https://genzpulsehub.dpdns.org"
    except Exception:
        pass
    return "https://genzpulsehub.pages.dev"


SITE = _site()
ADS_API = os.environ.get("ADS_API", "https://genzpulsehub-ads.genzpulsehub-official.workers.dev")
YT = {"en": "UCrpJDlRnVJyC4EguHKJxHKg", "ml": "UC3dW_vEz432vsb6uqlCVHAw"}
IG = {"en": "genzpulsehubnews", "ml": "genzpulsehubmalayalam"}
FB = {"en": "61596319547043", "ml": "61596419862358"}
CAT = {
    "en": {"headlines": "Headlines", "jobs": "Jobs", "money": "Money", "tech": "Tech & AI", "exams": "Exams",
           "trending": "Trending", "entertainment": "Entertainment", "health": "Health", "sports": "Sports & Gaming",
           "kerala": "Kerala"},
    "ml": {"headlines": "പ്രധാന വാർത്ത", "jobs": "ജോലി", "money": "പണം", "tech": "ടെക് & AI", "exams": "പരീക്ഷ",
           "trending": "ട്രെൻഡിംഗ്", "entertainment": "വിനോദം", "health": "ആരോഗ്യം", "sports": "സ്പോർട്സ്",
           "kerala": "കേരളം"},
}
COLOR = {"headlines": "#ff3cac", "jobs": "#ffd60a", "money": "#2ee59d", "tech": "#00c2ff", "exams": "#ff8a00",
         "trending": "#c77dff", "entertainment": "#ff5d8f", "health": "#7bdff2", "sports": "#80ed99", "kerala": "#00f5d4"}
LIVE_ON = os.environ.get("STREAM_LIVE", "0") == "1"   # set to 1 once the 24/7 stream runs
T = {
    "en": {"live": "LIVE 24/7", "why": "Why it matters to you", "soon": "🔴 24/7 Live news: coming soon",
           "soon_sub": "Subscribe now so you're notified the moment we go live. Meanwhile: daily Shorts + all stories below.",
           "subscribe": "Subscribe on YouTube", "source": "Source", "latest": "Latest",
           "watch": "Watch the live stream", "switch": "മലയാളം", "switch_href": "/ml/", "tag": "What happened + why it matters to YOU",
           "advertise": "Advertise with us", "home": "/", "about": "News for your generation, written fresh from credited sources. Facts only from the source."},
    "ml": {"live": "LIVE 24/7", "why": "നിങ്ങളെ എങ്ങനെ ബാധിക്കും", "soon": "🔴 24/7 തത്സമയ വാർത്ത: ഉടൻ വരുന്നു",
           "soon_sub": "ലൈവ് തുടങ്ങുമ്പോൾ അറിയാൻ ഇപ്പോൾ സബ്സ്ക്രൈബ് ചെയ്യൂ. അതുവരെ: ദിവസവും Shorts + താഴെ എല്ലാ വാർത്തകളും.",
           "subscribe": "YouTube-ൽ സബ്സ്ക്രൈബ് ചെയ്യൂ", "source": "ഉറവിടം", "latest": "പുതിയ വാർത്തകൾ",
           "watch": "ലൈവ് കാണുക", "switch": "English", "switch_href": "/", "tag": "എന്ത് സംഭവിച്ചു + നിങ്ങളെ എങ്ങനെ ബാധിക്കും",
           "advertise": "പരസ്യം നൽകാൻ", "home": "/ml/", "about": "നിങ്ങളുടെ തലമുറയ്ക്കുള്ള വാർത്ത, ഉറവിടങ്ങളിൽ നിന്ന് പുതുതായി എഴുതിയത്. ഉറവിടത്തിലെ വസ്തുതകൾ മാത്രം."},
}

CSS = """
*{box-sizing:border-box}body{margin:0;font-family:'Inter','Noto Sans Malayalam',system-ui,sans-serif;background:#0b0618;color:#f3f0ff;line-height:1.55}
a{color:inherit}header{position:sticky;top:0;z-index:5;background:linear-gradient(90deg,#1a0533,#05213d);padding:12px 18px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a1a4a}
.logo{font-weight:900;font-size:22px;background:linear-gradient(90deg,#ff3cac,#ffd60a);-webkit-background-clip:text;color:transparent;text-decoration:none}
.live{background:#ff1e56;color:#fff;font-size:12px;font-weight:800;padding:3px 8px;border-radius:4px;animation:p 1.6s infinite}@keyframes p{50%{opacity:.55}}
nav{margin-left:auto;display:flex;gap:14px;font-size:14px}nav a{text-decoration:none;opacity:.85}
main{max-width:1100px;margin:auto;padding:18px}.tag{opacity:.75;margin:0 0 14px}
.player{aspect-ratio:16/9;width:100%;border:0;border-radius:14px;background:#000}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;margin-top:18px}
.card{background:#140c28;border:1px solid #2a1a4a;border-radius:14px;padding:16px;text-decoration:none;display:block;transition:.15s}.card:hover{border-color:#00f5d4;transform:translateY(-2px)}
.cat{font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}.card h2{font-size:18px;margin:6px 0}.card p{margin:0;opacity:.8;font-size:14px}
.brk{background:#ff1e56;color:#fff;font-size:10px;padding:2px 6px;border-radius:3px;margin-left:6px}
article{max-width:720px;margin:auto}article h1{font-size:30px;line-height:1.2;margin:8px 0}.hook{font-size:19px;color:#00f5d4;font-weight:600}
.why{background:#1d1038;border-left:4px solid #ffd60a;padding:12px 14px;border-radius:8px;margin:16px 0}.src{font-size:13px;opacity:.7}
.adslot{border:1px dashed #3a2a5a;border-radius:12px;padding:14px;text-align:center;font-size:13px;opacity:.7;margin:18px 0}
.tags span{display:inline-block;background:#221540;border-radius:20px;padding:3px 10px;margin:3px;font-size:12px}
footer{text-align:center;padding:30px 12px;font-size:13px;opacity:.65}
"""


def esc(s):
    return html.escape(str(s or ""))


def page(lang, title, desc, body, path, og_type="website"):
    t = T[lang]
    alt = ("/ml" + path) if lang == "en" else path.replace("/ml", "", 1) or "/"
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}"><link rel="canonical" href="{SITE}{path}">
<link rel="alternate" hreflang="{'ml' if lang=='en' else 'en'}" href="{SITE}{alt}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{og_type}"><meta property="og:url" content="{SITE}{path}"><meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image"><link rel="icon" href="/favicon.svg">
<link rel="alternate" type="application/rss+xml" href="{SITE}{t['home']}rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&family=Noto+Sans+Malayalam:wght@400;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<header><a class="logo" href="{t['home']}">GenZ Pulse Hub</a><span class="live">● {t['live'] if LIVE_ON else 'LIVE soon'}</span>
<nav><a href="{t['switch_href']}">{t['switch']}</a><a href="https://www.youtube.com/channel/{YT[lang]}/live">YouTube</a>
<a href="https://instagram.com/{IG[lang]}">Instagram</a><a href="/advertise/">{t['advertise']}</a></nav></header>
<main>{body}</main>
<footer>© GenZ Pulse Hub · {t['about']}</footer>
<script src="/ads.js" defer></script></body></html>"""


def card(s, lang):
    base = "/ml" if lang == "ml" else ""
    c = s.get("category", "headlines")
    brk = '<span class="brk">BREAKING</span>' if s.get("breaking") else ""
    return (f'<a class="card" href="{base}/news/{s["id"]}/"><span class="cat" style="color:{COLOR.get(c,"#fff")}">'
            f'{esc(CAT[lang].get(c, c))}</span>{brk}<h2>{esc(s["headline"])}</h2><p>{esc(s["hook"])}</p></a>')


def write(path, content):
    full = os.path.join(OUT, path.strip("/"), "index.html") if not path.endswith((".xml", ".txt", ".svg", ".json", ".js")) \
        else os.path.join(OUT, path.strip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    stories = []
    for p in sorted(glob.glob(os.path.join(DATA, "stories", "*", "*.json")), reverse=True):
        try:
            stories.append(json.load(open(p)))
        except Exception:
            pass
    stories.sort(key=lambda s: s["created"], reverse=True)
    urls = []
    for lang in ("en", "ml"):
        t, base = T[lang], ("/ml" if lang == "ml" else "")
        items = [{**s[lang], "id": s["id"], "category": s["category"], "breaking": s["breaking"],
                  "created": s["created"], "source": s["source"], "source_url": s["source_url"]} for s in stories]
        live = (f'<div class="player soon" style="display:flex;flex-direction:column;align-items:center;justify-content:center;'
                f'gap:14px;text-align:center;background:linear-gradient(135deg,#1b1035,#0b0b14);border-radius:14px;padding:28px">'
                f'<b style="font-size:1.4em">{t["soon"]}</b><span>{t["soon_sub"]}</span>'
                f'<a href="https://www.youtube.com/channel/{YT[lang]}?sub_confirmation=1" target="_blank" rel="noopener" '
                f'style="background:#e10600;color:#fff;padding:12px 22px;border-radius:999px;font-weight:700;text-decoration:none">'
                f'{t["subscribe"]}</a></div>') if not LIVE_ON else (f'<iframe class="player" src="https://www.youtube.com/embed/live_stream?channel={YT[lang]}&autoplay=1&mute=1" '
                f'title="{t["watch"]}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen loading="lazy"></iframe>')
        home = (f'<p class="tag">{t["tag"]}</p>{live}<div class="adslot" data-slot="site_banner" data-lang="{lang}"></div>'
                f'<h2>{t["latest"]}</h2><div class="grid">{"".join(card(s, lang) for s in items[:60])}</div>')
        write(f"{base}/", page(lang, "GenZ Pulse Hub — " + t["tag"], t["tag"], home, f"{base}/"))
        urls.append(f"{base}/")
        for s in items:
            path = f"{base}/news/{s['id']}/"
            c = s["category"]
            body = (f'<article><span class="cat" style="color:{COLOR.get(c,"#fff")}">{esc(CAT[lang].get(c, c))}</span>'
                    f'<h1>{esc(s["headline"])}</h1><p class="hook">{esc(s["hook"])}</p><p>{esc(s["what"])}</p>'
                    f'<div class="why"><b>{t["why"]}</b><br>{esc(s["why"])}</div>'
                    f'<div class="adslot" data-slot="site_banner" data-lang="{lang}"></div>'
                    f'<div class="tags">{"".join("<span>#"+esc(x)+"</span>" for x in (s.get("tags") or [])[:6])}</div>'
                    f'<p class="src">{t["source"]}: <a href="{esc(s["source_url"])}" rel="nofollow noopener" target="_blank">{esc(s["source"])}</a> · {esc(s["created"][:16].replace("T"," "))} IST</p>'
                    f'<h3>{t["watch"]}</h3>{live}</article>')
            ld = json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", "headline": s["headline"][:110],
                             "datePublished": s["created"], "inLanguage": lang,
                             "publisher": {"@type": "Organization", "name": "GenZ Pulse Hub"},
                             "isBasedOn": s["source_url"]}, ensure_ascii=False)
            write(path, page(lang, s["headline"] + " | GenZ Pulse Hub", s["hook"],
                             body + f'<script type="application/ld+json">{ld}</script>', path, "article"))
            urls.append(path)
        rss = "".join(f"<item><title>{esc(s['headline'])}</title><link>{SITE}{base}/news/{s['id']}/</link>"
                      f"<guid>{SITE}{base}/news/{s['id']}/</guid><description>{esc(s['hook'])}</description></item>"
                      for s in items[:50])
        write(f"{base}/rss.xml", f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>GenZ Pulse Hub {lang.upper()}</title>'
                                 f'<link>{SITE}{base}/</link><description>{esc(t["tag"])}</description>{rss}</channel></rss>')
    write("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{SITE}{u}</loc></url>" for u in urls) + "</urlset>")
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    write("/favicon.svg", '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1a0533"/>'
          '<text x="32" y="42" font-size="30" font-weight="900" text-anchor="middle" fill="#ffd60a" font-family="Arial">GZ</text></svg>')
    # static files (advertise pages, ads.js) with the ads API url filled in
    static = os.path.join(ROOT, "site", "static")
    for dirpath, _, files in os.walk(static):
        for fn in files:
            src = os.path.join(dirpath, fn)
            dst = os.path.join(OUT, os.path.relpath(src, static))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src) as f:
                txt = f.read().replace("__ADS_API__", ADS_API)
            with open(dst, "w") as f:
                f.write(txt)
    print(f"built {len(urls)} pages from {len(stories)} stories at {datetime.now():%H:%M}")


if __name__ == "__main__":
    main()
