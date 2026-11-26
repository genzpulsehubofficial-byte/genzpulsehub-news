"""News sources. Each feed: (name, url, default_category, language_hint)."""

G = "https://news.google.com/rss"
GIN = "?hl=en-IN&gl=IN&ceid=IN:en"


def gsearch(q):
    return f"{G}/search?q={q.replace(' ', '+')}&hl=en-IN&gl=IN&ceid=IN:en"


FEEDS = [
    # national / world
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss", "headlines", "in"),
    ("Indian Express", "https://indianexpress.com/section/india/feed/", "headlines", "in"),
    ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories", "headlines", "in"),
    ("Hindustan Times", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "headlines", "in"),
    ("Google News India", f"{G}{GIN}", "headlines", "in"),
    ("PIB", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "headlines", "in"),
    # tech
    ("Google News Tech", f"{G}/headlines/section/topic/TECHNOLOGY{GIN}", "tech", "in"),
    ("Gadgets360", "https://feeds.feedburner.com/gadgets360-latest", "tech", "in"),
    ("TechCrunch", "https://techcrunch.com/feed/", "tech", "world"),
    ("Inc42", "https://inc42.com/feed/", "tech", "in"),
    # money
    ("Google News Business", f"{G}/headlines/section/topic/BUSINESS{GIN}", "money", "in"),
    ("Livemint", "https://www.livemint.com/rss/money", "money", "in"),
    ("Scam alerts", gsearch("UPI scam OR cyber fraud alert India"), "money", "in"),
    # jobs / exams
    ("Jobs", gsearch("hiring freshers OR recruitment notification India"), "jobs", "in"),
    ("Exams", gsearch("exam result OR admit card OR exam date NEET JEE CAT UPSC"), "exams", "in"),
    # entertainment / sports / gaming
    ("Google News Entertainment", f"{G}/headlines/section/topic/ENTERTAINMENT{GIN}", "entertainment", "in"),
    ("OTT releases", gsearch("OTT release this week"), "entertainment", "in"),
    ("Google News Sports", f"{G}/headlines/section/topic/SPORTS{GIN}", "sports", "in"),
    ("Gaming", gsearch("BGMI OR Valorant OR esports India"), "sports", "in"),
    # health / science / good news
    ("Google News Health", f"{G}/headlines/section/topic/HEALTH{GIN}", "health", "in"),
    ("Good news", gsearch("inspiring young Indian achievement"), "trending", "in"),
    # Kerala (Malayalam channel extras)
    ("Kerala news", gsearch("Kerala news today"), "kerala", "kl"),
    ("Mathrubhumi English", "https://english.mathrubhumi.com/rss/news/kerala", "kerala", "kl"),
    ("Kerala PSC", gsearch("Kerala PSC notification OR rank list"), "exams", "kl"),
    ("Kerala weather", gsearch("Kerala rain alert IMD"), "kerala", "kl"),
    ("Mollywood", gsearch("Malayalam movie release OR box office"), "entertainment", "kl"),
]

CATEGORY_WEIGHT = {  # starting weights; Phase 6 auto-tunes these
    "headlines": 1.0, "jobs": 1.2, "money": 1.15, "tech": 1.1, "exams": 1.1,
    "trending": 1.0, "entertainment": 0.95, "health": 0.9, "sports": 0.9, "kerala": 1.0,
}

BLOCK_WORDS = [  # skip stories we never cover
    "rape", "sexual assault", "suicide", "beheaded", "lynch", "porn",
    "betting tips", "satta", "astrology", "horoscope",
]
