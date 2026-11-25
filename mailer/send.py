"""Send queued ad emails (receipt, expiry reminders, ended, win-back) via Gmail SMTP.
Reads the D1 `emails` queue through the Cloudflare API. Runs from GitHub Actions; no Claude needed.
Secrets: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, GMAIL_APP_PASSWORD (GMAIL_USER optional)."""
import os, smtplib, ssl, json, urllib.request
from email.message import EmailMessage

ACC, TOK = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
USER = os.environ.get("GMAIL_USER", "genzpulsehub.official@gmail.com")
PW = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
API = "https://genzpulsehub-ads.genzpulsehub-official.workers.dev"
SITE = os.environ.get("SITE_URL", "https://genzpulsehub.pages.dev")
CF = f"https://api.cloudflare.com/client/v4/accounts/{ACC}/d1/database"


def cf(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, method="POST" if body else "GET",
                                 headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def db_id():
    for d in cf(f"{CF}?name=genzpulsehub-ads")["result"]:
        if d["name"] == "genzpulsehub-ads":
            return d["uuid"]
    raise SystemExit("D1 database not found")


def q(dbid, sql, params=None):
    return cf(f"{CF}/{dbid}/query", {"sql": sql, "params": params or []})["result"][0]["results"]


def body(kind, a):
    name = a.get("name") or a.get("brand") or "there"
    renew = f"{API}/api/renew?ad={a['id']}"
    end = (a.get("end_date") or "")[:10]
    T = {
        "receipt": (f"Payment received - your GenZ Pulse Hub ad ({a['brand']})",
                    f"Hi {name},\n\nThanks! We received ₹{a['amount']} for your '{a['placement']}' ad.\n"
                    f"It runs {a.get('start_date','')[:10]} to {end}.\nOrder: {a['order_id']}\n\n"
                    f"Track it: {SITE}/advertise/thanks/?order={a['order_id']}\n"),
        "expiring_3d": (f"Your ad ends in 3 days - renew with 10% off",
                        f"Hi {name},\n\nYour '{a['brand']}' ad ends on {end}. Keep it running with 10% off:\n{renew}\n"),
        "expiring_1d": (f"Last day tomorrow - renew your ad (10% off)",
                        f"Hi {name},\n\nYour '{a['brand']}' ad ends tomorrow ({end}). One click to renew at 10% off:\n{renew}\n"),
        "ended": (f"Your GenZ Pulse Hub ad has ended",
                  f"Hi {name},\n\nYour '{a['brand']}' ad finished on {end}. It got {a.get('impressions',0)} views and "
                  f"{a.get('clicks',0)} clicks.\nRun it again (10% off): {renew}\n"),
        "winback": (f"Come back to GenZ Pulse Hub - 10% off your next ad",
                    f"Hi {name},\n\nOur audience keeps growing. Book your next ad with 10% off:\n{renew}\n"),
    }
    s, b = T.get(kind, T["receipt"])
    return s, b + "\nGenZ Pulse Hub\nReply to this email if you need help.\n"


def main():
    if not PW:
        print("GMAIL_APP_PASSWORD not set; skipping"); return
    dbid = db_id()
    rows = q(dbid, "SELECT e.n, e.kind, a.* FROM emails e JOIN ads a ON a.id=e.ad_id WHERE e.sent IS NULL ORDER BY e.n LIMIT 40")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(USER, PW)
        print("gmail login ok;", len(rows), "emails queued")
        for r in rows:
            if not r.get("email"):
                q(dbid, "UPDATE emails SET sent='no-email' WHERE n=?", [r["n"]]); continue
            subj, text = body(r["kind"], r)
            m = EmailMessage(); m["From"] = f"GenZ Pulse Hub <{USER}>"; m["To"] = r["email"]; m["Subject"] = subj
            m.set_content(text)
            s.send_message(m)
            q(dbid, "UPDATE emails SET sent=datetime('now') WHERE n=?", [r["n"]])
            print("sent", r["kind"], r["n"])


if __name__ == "__main__":
    main()
