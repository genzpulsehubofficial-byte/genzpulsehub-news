"""Phase 1: fetch -> rank -> rewrite (EN + ML) -> save. Runs every 15 min in GitHub Actions."""
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

sys.path.insert(0, os.path.dirname(__file__))
from ai import ask, AllFailed, ERRORS, MODELS  # noqa: E402
from sources import FEEDS, CATEGORY_WEIGHT, BLOCK_WORDS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
IST = timezone(timedelta(hours=5, minutes=30))
PER_RUN = int(os.environ.get("PER_RUN", "6"))
MAX_AGE_H = 12
KEEP_DAYS = 7

PROMPT = """You are the writer for "GenZ Pulse Hub", a 24/7 news channel for Indian Gen Z and teens (13+).
Rewrite the news below COMPLETELY in your own words. Never copy sentences from the source.
Use ONLY facts stated in the source. Do not add numbers, names, quotes or claims that are not there.
Stay neutral on politics. No opinions. No medical or financial promises. If the source is too thin to be sure, set "ok": false.

Return ONLY valid JSON, no markdown:
{{
 "ok": true,
 "category": one of ["headlines","jobs","money","tech","exams","trending","entertainment","health","sports","kerala"],
 "en": {{"headline": "max 12 words, punchy, no clickbait lies",
         "hook": "one line that makes a teen stop scrolling",
         "what": "2-3 short sentences: what happened",
         "why": "1-2 sentences: why it matters to a young Indian / what they should do",
         "tags": ["3-5 short hashtags without #"]}},
 "ml": {{"headline": "same in natural spoken Malayalam script. Translate everything into Malayalam; only brand names and tech words like UPI, app, AI, BGMI may stay in English",
         "hook": "...", "what": "...", "why": "...", "tags": ["..."]}}
}}

SOURCE ({source}):
TITLE: {title}
TEXT: {text}
"""


ML_FIX = """You are a senior Malayalam news sub-editor. Fix this Malayalam news text written for teenagers in Kerala.
1) Correct every spelling, grammar and chillu/conjunct error. Make it sound natural, like a Malayalam news anchor speaking to young people.
2) Keep the same facts. Do not add anything.
3) Also write "say": the spoken voice-over script (hook + what + why), written for the ear:
   - Everyday spoken Malayalam (not bookish). Short sentences, one idea each. Use full stops and commas
     wherever a news anchor would pause.
   - Prefer the common Malayalam word when one exists (job -> ജോലി, exam -> പരീക്ഷ, price -> വില).
   - When young Malayalis actually SAY the English word (phone, app, AI, UPI, Instagram, iPhone, cricket,
     brand/company names, acronyms), keep it in ENGLISH letters exactly, e.g. "പുതിയ iPhone ഇറങ്ങി".
     Never write those in Malayalam script (no ഐഫോൺ, no യുപിഐ) - the voice reads English letters naturally.
   - If a difficult English term is needed, say it in English and explain it in a few simple Malayalam words once.
   - Write numbers as digits (₹500, 2026, 10). Do not use symbols other than . , ? !
Return ONLY valid JSON: {{"headline": "...", "hook": "...", "what": "...", "why": "...", "say": "..."}}

TEXT:
{text}
"""


_DEP = set(chr(c) for c in list(range(0x0D3E, 0x0D4E)) + [0x0D57, 0x0D62, 0x0D63])


def ml_ok(ml):
    """Reject gibberish Malayalam: too much non-Malayalam, broken letters, replacement boxes."""
    txt = " ".join(ml.get(k, "") for k in ("headline", "what", "why"))
    if not txt.strip() or "\ufffd" in txt or "□" in txt:
        return False
    letters = [c for c in txt if c.isalpha() or 0x0D00 <= ord(c) <= 0x0D7F]
    mal = sum(1 for c in letters if 0x0D00 <= ord(c) <= 0x0D7F)
    if not letters or mal / len(letters) < 0.6:
        return False
    for w in txt.split():
        if w[0] in _DEP or "\u0d4d\u0d4d" in w:
            return False
    say = ml.get("say", "")
    if say:   # mostly Malayalam, English only for real loanwords/brands
        lat = sum(1 for c in say if "a" <= c.lower() <= "z")
        mls = sum(1 for c in say if 0x0D00 <= ord(c) <= 0x0D7F)
        if mls == 0 or lat / (lat + mls) > 0.3:
            return False
    return True


def fix_ml(ml):
    try:
        raw, _ = ask(ML_FIX.format(text=json.dumps({k: ml.get(k, "") for k in ("headline", "hook", "what", "why")},
                                                   ensure_ascii=False)))
        fx = parse_json(raw)
        if all(isinstance(fx.get(k), str) and fx[k].strip() for k in ("headline", "hook", "what", "why", "say")):
            ml.update({k: fx[k].strip() for k in ("headline", "hook", "what", "why", "say")})
    except Exception as e:
        print("ml proofread skipped:", str(e)[:80])
    return ml


_TW = None


def _tuned():
    """Category multipliers learned from real performance (growth/insights.py)."""
    global _TW
    if _TW is None:
        try:
            _TW = json.load(open(os.path.join(DATA, "weights.json")))
        except Exception:
            _TW = {}
    return _TW


def now():
    return datetime.now(timezone.utc)


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def words(t):
    return set(w for w in re.findall(r"[a-z0-9]{4,}", t.lower()))


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def discord(msg):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return
    try:
        requests.post(url, timeout=15, json={
            "content": f"@everyone {msg}"[:1900], "username": "GenZ Pulse Hub",
            "allowed_mentions": {"parse": ["everyone"]}})
    except Exception:
        pass


def fetch_all():
    items, bad = [], []
    for name, url, cat, region in FEEDS:
        try:
            r = requests.get(url, timeout=25, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0 Safari/537.36", "Accept-Language": "en-IN,en;q=0.9"})
            d = feedparser.parse(r.content)
            if not d.entries:
                bad.append(name)
            for e in d.entries[:25]:
                t = e.get("published_parsed") or e.get("updated_parsed")
                ts = datetime(*t[:6], tzinfo=timezone.utc) if t else now()
                if now() - ts > timedelta(hours=MAX_AGE_H):
                    continue
                title = clean(e.get("title"))
                src = name
                if " - " in title and "news.google" in url:  # Google News: "Title - Publisher"
                    title, src = title.rsplit(" - ", 1)
                items.append({"title": title, "text": clean(e.get("summary", ""))[:1500],
                              "link": e.get("link"), "source": src, "cat": cat,
                              "region": region, "ts": ts.isoformat()})
        except Exception:
            bad.append(name)
    return items, bad


def rank(items, seen):
    # cluster by title overlap -> count sources reporting the same story
    for it in items:
        it["w"] = words(it["title"])
    out = []
    for it in items:
        if it["link"] in seen or not it["title"]:
            continue
        low = (it["title"] + " " + it["text"]).lower()
        if any(b in low for b in BLOCK_WORDS):
            continue
        srcs = {o["source"] for o in items if len(it["w"] & o["w"]) >= max(3, len(it["w"]) // 2)}
        it["sources"] = len(srcs)
        age_h = (now() - datetime.fromisoformat(it["ts"])).total_seconds() / 3600
        tuned = _tuned().get("en", {}).get(it["cat"], 1.0) if it["region"] != "kl" else _tuned().get("ml", {}).get(it["cat"], 1.0)
        it["score"] = (1 + 0.6 * (it["sources"] - 1)) * CATEGORY_WEIGHT.get(it["cat"], 1) * tuned / (1 + age_h / 3)
        out.append(it)
    out.sort(key=lambda x: -x["score"])
    # pick top, avoid near-duplicates, keep category mix
    picked, per_cat = [], {}
    for it in out:
        if any(len(it["w"] & p["w"]) >= max(3, len(it["w"]) // 2) for p in picked):
            continue
        if per_cat.get(it["cat"], 0) >= 2:
            continue
        picked.append(it)
        per_cat[it["cat"]] = per_cat.get(it["cat"], 0) + 1
        if len(picked) >= PER_RUN:
            break
    return picked


def parse_json(txt):
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0) if m else txt)


def valid(s):
    try:
        for lang in ("en", "ml"):
            for k in ("headline", "hook", "what", "why"):
                if not s[lang][k] or len(s[lang][k]) < 8:
                    return False
        return s.get("ok", True)
    except Exception:
        return False


def copied(src_text, rewritten):
    """Reject if any 8-word run is copied from the source."""
    a = re.findall(r"\w+", src_text.lower())
    grams = {" ".join(a[i:i + 8]) for i in range(len(a) - 7)}
    b = re.findall(r"\w+", rewritten.lower())
    return any(" ".join(b[i:i + 8]) in grams for i in range(len(b) - 7))


def main():
    seen = load(os.path.join(DATA, "seen.json"), {})
    items, bad_feeds = fetch_all()
    picked = rank(items, seen)
    print(f"fetched {len(items)} items, picked {len(picked)}; dead feeds: {bad_feeds}")

    made, providers, all_failed = [], {}, 0
    for it in picked:
        try:
            raw, prov = ask(PROMPT.format(source=it["source"], title=it["title"], text=it["text"] or it["title"]))
        except AllFailed as e:
            all_failed += 1
            print("AI chain failed:", e)
            continue
        try:
            s = parse_json(raw)
        except Exception:
            print("bad json from", prov)
            continue
        seen[it["link"]] = now().isoformat()
        if not valid(s):
            continue
        en_text = " ".join(s["en"][k] for k in ("headline", "what", "why"))
        if copied(it["title"] + " " + it["text"], en_text):
            print("rejected: copied wording")
            continue
        s["ml"] = fix_ml(s["ml"])
        if not ml_ok(s["ml"]):
            s["ml"] = fix_ml(s["ml"])          # second attempt
        s["ml"]["ok"] = ml_ok(s["ml"])
        if not s["ml"]["ok"]:
            print("malayalam failed quality check; story kept English-only")
        s["ml"]["tags_en"] = s["en"].get("tags", [])
        sid = hashlib.sha1(it["link"].encode()).hexdigest()[:12]
        story = {
            "id": sid, "created": now().astimezone(IST).isoformat(timespec="seconds"),
            "category": s.get("category") or it["cat"], "region": it["region"],
            "breaking": it["sources"] >= 2 and it["cat"] == "headlines",
            "source": it["source"], "source_url": it["link"], "source_count": it["sources"],
            "provider": prov, "en": s["en"], "ml": s["ml"],
        }
        save(os.path.join(DATA, "stories", now().astimezone(IST).strftime("%Y-%m-%d"), f"{sid}.json"), story)
        made.append(story)
        providers[prov] = providers.get(prov, 0) + 1

    # latest feeds for stream + site
    for lang in ("en", "ml"):
        path = os.path.join(DATA, f"latest_{lang}.json")
        cur = load(path, [])
        new = [{"id": s["id"], "created": s["created"], "category": s["category"], "breaking": s["breaking"],
                "source": s["source"], "source_url": s["source_url"], **s[lang]}
               for s in made if lang == "en" or (s["region"] in ("in", "kl", "world") and s["ml"].get("ok", True))]
        save(path, (new + [c for c in cur if c["id"] not in {n["id"] for n in new}])[:40])

    # housekeeping: prune seen + old story folders
    cutoff = now() - timedelta(days=3)
    seen = {k: v for k, v in seen.items() if datetime.fromisoformat(v) > cutoff}
    save(os.path.join(DATA, "seen.json"), seen)
    sd = os.path.join(DATA, "stories")
    if os.path.isdir(sd):
        limit = (now().astimezone(IST) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
        for day in os.listdir(sd):
            if day < limit:
                shutil.rmtree(os.path.join(sd, day), ignore_errors=True)

    status = {"last_run": now().astimezone(IST).isoformat(timespec="seconds"), "fetched": len(items),
              "made": len(made), "providers": providers, "dead_feeds": bad_feeds, "ai_all_failed": all_failed, "ai_errors": ERRORS, "models": MODELS}
    save(os.path.join(DATA, "status.json"), status)
    print(json.dumps(status, indent=1))

    if picked and all_failed == len(picked):
        discord("🚨 **AI chain down** — every free AI provider failed this run. Stories paused until one recovers.")
    if len(bad_feeds) > len(FEEDS) // 2:
        discord(f"⚠️ **News sources failing**: {len(bad_feeds)}/{len(FEEDS)} feeds returned nothing.")


if __name__ == "__main__":
    main()
