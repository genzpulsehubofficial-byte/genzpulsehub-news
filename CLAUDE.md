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
- 2026-11-19..24: Phase 3 site live on genzpulsehub.pages.dev (custom domain pending). Phase 4 ads Worker live (genzpulsehub-ads.genzpulsehub-official.workers.dev, D1, Cashfree prod; live-stream slots marked "Coming soon"). Shorts renderer + publisher built.
- 2026-11-25: YouTube publishing WORKS for both channels (secrets YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_EN, YT_REFRESH_ML). Oracle Cloud account approved: tenancy `genzpulsehubofficial`, region ap-mumbai-1, login genzpulsehub.official@gmail.com.

## For a future Claude session (start here)
The owner only logs in and Ctrl+C/Ctrl+V's keys. You do everything else: open the exact page, fill fields, click, then hand him only the login/approval/secret-paste step. Never ask him to type code.
- Repo is the single source of truth. Read this file, then `git log -20`.
- Check health: latest runs of `news`, `shorts`, `ads-deploy` workflows; `data/status.json`; Discord.
- Secrets can't be read back from GitHub. If one is wrong, the owner re-copies it from the provider and pastes into the GitHub "Update secret" page you open.
- YouTube refresh token: OAuth Playground with own credentials (client above, redirect https://developers.google.com/oauthplayground), scopes youtube.upload youtube.readonly yt-analytics.readonly, access type offline. Click **Exchange authorization code for tokens**; copy the **Refresh token** (starts `1//`), NOT the auth code (`4/`). English = main "GenZ Pulse" account, Malayalam = brand account "GenZ Pulse Hub Malayalam".

## Decisions (owner)
- Posting volume: ramp, don't blast. IG/FB start 30/day per account → auto-ramp to 95/day while followers/day and total reach keep rising; step down on action block/warning or 3-day reach drop. YouTube: max the free quota (~6 uploads/day total) and request a quota raise.
- Skip Telegram, WhatsApp, Threads, X.
- Advertiser outreach: inbound only (no cold DMs/emails). Auto-reply to people who contact us.
- Auto-optimise everything weekly/monthly (categories, times, lengths, formats, volume, ad prices), English and Malayalam separately, Discord report.

## Pending (in order)
1. META_TOKEN (system-user token, portfolio 932757405756172, pages + IG publish/insights perms) → Reels live.
2. Oracle VM (Always Free ARM, Mumbai) → Phase 2 24/7 stream to YouTube + Facebook; then open live ad slots.
3. Cashfree domain whitelist; domain activation → switch SITE_URL to genzpulsehub.dpdns.org; Email Routing ads@ → Gmail.
4. Gmail App Password secret + mailer for queued ad emails.
5. Auto-replies (comments, ads inbox, IG DMs), inbound ad pitch, watchdog, weekly backup, corrections, copyright guard, Google News/Discover, monetisation tracker, affiliate links.
6. Phase 6 analytics + Audience Pulse + volume ramp.
7. Mobile header fix; replace dead feeds (Indian Express, Onmanorama).
- Reminder: Meta refund ₹499.99 check on 27 Nov (scheduled).
