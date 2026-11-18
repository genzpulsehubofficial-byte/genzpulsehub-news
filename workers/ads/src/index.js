// GenZ Pulse Hub — self-serve ads API (Cloudflare Worker + D1 + Workers AI + Cashfree)
// Flow: advertiser fills form -> AI policy check (BEFORE payment) -> Cashfree order -> pay
//       -> webhook marks paid -> auto-scheduled on next free dates -> served to site/stream/socials
//       -> daily cron: start/expire ads, reminders (3d, 1d, ended, win-back) -> Discord + email queue.

const PLACEMENTS = {
  ticker:       { name: "Live ticker ad", day: 299, week: 1499, max: 5, unit: "day" , soon: true },
  segment:      { name: "Sponsored segment", day: 499, week: 2499, max: 1, unit: "day" , soon: true },
  banner:       { name: "Live screen banner", day: 799, week: 3999, max: 1, unit: "day" , soon: true },
  video:        { name: "Video ad (15-30s)", day: 1499, week: 7499, max: 2, unit: "day" , soon: true },
  story:        { name: "Sponsored story (60s on air)", once: 999, max: 3, unit: "once" , soon: true },
  site_banner:  { name: "Website banner", day: 199, week: 999, max: 1, unit: "day" },
  site_article: { name: "Sponsored article", once: 1499, max: 3, unit: "once" },
  insta:        { name: "Instagram story shout-out", once: 499, max: 2, unit: "once" },
  job:          { name: "Featured job listing", once: 499, max: 5, unit: "once" },
  bundle:       { name: "Mega bundle (1 week)", week: 5999, max: 1, unit: "week" , soon: true },
};
const BOTH_LANG_DISCOUNT = 0.75;   // 25% off when buying English + Malayalam together
const BANNED = /bet(ting)?|casino|gambl|satta|lottery|crypto|bitcoin|forex|loan app|instant loan|mlm|network marketing|adult|escort|dating|vape|tobacco|alcohol|liquor|guaranteed (returns|profit|income)|100% (cure|guarantee)|weight loss miracle|political party|vote for|election/i;

const json = (d, s = 200, h = {}) => new Response(JSON.stringify(d), {
  status: s, headers: { "content-type": "application/json", ...CORS, ...h } });
const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type",
  "access-control-allow-methods": "GET,POST,OPTIONS" };
const today = () => new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);   // IST date
const addDays = (d, n) => new Date(Date.parse(d) + n * 864e5).toISOString().slice(0, 10);
const id = () => crypto.randomUUID().replace(/-/g, "").slice(0, 16);

function price(p, duration, langs) {
  const P = PLACEMENTS[p];
  if (!P) throw new Error("unknown placement");
  let base;
  if (P.unit === "once") base = P.once;
  else if (P.unit === "week") base = P.week * Math.max(1, Math.round(duration / 7));
  else base = duration >= 7 ? P.week * Math.floor(duration / 7) + P.day * (duration % 7) : P.day * duration;
  const total = langs.length === 2 ? Math.round(base * 2 * BOTH_LANG_DISCOUNT) : base;
  return total;
}

async function discord(env, msg) {
  if (!env.DISCORD_WEBHOOK_URL) return;
  await fetch(env.DISCORD_WEBHOOK_URL, { method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ content: ("@everyone " + msg).slice(0, 1900), username: "GenZ Pulse Hub Ads",
      allowed_mentions: { parse: ["everyone"] } }) }).catch(() => {});
}

async function aiCheck(env, ad) {
  const text = `${ad.brand}\n${ad.text}\n${ad.details || ""}\n${ad.link}`;
  if (BANNED.test(text)) return { ok: false, reason: "This category of ad is not allowed on GenZ Pulse Hub." };
  if (!/^https:\/\/[\w.-]+\.[a-z]{2,}/i.test(ad.link || "")) return { ok: false, reason: "Please give a valid https:// link." };
  try {
    const r = await env.AI.run("@cf/meta/llama-3.3-70b-instruct-fp8-fast", { messages: [{ role: "user", content:
`You review ads for an Indian news channel watched by teens (13+) and young adults. Be STRICT; when in doubt reject.
Reject: gambling/betting, crypto/forex/trading tips, loan apps, MLM, adult/dating, alcohol/tobacco/vape, political ads,
fake jobs or "earn from home" schemes, medical or guaranteed-income/result claims, misleading or scammy wording, hate, weapons.
Reply ONLY JSON: {"ok": true|false, "reason": "short reason for the advertiser"}
AD:\n${text}` }], max_tokens: 200 });
    const m = String(r.response || "").match(/\{[\s\S]*\}/);
    const v = m ? JSON.parse(m[0]) : { ok: false, reason: "Could not verify this ad automatically." };
    return { ok: !!v.ok, reason: v.reason || "" };
  } catch (e) {
    return { ok: false, reason: "Ad check is busy, please try again in a minute." };
  }
}

async function nextStart(env, placement, lang, duration) {
  const P = PLACEMENTS[placement];
  let d = addDays(today(), 1);
  for (let i = 0; i < 120; i++, d = addDays(d, 1)) {
    const end = addDays(d, Math.max(duration, 1) - 1);
    const { results } = await env.DB.prepare(
      `SELECT COUNT(*) c FROM ads WHERE placement=? AND lang IN (?, 'both') AND status IN ('paid','live')
       AND start_date <= ? AND end_date >= ?`).bind(placement, lang, end, d).all();
    if (results[0].c < P.max) return d;
  }
  return null;
}

async function cashfree(env, path, body) {
  const r = await fetch(`https://api.cashfree.com/pg${path}`, { method: body ? "POST" : "GET",
    headers: { "content-type": "application/json", "x-api-version": "2023-08-01",
      "x-client-id": env.CASHFREE_APP_ID, "x-client-secret": env.CASHFREE_SECRET_KEY },
    body: body ? JSON.stringify(body) : undefined });
  const j = await r.json();
  if (!r.ok) throw new Error(j.message || "cashfree error");
  return j;
}

async function verifyWebhook(env, req, raw) {
  const ts = req.headers.get("x-webhook-timestamp"), sig = req.headers.get("x-webhook-signature");
  if (!ts || !sig) return false;
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.CASHFREE_SECRET_KEY),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(ts + raw));
  return btoa(String.fromCharCode(...new Uint8Array(mac))) === sig;
}

async function markPaid(env, orderId) {
  const ad = await env.DB.prepare("SELECT * FROM ads WHERE order_id=?").bind(orderId).first();
  if (!ad || ad.status !== "pending") return ad;
  const o = await cashfree(env, `/orders/${orderId}`);          // double-check with Cashfree
  if (o.order_status !== "PAID") return ad;
  const langs = ad.lang === "both" ? ["en", "ml"] : [ad.lang];
  let start = null;
  for (const l of langs) { const s = await nextStart(env, ad.placement, l, ad.duration); if (!start || s > start) start = s; }
  const end = addDays(start, Math.max(ad.duration, 1) - 1);
  await env.DB.prepare("UPDATE ads SET status='paid', start_date=?, end_date=?, paid_at=? WHERE id=?")
    .bind(start, end, new Date().toISOString(), ad.id).run();
  await env.DB.prepare("INSERT INTO emails (ad_id, kind, created) VALUES (?, 'receipt', ?)").bind(ad.id, new Date().toISOString()).run();
  await discord(env, `💰 **New ad paid** — ₹${ad.amount} · ${PLACEMENTS[ad.placement].name} (${ad.lang}) · **${ad.brand}** · runs ${start} → ${end}`);
  return { ...ad, status: "paid", start_date: start, end_date: end };
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    try {
      if (url.pathname === "/api/placements")
        return json({ placements: PLACEMENTS, both_lang_discount: BOTH_LANG_DISCOUNT });

      if (url.pathname === "/api/quote") {
        const p = url.searchParams.get("placement"), d = +url.searchParams.get("days") || 1;
        const langs = (url.searchParams.get("lang") || "en") === "both" ? ["en", "ml"] : ["en"];
        const start = await nextStart(env, p, langs[0], d);
        return json({ amount: price(p, d, langs), next_start: start });
      }

      if (url.pathname === "/api/order" && req.method === "POST") {
        const b = await req.json();
        const ad = { brand: String(b.brand || "").slice(0, 60), text: String(b.text || "").slice(0, 160),
          details: String(b.details || "").slice(0, 1200), link: String(b.link || "").slice(0, 300),
          email: String(b.email || "").slice(0, 120), phone: String(b.phone || "").replace(/\D/g, "").slice(-10),
          name: String(b.name || "").slice(0, 80), placement: b.placement, lang: ["en", "ml", "both"].includes(b.lang) ? b.lang : "en",
          duration: Math.min(Math.max(+b.days || 1, 1), 60), logo: String(b.logo || "").slice(0, 400) };
        if (!PLACEMENTS[ad.placement]) return json({ error: "Choose a placement." }, 400);
        if (PLACEMENTS[ad.placement].soon) return json({ error: "This placement opens when our 24/7 live stream launches. Coming soon!" }, 400);
        if (!ad.brand || !ad.text || !/^\S+@\S+\.\S+$/.test(ad.email) || ad.phone.length !== 10)
          return json({ error: "Please fill brand, ad text, a valid email and 10-digit phone." }, 400);
        const check = await aiCheck(env, ad);
        if (!check.ok) {
          await discord(env, `🚫 Ad auto-rejected before payment — **${ad.brand}**: ${check.reason}`);
          return json({ error: "Sorry, we can't run this ad: " + check.reason }, 422);
        }
        const amount = price(ad.placement, ad.duration, ad.lang === "both" ? ["en", "ml"] : ["en"]);
        const adId = id(), orderId = "gzp_" + adId;
        const o = await cashfree(env, "/orders", { order_id: orderId, order_amount: amount, order_currency: "INR",
          customer_details: { customer_id: "adv_" + ad.phone, customer_name: ad.name || ad.brand,
            customer_email: ad.email, customer_phone: ad.phone },
          order_meta: { return_url: `${env.SITE_URL}/advertise/thanks/?order={order_id}`,
            notify_url: `${url.origin}/api/cf-webhook` },
          order_note: `${PLACEMENTS[ad.placement].name} - ${ad.brand}` });
        await env.DB.prepare(`INSERT INTO ads (id, order_id, status, placement, lang, duration, amount, brand, text, details,
          link, logo, name, email, phone, created) VALUES (?,?,'pending',?,?,?,?,?,?,?,?,?,?,?,?,?)`)
          .bind(adId, orderId, ad.placement, ad.lang, ad.duration, amount, ad.brand, ad.text, ad.details, ad.link,
            ad.logo, ad.name, ad.email, ad.phone, new Date().toISOString()).run();
        return json({ order_id: orderId, amount, payment_session_id: o.payment_session_id });
      }

      if (url.pathname === "/api/cf-webhook" && req.method === "POST") {
        const raw = await req.text();
        if (!(await verifyWebhook(env, req, raw))) return json({ error: "bad signature" }, 401);
        const ev = JSON.parse(raw);
        const orderId = ev?.data?.order?.order_id;
        if (orderId && ev.type?.includes("PAYMENT_SUCCESS")) await markPaid(env, orderId);
        return json({ ok: true });
      }

      if (url.pathname === "/api/status") {             // used by the thanks page
        const orderId = url.searchParams.get("order");
        const ad = await markPaid(env, orderId).catch(() => null);
        return ad ? json({ status: ad.status, start: ad.start_date, end: ad.end_date, brand: ad.brand }) : json({ error: "not found" }, 404);
      }

      if (url.pathname === "/api/renew") {               // 1-click renew link from reminder emails
        const old = await env.DB.prepare("SELECT * FROM ads WHERE id=?").bind(url.searchParams.get("ad")).first();
        if (!old) return json({ error: "not found" }, 404);
        const amount = Math.round(old.amount * 0.9);     // 10% renewal discount
        const adId = id(), orderId = "gzp_" + adId;
        const o = await cashfree(env, "/orders", { order_id: orderId, order_amount: amount, order_currency: "INR",
          customer_details: { customer_id: "adv_" + old.phone, customer_name: old.name || old.brand,
            customer_email: old.email, customer_phone: old.phone },
          order_meta: { return_url: `${env.SITE_URL}/advertise/thanks/?order={order_id}`, notify_url: `${url.origin}/api/cf-webhook` } });
        await env.DB.prepare(`INSERT INTO ads (id, order_id, status, placement, lang, duration, amount, brand, text, details,
          link, logo, name, email, phone, created, renewed_from) VALUES (?,?,'pending',?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
          .bind(adId, orderId, old.placement, old.lang, old.duration, amount, old.brand, old.text, old.details, old.link,
            old.logo, old.name, old.email, old.phone, new Date().toISOString(), old.id).run();
        return Response.redirect(`${env.SITE_URL}/advertise/pay/?sid=${o.payment_session_id}&order=${orderId}`, 302);
      }

      if (url.pathname === "/api/active") {               // site, stream and socials read this
        const d = today();
        const { results } = await env.DB.prepare(`SELECT id, placement, lang, brand, text, details, link, logo FROM ads
          WHERE status IN ('paid','live') AND start_date <= ? AND end_date >= ?`).bind(d, d).all();
        const lang = url.searchParams.get("lang"), slot = url.searchParams.get("slot");
        const out = results.filter(a => (!lang || a.lang === lang || a.lang === "both") &&
          (!slot || a.placement === slot || a.placement === "bundle"))
          .map(a => ({ ...a, link: `${url.origin}/go/${a.id}` }));
        return json({ ads: out }, 200, { "cache-control": "public, max-age=120" });
      }

      if (url.pathname.startsWith("/go/")) {               // click tracking redirect
        const ad = await env.DB.prepare("SELECT link FROM ads WHERE id=?").bind(url.pathname.slice(4)).first();
        if (!ad) return new Response("Not found", { status: 404 });
        await env.DB.prepare("UPDATE ads SET clicks = clicks + 1 WHERE id=?").bind(url.pathname.slice(4)).run();
        return Response.redirect(ad.link, 302);
      }

      if (url.pathname === "/api/impression" && req.method === "POST") {
        const b = await req.json().catch(() => ({}));
        for (const a of (b.ids || []).slice(0, 10))
          await env.DB.prepare("UPDATE ads SET impressions = impressions + ? WHERE id=?").bind(+b.n || 1, a).run();
        return json({ ok: true });
      }
      return json({ service: "GenZ Pulse Hub ads", ok: true });
    } catch (e) {
      return json({ error: String(e.message || e) }, 500);
    }
  },

  async scheduled(_ev, env) {                             // daily 9:00 IST
    const d = today();
    await env.DB.prepare("UPDATE ads SET status='live' WHERE status='paid' AND start_date <= ?").bind(d).run();
    const ended = await env.DB.prepare("SELECT * FROM ads WHERE status='live' AND end_date < ?").bind(d).all();
    for (const a of ended.results) {
      await env.DB.prepare("UPDATE ads SET status='ended' WHERE id=?").bind(a.id).run();
      await env.DB.prepare("INSERT INTO emails (ad_id, kind, created) VALUES (?, 'ended', ?)").bind(a.id, new Date().toISOString()).run();
    }
    for (const [days, kind] of [[3, "expiring_3d"], [1, "expiring_1d"]]) {
      const soon = await env.DB.prepare("SELECT id FROM ads WHERE status='live' AND end_date = ?").bind(addDays(d, days - 1)).all();
      for (const a of soon.results)
        await env.DB.prepare("INSERT INTO emails (ad_id, kind, created) VALUES (?, ?, ?)").bind(a.id, kind, new Date().toISOString()).run();
    }
    const win = await env.DB.prepare(`SELECT id FROM ads a WHERE status='ended' AND end_date = ?
      AND NOT EXISTS (SELECT 1 FROM ads b WHERE b.renewed_from = a.id)`).bind(addDays(d, -7)).all();
    for (const a of win.results)
      await env.DB.prepare("INSERT INTO emails (ad_id, kind, created) VALUES (?, 'winback', ?)").bind(a.id, new Date().toISOString()).run();
    await env.DB.prepare("DELETE FROM ads WHERE status='pending' AND created < ?").bind(new Date(Date.now() - 2 * 864e5).toISOString()).run();
    if (ended.results.length) await discord(env, `📅 ${ended.results.length} ad(s) ended today; renewal emails queued.`);
  },
};
