"""Daily analytics + watchdog + auto-optimisation (GitHub Actions, no Claude).

1. Followers/subscribers per account (IG, FB, YouTube) -> data/analytics/followers.json (history)
2. Per-post performance for recent Reels/Shorts -> reach/views by category & language
3. Auto-tunes data/weights.json (category multipliers 0.6-1.6, per language) from what performs
4. Watchdog: workflow health, site up, tokens valid -> Discord
5. Daily Discord summary; full weekly report on Mondays (IST)
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shorts"))
import requests  # noqa: E402
from publish import G, IG_IDS, discord, env, meta_pages, yt_token  # noqa: E402

DATA = os.path.join(ROOT, "data")
AN = os.path.join(DATA, "analytics"); os.makedirs(AN, exist_ok=True)
IST = timezone(timedelta(hours=5, minutes=30))
YT_CH = {"en": "UCrpJDlRnVJyC4EguHKJxHKg", "ml": "UC3dW_vEz432vsb6uqlCVHAw"}
REPO = "genzpulsehubofficial-byte/genzpulsehub-news"


def jget(url, **kw):
    try:
        return requests.get(url, timeout=30, **kw).json()
    except Exception as e:
        return {"error": str(e)}


def followers():
    out = {}
    tok = env("META_TOKEN")
    for lang, p in meta_pages().items():
        fb = jget(f"{G}/{p['id']}", params={"fields": "followers_count,fan_count", "access_token": p["access_token"]})
        ig_id = (p.get("instagram_business_account") or {}).get("id") or IG_IDS.get(lang)
        ig = jget(f"{G}/{ig_id}", params={"fields": "followers_count,media_count", "access_token": p.get("ig_token") or tok}) if ig_id else {}
        out[f"fb_{lang}"] = fb.get("followers_count") or fb.get("fan_count")
        out[f"ig_{lang}"] = ig.get("followers_count")
    for lang in ("en", "ml"):
        t = yt_token(lang)
        if t:
            r = jget("https://www.googleapis.com/youtube/v3/channels", params={"part": "statistics", "mine": "true"},
                     headers={"Authorization": f"Bearer {t}"})
            st = (r.get("items") or [{}])[0].get("statistics", {})
            out[f"yt_{lang}"] = int(st.get("subscriberCount", 0) or 0)
            out[f"ytviews_{lang}"] = int(st.get("viewCount", 0) or 0)
    return out


def post_perf():
    """Reach/views per recent post, grouped by (lang, category)."""
    posted = json.load(open(os.path.join(DATA, "posted.json"))) if os.path.exists(os.path.join(DATA, "posted.json")) else {}
    cats = {}
    for lang in ("en", "ml"):
        try:
            for s in json.load(open(os.path.join(DATA, f"latest_{lang}.json"))):
                cats[(lang, s["id"])] = s.get("category", "headlines")
        except Exception:
            pass
    pages = meta_pages()
    tok = env("META_TOKEN")
    perf = {}
    for lang, items in posted.items():
        p = pages.get(lang) or {}
        for sid, r in list(items.items())[-60:]:
            score = 0
            ig = str(r.get("instagram", ""))
            if ig.startswith("ig:"):
                j = jget(f"{G}/{ig[3:]}/insights", params={"metric": "reach,saved,shares", "access_token": p.get("ig_token") or tok})
                vals = {d["name"]: (d.get("values") or [{}])[0].get("value", 0) for d in j.get("data", [])}
                score += vals.get("reach", 0) + 5 * vals.get("saved", 0) + 5 * vals.get("shares", 0)
            yt = str(r.get("youtube", ""))
            if "shorts/" in yt and yt_token(lang):
                vid = yt.rsplit("/", 1)[-1]
                j = jget("https://www.googleapis.com/youtube/v3/videos", params={"part": "statistics", "id": vid},
                         headers={"Authorization": f"Bearer {yt_token(lang)}"})
                st = (j.get("items") or [{}])[0].get("statistics", {})
                score += int(st.get("viewCount", 0) or 0)
            cat = cats.get((lang, sid))
            if cat:
                perf.setdefault(lang, {}).setdefault(cat, []).append(score)
    return perf


def tune(perf):
    """Categories that beat the average get more airtime; laggards less. Gentle steps, bounded."""
    wp = os.path.join(DATA, "weights.json")
    w = json.load(open(wp)) if os.path.exists(wp) else {}
    changes = []
    for lang, cats in perf.items():
        avg = {c: sum(v) / len(v) for c, v in cats.items() if len(v) >= 3}
        if len(avg) < 3:
            continue
        overall = sum(avg.values()) / len(avg) or 1
        for c, a in avg.items():
            old = w.get(lang, {}).get(c, 1.0)
            target = max(0.6, min(1.6, a / overall))
            new = round(old + 0.25 * (target - old), 3)
            w.setdefault(lang, {})[c] = new
            if abs(new - old) >= 0.05:
                changes.append(f"{lang}:{c} {old}->{new}")
    json.dump(w, open(wp, "w"), indent=1)
    return changes


def watchdog():
    issues = []
    tok = env("GITHUB_TOKEN")
    h = {"Authorization": f"Bearer {tok}"} if tok else {}
    for wf, max_h in (("news.yml", 1), ("shorts.yml", 2), ("mailer.yml", 2)):
        r = jget(f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/runs", params={"per_page": 5}, headers=h)
        runs = r.get("workflow_runs", [])
        ok = [x for x in runs if x.get("conclusion") == "success"]
        if not ok:
            issues.append(f"{wf}: no recent successful run")
        else:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(ok[0]["updated_at"].replace("Z", "+00:00"))).total_seconds() / 3600
            if age > max_h:
                issues.append(f"{wf}: last success {age:.0f}h ago")
    for url in ("https://genzpulsehub.pages.dev/", "https://genzpulsehub-ads.genzpulsehub-official.workers.dev/api/placements"):
        try:
            if requests.get(url, timeout=20).status_code != 200:
                issues.append(f"down: {url}")
        except Exception:
            issues.append(f"down: {url}")
    if env("META_TOKEN") and not meta_pages():
        issues.append("Meta token not working (no pages visible)")
    for lang in ("en", "ml"):
        if not yt_token(lang):
            issues.append(f"YouTube {lang} login not working")
    return issues


def main():
    now = datetime.now(IST)
    hist_p = os.path.join(AN, "followers.json")
    hist = json.load(open(hist_p)) if os.path.exists(hist_p) else {}
    f = followers()
    day = now.strftime("%Y-%m-%d")
    hist[day] = f
    json.dump(hist, open(hist_p, "w"), indent=1)
    prev = hist.get((now - timedelta(days=1)).strftime("%Y-%m-%d"), {})
    perf = post_perf()
    json.dump(perf, open(os.path.join(AN, f"perf_{day}.json"), "w"))
    changes = tune(perf)
    issues = watchdog()
    ramp = json.load(open(os.path.join(DATA, "ramp.json"))) if os.path.exists(os.path.join(DATA, "ramp.json")) else {}

    def line(k, label):
        v, pv = f.get(k), prev.get(k)
        d = f" ({v - pv:+d})" if isinstance(v, int) and isinstance(pv, int) else ""
        return f"{label}: {v if v is not None else '?'}{d}"
    msg = ["📊 **Daily report** " + day,
           " · ".join([line("yt_en", "YT EN"), line("yt_ml", "YT ML")]),
           " · ".join([line("ig_en", "IG EN"), line("ig_ml", "IG ML")]),
           " · ".join([line("fb_en", "FB EN"), line("fb_ml", "FB ML")]),
           f"Posting cap today: {ramp.get('cap', '?')}/account (IG/FB)"]
    if changes:
        msg.append("🔧 Auto-tuned topics: " + ", ".join(changes[:8]))
    if issues:
        msg.append("⚠️ Needs attention: " + "; ".join(issues))
    else:
        msg.append("✅ All systems OK")
    if now.weekday() == 0:   # Monday weekly summary
        wk = hist.get((now - timedelta(days=7)).strftime("%Y-%m-%d"), {})
        grow = [f"{k} {f[k] - wk[k]:+d}" for k in f if isinstance(f.get(k), int) and isinstance(wk.get(k), int) and not k.startswith("ytviews")]
        best = {lang: max(c.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))[0] for lang, c in perf.items() if c}
        msg.append("🗓️ **Week**: " + (", ".join(grow) or "first week") + f" | best topics: {best}")
    discord("\n".join(msg))
    print("\n".join(msg))


if __name__ == "__main__":
    main()
