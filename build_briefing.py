import os
import re
import html
import datetime as dt
from dateutil import tz
import feedparser

# -----------------------
# Settings (you can tweak)
# -----------------------
TIMEZONE = "America/Edmonton"
LAST_RUN_FILE = "last_run.txt"

MAX_ITEMS_PER_SECTION = 8  # keep it tight to prevent spirals
MAX_BULLETS = 3            # per item
SUMMARY_CHARS_FALLBACK = 240

# High-risk keywords (Trump/war etc). Only allowed if source is trusted.
HIGH_RISK_KEYWORDS = [
    "trump", "maga", "white house", "president",
    "war", "invasion", "missile", "nuclear", "airstrike",
    "terror", "hostage", "genocide"
]

TRUSTED_SOURCES_FOR_HIGH_RISK = {
    "CBC",
    "BBC",
    "Reuters",
}

# Sections + RSS feeds
FEEDS = {
    "Canada News": [
        ("CBC", "https://www.cbc.ca/webfeed/rss/rss-canada"),
    ],
    "Sports (NHL/MLB/NFL)": [
        ("NHL", "http://www.nhl.com/rss/news.xml"),
        ("ESPN", "https://www.espn.com/espn/rss/news"),
        ("The Hockey Writers", "https://thehockeywriters.com/feed/"),
    ],
    "AI Tech (assistants + robots)": [
        ("BBC", "http://feeds.bbci.co.uk/news/technology/rss.xml"),
        ("BBC", "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ],
    "Basic American News (big-impact only)": [
        ("BBC", "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
        # Reuters feeds sometimes work, sometimes fail; leaving in as an option
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
def now_local():
    return dt.datetime.now(tz.gettz(TIMEZONE))

def utc_now():
    return dt.datetime.now(dt.timezone.utc)

def clean_text(s: str) -> str:
    s = s or ""
    s = re.sub(r"\s+", " ", s).strip()
    return s

def is_high_risk(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in HIGH_RISK_KEYWORDS)

def parse_entry_time(entry) -> dt.datetime | None:
    """
    Return a UTC datetime if we can parse one, else None.
    """
    for attr in ("published_parsed", "updated_parsed"):
        p = getattr(entry, attr, None)
        if p:
            try:
                return dt.datetime(*p[:6], tzinfo=dt.timezone.utc)
            except Exception:
                pass
    return None

def load_last_run_utc() -> dt.datetime:
    """
    If last_run.txt exists, use it; else default to 24 hours ago (first run).
    """
    if os.path.exists(LAST_RUN_FILE):
        raw = clean_text(open(LAST_RUN_FILE, "r", encoding="utf-8").read())
        try:
            # expected ISO like: 2026-01-19T15:00:00Z
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            return dt.datetime.fromisoformat(raw).astimezone(dt.timezone.utc)
        except Exception:
            pass

    return utc_now() - dt.timedelta(hours=24)

def save_last_run_utc(ts_utc: dt.datetime):
    s = ts_utc.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        f.write(s + "\n")

def dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        key = re.sub(r"[^a-z0-9]+", "", (it["title"] or "").lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def bullets_from_summary(summary: str, max_bullets: int = MAX_BULLETS) -> list[str]:
    summary = clean_text(summary)
    if not summary:
        return []
    parts = re.split(r"(?<=[.!?])\s+", summary)
    bullets = []
    for p in parts:
        p = clean_text(p)
        if not p:
            continue
        if len(p) > 180:
            p = p[:177].rstrip() + "…"
        bullets.append(p)
        if len(bullets) >= max_bullets:
            break
    return bullets

def esc(s: str) -> str:
    return html.escape(s or "", quote=True)

# -----------------------
# Main build
# -----------------------
def main():
    last_run_utc = load_last_run_utc()
    this_run_utc = utc_now()

    # Display time in your local zone (for sanity)
    last_run_local = last_run_utc.astimezone(tz.gettz(TIMEZONE))
    this_run_local = this_run_utc.astimezone(tz.gettz(TIMEZONE))

    header_date = this_run_local.strftime("%A, %B %d, %Y")
    window_line = f"New since: {last_run_local.strftime('%a %I:%M %p')} → {this_run_local.strftime('%a %I:%M %p')} ({TIMEZONE})"

    sections_out: list[tuple[str, list[dict]]] = []

    for section, feed_list in FEEDS.items():
        collected = []

        for source_name, url in feed_list:
            try:
                parsed = feedparser.parse(url)
            except Exception:
                # Some feeds occasionally drop connections; skip quietly
                continue

            # If a feed errors, just skip it quietly (no spiraling)
            if getattr(parsed, "bozo", 0) == 1 and not getattr(parsed, "entries", None):
                continue

            for e in parsed.entries[:40]:
                title = clean_text(getattr(e, "title", ""))
                summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", ""))

                if not title:
                    continue

                published_utc = parse_entry_time(e)
                if not published_utc:
                    # If no timestamp, we can't safely do "since last run" — skip it.
                    continue

                # Only include items newer than last run
                if published_utc <= last_run_utc:
                    continue

                # High-risk filter: only allow from trusted sources
                if is_high_risk(title) and source_name not in TRUSTED_SOURCES_FOR_HIGH_RISK:
                    continue

                collected.append({
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "published_utc": published_utc,
                })

        # Dedup + sort newest first
        collected = dedupe(collected)
        collected.sort(key=lambda x: x["published_utc"], reverse=True)

        # Positive story: force exactly 1
        if section == "One Positive Story":
            collected = collected[:1]
        else:
            collected = collected[:MAX_ITEMS_PER_SECTION]

        sections_out.append((section, collected))

    # Build HTML (NO external links)
    html_parts = []
    html_parts.append(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Doomscroll Briefing — {esc(header_date)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0; background: #0b0f14; color: #e7edf5; }}
    .wrap {{ max-width: 900px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 22px; margin: 0 0 6px; }}
    .sub {{ color: #a9b6c6; margin: 0 0 18px; }}
    .card {{ background: #121923; border: 1px solid #1d2a3a; border-radius: 14px; padding: 16px; margin: 14px 0; }}
    h2 {{ font-size: 18px; margin: 0 0 10px; }}
    .item {{ padding: 10px 0; border-top: 1px solid #1d2a3a; }}
    .item:first-of-type {{ border-top: none; padding-top: 0; }}
    .title {{ font-weight: 650; margin: 0 0 6px; }}
    .meta {{ color: #a9b6c6; font-size: 12px; margin: 0 0 8px; }}
    ul {{ margin: 0; padding-left: 18px; color: #d6e0ec; }}
    .badge {{ display:inline-block; font-size:11px; padding:2px 8px; border:1px solid #2a3b52; border-radius:999px; color:#cfe3ff; margin-left:8px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Doomscroll Briefing</h1>
    <p class="sub">{esc(header_date)} • {esc(window_line)} • hard cap • no links</p>
""")

    for section_name, items in sections_out:
        html_parts.append(f'<div class="card"><h2>{esc(section_name)}</h2>')

        if not items:
            html_parts.append('<div class="item"><p class="meta">No new items since last send.</p></div>')
            html_parts.append("</div>")
            continue

        for it in items:
            title = it["title"]
            source = it["source"]
            summary = it["summary"]

            badge = ""
            if is_high_risk(title) and source in TRUSTED_SOURCES_FOR_HIGH_RISK:
                badge = '<span class="badge">trusted-source</span>'

            bullets = bullets_from_summary(summary, MAX_BULLETS)

            html_parts.append('<div class="item">')
            html_parts.append(f'<p class="title">{esc(title)}{badge}</p>')
            html_parts.append(f'<p class="meta">{esc(source)}</p>')

            if bullets:
                html_parts.append("<ul>")
                for b in bullets:
                    html_parts.append(f"<li>{esc(b)}</li>")
                html_parts.append("</ul>")
            else:
                fallback = (summary[:SUMMARY_CHARS_FALLBACK] + ("…" if len(summary) > SUMMARY_CHARS_FALLBACK else ""))
                html_parts.append(f'<p class="meta">{esc(fallback)}</p>')

            html_parts.append("</div>")

        html_parts.append("</div>")

    html_parts.append("""
  </div>
</body>
</html>
""")

    out = "\n".join(html_parts)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(out)

    # Save last-run marker so tomorrow is "since today"
    save_last_run_utc(this_run_utc)

    print("Generated index.html and updated last_run.txt")

if __name__ == "__main__":
    main()
