import os
import re
import html
import datetime as dt
from dateutil import tz
import feedparser

# -----------------------
# Settings
# -----------------------
TIMEZONE = "America/Edmonton"
LAST_RUN_FILE = "last_run.txt"

MAX_ITEMS_PER_SECTION = 8
MAX_BULLETS = 3
SUMMARY_CHARS_FALLBACK = 240

HIGH_RISK_KEYWORDS = [
    "trump", "maga", "white house", "president",
    "war", "invasion", "missile", "nuclear", "airstrike",
    "terror", "hostage", "genocide"
]

TRUSTED_SOURCES_FOR_HIGH_RISK = {
    "CBC", "BBC", "Reuters"
}

# -----------------------
# Feeds
# -----------------------
FEEDS = {
    "Canada News": [
        ("CBC", "https://www.cbc.ca/webfeed/rss/rss-canada"),
    ],

    "Sports (Oilers + NHL — real news)": [
        ("Sportsnet", "https://www.sportsnet.ca/feed/"),
        ("TSN", "https://www.tsn.ca/rss"),
        ("NHL", "http://www.nhl.com/rss/news.xml"),
    ],

    "Sports Blogs (Oilers)": [
        ("Lowetide", "https://lowetide.ca/feed/"),
        ("Oilersnation", "https://oilersnation.com/feed/"),
    ],

    "AI Tech (assistants + robots)": [
        ("BBC", "http://feeds.bbci.co.uk/news/technology/rss.xml"),
        ("BBC", "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ],

    "Basic American News (big-impact only)": [
        ("BBC", "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
        ("Reuters", "http://feeds.reuters.com/Reuters/domesticNews"),
    ],

    "Big World Events": [
        ("BBC", "http://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Reuters", "http://feeds.reuters.com/Reuters/worldNews"),
    ],

    "One Positive Story": [
        ("Good News Network", "https://www.goodnewsnetwork.org/feed/"),
    ],
}

# -----------------------
# Helpers
# -----------------------
def utc_now():
    return dt.datetime.now(dt.timezone.utc)

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def parse_entry_time(entry):
    for attr in ("published_parsed", "updated_parsed"):
        p = getattr(entry, attr, None)
        if p:
            try:
                return dt.datetime(*p[:6], tzinfo=dt.timezone.utc)
            except Exception:
                pass
    return None

def load_last_run_utc():
    try:
        if not os.path.exists(LAST_RUN_FILE):
            return utc_now() - dt.timedelta(days=1)

        raw = open(LAST_RUN_FILE, "r", encoding="utf-8").read().strip()
        if not raw:
            return utc_now() - dt.timedelta(days=1)

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        return dt.datetime.fromisoformat(raw)
    except Exception:
        return utc_now() - dt.timedelta(days=1)

def save_last_run_utc(ts):
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        f.write(ts.replace(microsecond=0).isoformat().replace("+00:00", "Z"))

def esc(s: str) -> str:
    return html.escape(s or "", quote=True)

# -----------------------
# Main
# -----------------------
def main():
    last_run_utc = load_last_run_utc()
    this_run_utc = utc_now()

    last_run_local = last_run_utc.astimezone(tz.gettz(TIMEZONE))
    this_run_local = this_run_utc.astimezone(tz.gettz(TIMEZONE))

    header_date = this_run_local.strftime("%A, %B %d, %Y")
    window_line = f"New since: {last_run_local.strftime('%a %I:%M %p')} → {this_run_local.strftime('%a %I:%M %p')} ({TIMEZONE})"

    sections_out = []

    for section, feeds in FEEDS.items():
        items = []

        for source, url in feeds:
            try:
                parsed = feedparser.parse(url)
            except Exception:
                continue

            for e in parsed.entries[:40]:
                title = clean_text(getattr(e, "title", ""))
                summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", ""))

                if not title:
                    continue

                published = parse_entry_time(e)
                if not published or published <= last_run_utc:
                    continue

                items.append({
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "published": published,
                })

        items.sort(key=lambda x: x["published"], reverse=True)
        items = items[:1] if section == "One Positive Story" else items[:MAX_ITEMS_PER_SECTION]
        sections_out.append((section, items))

    html_out = [f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Doomscroll Briefing</title>
</head>
<body>
<h1>Doomscroll Briefing</h1>
<p>{esc(header_date)} • {esc(window_line)}</p>
"""]

    for section, items in sections_out:
        html_out.append(f"<h2>{esc(section)}</h2>")
        if not items:
            html_out.append("<p>No new items since last send.</p>")
            continue

        for it in items:
            html_out.append(f"<p><strong>{esc(it['title'])}</strong><br>{esc(it['source'])}<br>{esc(it['summary'])}</p>")

    html_out.append("</body></html>")

    with open("index.html", "w", encoding="utf-8") as f:
        f.write("\n".join(html_out))

    save_last_run_utc(this_run_utc)

if __name__ == "__main__":
    main()
