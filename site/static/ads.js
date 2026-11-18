// Fills [data-slot] placeholders with live paid ads (always labelled Sponsored). Hides empty slots.
(function () {
  const API = "__ADS_API__";
  const slots = [...document.querySelectorAll("[data-slot]")];
  if (!slots.length) return;
  const lang = slots[0].dataset.lang || "en";
  fetch(`${API}/api/active?lang=${lang}&slot=site_banner`).then(r => r.json()).then(j => {
    const ads = j.ads || [];
    if (!ads.length) { slots.forEach(s => s.innerHTML = '<a href="/advertise/" style="text-decoration:none">📣 Your brand here — advertise on GenZ Pulse Hub</a>'); return; }
    const esc = s => String(s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    slots.forEach((s, i) => {
      const a = ads[i % ads.length];
      s.style.borderStyle = "solid";
      s.innerHTML = `<small style="opacity:.6">Sponsored</small><br><a href="${a.link}" rel="sponsored noopener" target="_blank" style="text-decoration:none;font-weight:700">` +
        (a.logo ? `<img src="${esc(a.logo)}" alt="" style="height:40px;vertical-align:middle;margin-right:8px">` : "") + `${esc(a.brand)} — ${esc(a.text)}</a>`;
    });
    fetch(`${API}/api/impression`, { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ ids: [...new Set(slots.map((_, i) => ads[i % ads.length].id))] }) });
  }).catch(() => {});
})();
