# GenZ Pulse Hub — handbook (read this first)

24/7 AI-run news brand for Indian Gen Z (+ incoming Gen Alpha teens, 13+). Two channels: **English** and **Malayalam**.
Runs at **₹0** and uses **no Claude usage at runtime** — only free AI APIs, GitHub Actions and Cloudflare.

Owner: Shaazamaan Shaji (not technical — open exact pages for him; he only does Ctrl+C / Ctrl+V).

## Owner rules (never break)
- Every story is **fully rewritten** in our own words (hook → what happened → why it matters to you). Never copy sentences. Only facts present in the source; credit the source.
- Fully automatic: **no human approvals**. Alerts/reports go to Discord with `@everyone`.
- Nothing is announced on any social account until the owner confirms the system is finished and working.
- Neutral on politics; crime = facts only, no private victims' names; no medical/financial promises.
- Audience is Gen Z + Gen Alpha teens (13+). Not millennials. Channels are "Not made for kids".
- Keys only in GitHub Secrets — never in code or chat.

## Accounts (all on genzpulsehub.official@gmail.com unless noted)
| Thing | Value |
|---|---|
| YouTube EN | GenZ Pulse Hub — @genzpulsehubnews (UCrpJDlRnVJyC4EguHKJxHKg) |
| YouTube ML | GenZ Pulse Hub Malayalam — @genzpulsehubmalayalam (UC3dW_vEz432vsb6uqlCVHAw) |
| Facebook Pages | GenZ Pulse Hub (61596319547043), GenZ Pulse Hub Malayalam (61596419862358) |
| Instagram | @genzpulsehubnews, @genzpulsehubmalayalam (Business, linked to Pages) |
| Meta portfolio | "GenZ Pulse Hub" (business_id 932757405756172) |
| GitHub | genzpulsehubofficial-byte/genzpulsehub-news |
| Cloudflare | brand account (id in secret CLOUDFLARE_ACCOUNT_ID) |
| Domain | genzpulsehub.dpdns.org (EN at `/`, ML at `/ml`) — move to a real domain before AdSense/ads |
| Email | Hostinger business email (for ad receipts) |
| Payments | Cashfree (ad system, Phase 4) |

## Secrets (names only)
`GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DISCORD_WEBHOOK_URL`.
GitHub Models uses the built-in `GITHUB_TOKEN` (workflow permission `models: read`).
Dropped (now paid): Cerebras, Mistral.

## AI fallback chain
Gemini → Groq → OpenRouter (free models) → GitHub Models → Cloudflare Workers AI. `pipeline/ai.py` tries each in order, logs which answered, alerts Discord only if all fail.

## Architecture
```
GitHub Actions (every 15 min)  → fetch RSS → rank → rewrite EN+ML → data/  (Phase 1 ✅)
Stream device (TBD)            → TTS + mascot + FFmpeg → 24/7 YouTube Live  (Phase 2)
Cloudflare Pages               → website from data/                         (Phase 3)
Cloudflare Workers + D1 + R2   → self-serve ads + Cashfree + AI ad check    (Phase 4)
Meta/YouTube/Threads/X APIs    → Shorts, Reels, posts → drive to live       (Phase 5)
Analytics + Audience Pulse     → daily score, weekly/monthly auto-optimise  (Phase 6)
```

## Content
Categories: headlines, jobs, money+scams, tech/AI, exams, trending/good news, entertainment, health myth-busting, sports/gaming.
Malayalam extras: Kerala PSC, KSEB/KSRTC, rain alerts, Mollywood, K-wave, stay-or-fly (jobs abroad), youth schemes.
"Breaking" only when ≥2 sources report it.

## Data layout
- `data/stories/YYYY-MM-DD/<id>.json` — one rewritten story (both languages)
- `data/latest_en.json`, `data/latest_ml.json` — newest 40 for the stream/site
- `data/seen.json` — dedupe of source links (pruned)
- Stories older than 7 days are deleted automatically.

## Status / change log
- 2026-11-18: All accounts + keys set up. Phase 1 pipeline built.
- Open: choose stream device (Oracle free / phone with new battery / mini PC). Meta refund of ₹499.99 (old ad account) — check 27 Nov.
