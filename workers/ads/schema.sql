CREATE TABLE IF NOT EXISTS ads (
  id TEXT PRIMARY KEY, order_id TEXT UNIQUE, status TEXT,           -- pending | paid | live | ended
  placement TEXT, lang TEXT, duration INTEGER, amount INTEGER,
  brand TEXT, text TEXT, details TEXT, link TEXT, logo TEXT,
  name TEXT, email TEXT, phone TEXT,
  start_date TEXT, end_date TEXT, created TEXT, paid_at TEXT, renewed_from TEXT,
  clicks INTEGER DEFAULT 0, impressions INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ads_active ON ads (status, start_date, end_date);
CREATE TABLE IF NOT EXISTS emails (
  n INTEGER PRIMARY KEY AUTOINCREMENT, ad_id TEXT, kind TEXT, created TEXT, sent TEXT
);
