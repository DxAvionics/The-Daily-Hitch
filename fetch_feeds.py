#!/usr/bin/env python3
"""
THE DAILY HITCH — Feed Aggregator
Fetches from wire, underground, independent, left, right, and think tank sources.
Generates a static HTML briefing page and JSON feed.
Privacy-hardened: no tracking, no analytics, no external calls from the page itself.
"""

import feedparser
import json
import os
import re
import html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import anthropic

# ─────────────────────────────────────────────
# SOURCE REGISTRY
# ─────────────────────────────────────────────

SOURCES = {
    "WIRE": [
        {"name": "Reuters", "url": "https://feeds.reuters.com/reuters/topNews", "bias": "neutral"},
        {"name": "AP News", "url": "https://rsshub.app/apnews/topics/apf-topnews", "bias": "neutral"},
        {"name": "AFP", "url": "https://www.afp.com/en/rss-newsfeeds", "bias": "neutral"},
    ],
    "WAR & GEOPOLITICS": [
        {"name": "ISW — Institute for Study of War", "url": "https://www.understandingwar.org/feeds/rss.xml", "bias": "analytical"},
        {"name": "Bellingcat", "url": "https://www.bellingcat.com/feed/", "bias": "osint"},
        {"name": "C4ISRNET", "url": "https://www.c4isrnet.com/arc/outboundfeeds/rss/", "bias": "defense"},
        {"name": "Defense One", "url": "https://www.defenseone.com/rss/all/", "bias": "defense"},
        {"name": "War on the Rocks", "url": "https://warontherocks.com/feed/", "bias": "analytical"},
    ],
    "AEROSPACE & DEFENSE TECH": [
        {"name": "Aviation Week", "url": "https://aviationweek.com/rss.xml", "bias": "industry"},
        {"name": "The War Zone", "url": "https://www.thedrive.com/the-war-zone/rss", "bias": "defense"},
        {"name": "SpaceNews", "url": "https://spacenews.com/feed/", "bias": "industry"},
        {"name": "Janes", "url": "https://www.janes.com/feeds/news", "bias": "defense-intel"},
    ],
    "UNDERGROUND & INVESTIGATIVE": [
        {"name": "ProPublica", "url": "https://feeds.propublica.org/propublica/main", "bias": "investigative"},
        {"name": "The Intercept", "url": "https://theintercept.com/feed/?rss", "bias": "investigative-left"},
        {"name": "ICIJ", "url": "https://www.icij.org/feed/", "bias": "investigative"},
        {"name": "OCCRP", "url": "https://www.occrp.org/en/rss", "bias": "investigative"},
        {"name": "DDoSecrets Blog", "url": "https://ddosecrets.com/feed/", "bias": "leaks"},
    ],
    "INDEPENDENTS & SUBSTACK": [
        {"name": "Matt Taibbi — Racket News", "url": "https://www.racket.news/feed", "bias": "independent"},
        {"name": "Glenn Greenwald — System Update", "url": "https://greenwald.substack.com/feed", "bias": "independent"},
        {"name": "Bari Weiss — The Free Press", "url": "https://www.thefp.com/feed", "bias": "independent"},
        {"name": "Michael Shellenberger — Public", "url": "https://public.substack.com/feed", "bias": "independent"},
        {"name": "Bret Weinstein — Dark Horse", "url": "https://bretweinstein.substack.com/feed", "bias": "independent"},
        {"name": "Eric Weinstein", "url": "https://ericweinstein.substack.com/feed", "bias": "independent"},
        {"name": "Michael Yon", "url": "https://www.michaelyon-online.com/feed", "bias": "war-correspondent"},
        {"name": "Simplicius — The Duran", "url": "https://simplicius76.substack.com/feed", "bias": "independent"},
        {"name": "Naomi Wolf — DailyClout", "url": "https://naomiwolf.substack.com/feed", "bias": "independent"},
    ],
    "LEFT": [
        {"name": "Jacobin", "url": "https://jacobin.com/feed/", "bias": "hard-left"},
        {"name": "Democracy Now!", "url": "https://www.democracynow.org/democracynow.rss", "bias": "progressive"},
        {"name": "Truthout", "url": "https://truthout.org/feed/", "bias": "progressive"},
        {"name": "Mintpress News", "url": "https://www.mintpressnews.com/feed/", "bias": "anti-imperialist"},
        {"name": "The Nation", "url": "https://www.thenation.com/subject/politics/feed/", "bias": "liberal"},
    ],
    "RIGHT": [
        {"name": "Epoch Times", "url": "https://feeds.theepochtimes.com/us", "bias": "conservative"},
        {"name": "Breitbart", "url": "https://feeds.feedburner.com/breitbart", "bias": "nationalist-right"},
        {"name": "Zero Hedge", "url": "https://feeds.feedburner.com/zerohedge/feed", "bias": "fin-dark"},
        {"name": "The Daily Wire", "url": "https://www.dailywire.com/feeds/rss.xml", "bias": "conservative"},
        {"name": "InfoWars", "url": "https://www.infowars.com/rss.xml", "bias": "far-right"},
    ],
    "THINK TANKS": [
        {"name": "RAND Corporation", "url": "https://www.rand.org/feeds/research.xml", "bias": "dod-adjacent"},
        {"name": "Brookings Institution", "url": "https://www.brookings.edu/feed/", "bias": "center-left"},
        {"name": "Heritage Foundation", "url": "https://www.heritage.org/rss/research", "bias": "conservative"},
        {"name": "CSIS", "url": "https://www.csis.org/rss.xml", "bias": "defense-security"},
        {"name": "Council on Foreign Relations", "url": "https://www.cfr.org/rss/all", "bias": "establishment"},
        {"name": "Cato Institute", "url": "https://www.cato.org/rss/recent-op-eds", "bias": "libertarian"},
        {"name": "Foreign Policy", "url": "https://foreignpolicy.com/feed/", "bias": "analytical"},
    ],
    "AI & TECH": [
        {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/", "bias": "tech-analytical"},
        {"name": "Wired", "url": "https://www.wired.com/feed/rss", "bias": "tech-left"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "bias": "tech"},
        {"name": "404 Media", "url": "https://www.404media.co/rss/", "bias": "investigative-tech"},
    ],
    "SCIENCE": [
        {"name": "Nature News", "url": "https://www.nature.com/nature.rss", "bias": "peer-reviewed"},
        {"name": "New Scientist", "url": "https://www.newscientist.com/feed/home/", "bias": "science"},
        {"name": "Science Magazine", "url": "https://www.science.org/rss/news_current.xml", "bias": "peer-reviewed"},
    ],
}

ITEMS_PER_CATEGORY = 5
MAX_SUMMARY_LEN = 280


def clean_html(raw: str) -> str:
    """Strip HTML tags and decode entities."""
    clean = re.sub(r"<[^>]+>", "", raw or "")
    return html.unescape(clean).strip()


def fetch_category(category: str, sources: list) -> list:
    """Fetch top N items from each source in a category."""
    items = []
    for source in sources:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:3]:
                title = clean_html(entry.get("title", "Untitled"))
                link = entry.get("link", "#")
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                if len(summary) > MAX_SUMMARY_LEN:
                    summary = summary[:MAX_SUMMARY_LEN] + "…"
                published = entry.get("published", "")
                items.append({
                    "source": source["name"],
                    "bias": source["bias"],
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": published,
                    "category": category,
                })
        except Exception as e:
            print(f"  [WARN] Failed to fetch {source['name']}: {e}")
    return items[:ITEMS_PER_CATEGORY * 2]


def generate_hitchens_question(headlines: list[str]) -> str:
    """Use Claude to generate today's Hitchens-esque provocation."""
    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        sample = "\n".join(f"- {h}" for h in headlines[:15])
        prompt = f"""You are channeling the spirit of Christopher Hitchens at his most combative and intellectually precise.

Today's top headlines:
{sample}

Generate ONE razor-sharp Hitchens-esque question or provocation — the kind of thing he would open a Vanity Fair column with. 
Make it uncomfortable. Make it specific. Make it demand honest thought.
Something that cuts through ideological comfort on ALL sides.
No more than 3 sentences. No hedging. No qualifications. Pure Hitchens.
Do not use his name. Just write as him."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"  [WARN] Claude API failed: {e}")
        return "If the truth requires no army of defenders, why does every government in history have a Ministry of Information?"


def build_json_feed(all_data: dict, hitchens_q: str, date_str: str) -> dict:
    """Build a clean JSON feed for external consumption."""
    return {
        "version": "The Daily Hitch 1.0",
        "generated": date_str,
        "hitchens_question": hitchens_q,
        "categories": {
            cat: [
                {
                    "source": item["source"],
                    "title": item["title"],
                    "link": item["link"],
                    "summary": item["summary"],
                    "bias": item["bias"],
                }
                for item in items
            ]
            for cat, items in all_data.items()
        }
    }


def bias_badge(bias: str) -> str:
    colors = {
        "neutral": "#4a9e6b",
        "investigative": "#e8a838",
        "investigative-left": "#e8a838",
        "hard-left": "#c0392b",
        "progressive": "#e74c3c",
        "anti-imperialist": "#c0392b",
        "liberal": "#e67e22",
        "conservative": "#2980b9",
        "nationalist-right": "#1a5276",
        "far-right": "#154360",
        "fin-dark": "#6c3483",
        "independent": "#16a085",
        "war-correspondent": "#ca6f1e",
        "osint": "#1abc9c",
        "defense": "#2c3e50",
        "defense-intel": "#2c3e50",
        "defense-security": "#2c3e50",
        "dod-adjacent": "#2c3e50",
        "analytical": "#7f8c8d",
        "establishment": "#7f8c8d",
        "libertarian": "#d4ac0d",
        "center-left": "#e67e22",
        "industry": "#3498db",
        "tech": "#3498db",
        "tech-left": "#2980b9",
        "tech-analytical": "#2980b9",
        "investigative-tech": "#e8a838",
        "leaks": "#ff4444",
        "peer-reviewed": "#27ae60",
        "science": "#27ae60",
    }
    color = colors.get(bias, "#555")
    return f'<span class="bias-badge" style="background:{color}22;color:{color};border:1px solid {color}44">{bias}</span>'


def render_category_section(category: str, items: list) -> str:
    if not items:
        return ""

    CATEGORY_ICONS = {
        "WIRE": "◈",
        "WAR & GEOPOLITICS": "⚔",
        "AEROSPACE & DEFENSE TECH": "✈",
        "UNDERGROUND & INVESTIGATIVE": "☠",
        "INDEPENDENTS & SUBSTACK": "⬡",
        "LEFT": "◀",
        "RIGHT": "▶",
        "THINK TANKS": "⬛",
        "AI & TECH": "◉",
        "SCIENCE": "⬟",
    }
    icon = CATEGORY_ICONS.get(category, "▸")

    items_html = ""
    for item in items:
        items_html += f"""
        <article class="feed-item">
          <div class="item-meta">
            <span class="source-name">{html.escape(item['source'])}</span>
            {bias_badge(item['bias'])}
          </div>
          <a href="{html.escape(item['link'])}" target="_blank" rel="noopener noreferrer" class="item-title">
            {html.escape(item['title'])}
          </a>
          <p class="item-summary">{html.escape(item['summary'])}</p>
        </article>"""

    return f"""
    <section class="category-block" id="{category.lower().replace(' ', '-').replace('&', 'and')}">
      <div class="category-header">
        <span class="category-icon">{icon}</span>
        <h2 class="category-title">{category}</h2>
        <div class="category-line"></div>
      </div>
      <div class="items-grid">
        {items_html}
      </div>
    </section>"""


def build_html(all_data: dict, hitchens_q: str, date_str: str) -> str:
    # Build the five-perspective bottom bar
    wire_items = all_data.get("WIRE", [])
    left_items = all_data.get("LEFT", [])
    right_items = all_data.get("RIGHT", [])
    underground_items = all_data.get("UNDERGROUND & INVESTIGATIVE", [])
    indie_items = all_data.get("INDEPENDENTS & SUBSTACK", [])

    def mini_list(items):
        return "".join(
            f'<li><a href="{html.escape(i["link"])}" target="_blank" rel="noopener noreferrer">{html.escape(i["title"][:80])}{"…" if len(i["title"])>80 else ""}</a></li>'
            for i in items[:4]
        )

    # Build all category sections
    all_sections = ""
    for cat, items in all_data.items():
        all_sections += render_category_section(cat, items)

    # Nav links
    nav_links = ""
    for cat in all_data.keys():
        anchor = cat.lower().replace(' ', '-').replace('&', 'and')
        nav_links += f'<a href="#{anchor}" class="nav-link">{cat}</a>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="robots" content="noindex, nofollow" />
  <title>THE DAILY HITCH — {date_str}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Bebas+Neue&family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,600;1,300&family=Playfair+Display:ital@1&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg:        #0a0a0a;
      --bg2:       #0f0f0f;
      --bg3:       #141414;
      --panel:     #111111;
      --border:    #1e2a1e;
      --green:     #00ff41;
      --green2:    #00cc33;
      --green3:    #007a1e;
      --green-dim: #00ff4120;
      --amber:     #ffb000;
      --red:       #ff3333;
      --text:      #c8d8c8;
      --text-dim:  #5a7a5a;
      --text-muted:#3a4a3a;
      --mono:      'IBM Plex Mono', monospace;
      --display:   'Bebas Neue', sans-serif;
      --terminal:  'Share Tech Mono', monospace;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--mono);
      font-size: 13px;
      line-height: 1.7;
      overflow-x: hidden;
    }}

    /* Scanline overlay */
    body::before {{
      content: '';
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(0,255,65,0.015) 2px,
        rgba(0,255,65,0.015) 4px
      );
      pointer-events: none;
      z-index: 9999;
    }}

    /* ── HEADER ── */
    .masthead {{
      border-bottom: 1px solid var(--green3);
      padding: 2rem 2rem 1.5rem;
      background: var(--bg);
      position: relative;
      overflow: hidden;
    }}

    .masthead::after {{
      content: '';
      position: absolute;
      bottom: 0; left: 0; right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--green), transparent);
    }}

    .dateline {{
      font-family: var(--terminal);
      font-size: 10px;
      color: var(--green2);
      letter-spacing: 0.3em;
      text-transform: uppercase;
      margin-bottom: 0.5rem;
    }}

    .masthead-title {{
      font-family: var(--display);
      font-size: clamp(3rem, 10vw, 7rem);
      color: var(--green);
      letter-spacing: 0.05em;
      line-height: 0.9;
      text-shadow: 0 0 40px rgba(0,255,65,0.3);
    }}

    .masthead-sub {{
      font-family: var(--terminal);
      font-size: 10px;
      color: var(--text-dim);
      letter-spacing: 0.4em;
      text-transform: uppercase;
      margin-top: 0.75rem;
    }}

    .masthead-quote {{
      font-family: 'Playfair Display', serif;
      font-style: italic;
      font-size: 0.85rem;
      color: var(--amber);
      margin-top: 1rem;
      max-width: 600px;
      border-left: 2px solid var(--amber);
      padding-left: 1rem;
      opacity: 0.8;
    }}

    /* ── NAV ── */
    .nav-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 0;
      border-bottom: 1px solid var(--border);
      background: var(--bg2);
      padding: 0 1rem;
      position: sticky;
      top: 0;
      z-index: 100;
    }}

    .nav-link {{
      font-family: var(--terminal);
      font-size: 9px;
      letter-spacing: 0.2em;
      color: var(--text-dim);
      text-decoration: none;
      padding: 0.6rem 0.75rem;
      border-right: 1px solid var(--border);
      text-transform: uppercase;
      transition: color 0.15s, background 0.15s;
    }}

    .nav-link:hover {{
      color: var(--green);
      background: var(--green-dim);
    }}

    /* ── MAIN LAYOUT ── */
    .container {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }}

    /* ── CATEGORY BLOCK ── */
    .category-block {{
      margin-bottom: 3rem;
      border: 1px solid var(--border);
      background: var(--panel);
    }}

    .category-header {{
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.75rem 1.25rem;
      border-bottom: 1px solid var(--border);
      background: var(--bg3);
    }}

    .category-icon {{
      font-size: 1rem;
      color: var(--green);
    }}

    .category-title {{
      font-family: var(--terminal);
      font-size: 11px;
      letter-spacing: 0.35em;
      color: var(--green2);
      text-transform: uppercase;
      white-space: nowrap;
    }}

    .category-line {{
      flex: 1;
      height: 1px;
      background: linear-gradient(90deg, var(--green3), transparent);
    }}

    .items-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 0;
    }}

    /* ── FEED ITEM ── */
    .feed-item {{
      padding: 1.25rem;
      border-right: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      transition: background 0.15s;
      position: relative;
    }}

    .feed-item:hover {{
      background: var(--green-dim);
    }}

    .feed-item::before {{
      content: '';
      position: absolute;
      left: 0; top: 0; bottom: 0;
      width: 2px;
      background: transparent;
      transition: background 0.15s;
    }}

    .feed-item:hover::before {{
      background: var(--green);
    }}

    .item-meta {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.5rem;
      flex-wrap: wrap;
    }}

    .source-name {{
      font-family: var(--terminal);
      font-size: 9px;
      letter-spacing: 0.2em;
      color: var(--green2);
      text-transform: uppercase;
    }}

    .bias-badge {{
      font-family: var(--terminal);
      font-size: 8px;
      letter-spacing: 0.1em;
      padding: 1px 6px;
      border-radius: 0;
      text-transform: uppercase;
    }}

    .item-title {{
      display: block;
      font-family: var(--mono);
      font-weight: 600;
      font-size: 13px;
      color: var(--text);
      text-decoration: none;
      margin-bottom: 0.5rem;
      line-height: 1.4;
      transition: color 0.15s;
    }}

    .item-title:hover {{
      color: var(--green);
    }}

    .item-summary {{
      font-size: 11px;
      color: var(--text-dim);
      line-height: 1.6;
      font-family: var(--mono);
      font-weight: 300;
    }}

    /* ── FIVE PERSPECTIVES BAR ── */
    .perspectives {{
      background: var(--bg2);
      border: 1px solid var(--border);
      border-top: 2px solid var(--green3);
      margin: 3rem 0;
    }}

    .perspectives-header {{
      font-family: var(--terminal);
      font-size: 9px;
      letter-spacing: 0.5em;
      color: var(--green);
      text-transform: uppercase;
      padding: 0.75rem 1.25rem;
      border-bottom: 1px solid var(--border);
    }}

    .perspectives-grid {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 0;
    }}

    @media (max-width: 900px) {{
      .perspectives-grid {{
        grid-template-columns: 1fr 1fr;
      }}
    }}

    @media (max-width: 500px) {{
      .perspectives-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .perspective-col {{
      padding: 1rem 1.25rem;
      border-right: 1px solid var(--border);
    }}

    .perspective-col:last-child {{
      border-right: none;
    }}

    .perspective-label {{
      font-family: var(--terminal);
      font-size: 8px;
      letter-spacing: 0.3em;
      color: var(--green2);
      text-transform: uppercase;
      margin-bottom: 0.75rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--border);
    }}

    .perspective-col ul {{
      list-style: none;
      padding: 0;
    }}

    .perspective-col ul li {{
      margin-bottom: 0.6rem;
      padding-left: 0.75rem;
      position: relative;
    }}

    .perspective-col ul li::before {{
      content: '▸';
      position: absolute;
      left: 0;
      color: var(--green3);
      font-size: 10px;
    }}

    .perspective-col ul li a {{
      color: var(--text-dim);
      text-decoration: none;
      font-size: 11px;
      line-height: 1.4;
      transition: color 0.15s;
    }}

    .perspective-col ul li a:hover {{
      color: var(--green);
    }}

    /* ── HITCHENS QUESTION ── */
    .hitchens-block {{
      background: var(--bg3);
      border: 1px solid var(--green3);
      border-left: 3px solid var(--green);
      padding: 2rem 2.5rem;
      margin: 3rem 0;
      position: relative;
      overflow: hidden;
    }}

    .hitchens-block::before {{
      content: '"';
      position: absolute;
      top: -1rem;
      left: 1rem;
      font-size: 8rem;
      color: var(--green-dim);
      font-family: 'Playfair Display', serif;
      line-height: 1;
    }}

    .hitchens-label {{
      font-family: var(--terminal);
      font-size: 9px;
      letter-spacing: 0.5em;
      color: var(--green2);
      text-transform: uppercase;
      margin-bottom: 1rem;
    }}

    .hitchens-text {{
      font-family: 'Playfair Display', serif;
      font-style: italic;
      font-size: clamp(1rem, 2.5vw, 1.35rem);
      color: var(--amber);
      line-height: 1.6;
      position: relative;
      z-index: 1;
    }}

    /* ── FOOTER ── */
    .footer {{
      border-top: 1px solid var(--border);
      padding: 1.5rem;
      font-family: var(--terminal);
      font-size: 9px;
      color: var(--text-muted);
      letter-spacing: 0.2em;
      text-align: center;
    }}

    .footer a {{
      color: var(--green3);
      text-decoration: none;
    }}

    /* ── BLINK CURSOR ── */
    .cursor {{
      display: inline-block;
      width: 8px;
      height: 14px;
      background: var(--green);
      animation: blink 1s step-end infinite;
      vertical-align: middle;
      margin-left: 4px;
    }}

    @keyframes blink {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0; }}
    }}

    /* ── SCROLLBAR ── */
    ::-webkit-scrollbar {{ width: 4px; }}
    ::-webkit-scrollbar-track {{ background: var(--bg); }}
    ::-webkit-scrollbar-thumb {{ background: var(--green3); }}
  </style>
</head>
<body>

<header class="masthead">
  <div class="dateline">CLASSIFIED // EYES ONLY // {date_str} // BRIEFING CYCLE 0600</div>
  <div class="masthead-title">THE DAILY HITCH<span class="cursor"></span></div>
  <div class="masthead-sub">Underground Intelligence Digest — All Perspectives — No Filters — No Masters</div>
  <div class="masthead-quote">
    "The essence of the independent mind lies not in what it thinks, but in how it thinks."
  </div>
</header>

<nav class="nav-bar">
  {nav_links}
</nav>

<main class="container">

  <!-- HITCHENS QUESTION OF THE DAY -->
  <div class="hitchens-block">
    <div class="hitchens-label">◈ HITCHENS QUESTION OF THE DAY</div>
    <div class="hitchens-text">{html.escape(hitchens_q)}</div>
  </div>

  <!-- FIVE PERSPECTIVES -->
  <div class="perspectives">
    <div class="perspectives-header">◈ THE FIVE PERSPECTIVES</div>
    <div class="perspectives-grid">
      <div class="perspective-col">
        <div class="perspective-label">WHAT THE WIRE SAYS</div>
        <ul>{mini_list(wire_items)}</ul>
      </div>
      <div class="perspective-col">
        <div class="perspective-label">WHAT THE LEFT SAYS</div>
        <ul>{mini_list(left_items)}</ul>
      </div>
      <div class="perspective-col">
        <div class="perspective-label">WHAT THE RIGHT SAYS</div>
        <ul>{mini_list(right_items)}</ul>
      </div>
      <div class="perspective-col">
        <div class="perspective-label">WHAT THE UNDERGROUND SAYS</div>
        <ul>{mini_list(underground_items)}</ul>
      </div>
      <div class="perspective-col">
        <div class="perspective-label">WHAT THE INDEPENDENTS SAY</div>
        <ul>{mini_list(indie_items)}</ul>
      </div>
    </div>
  </div>

  <!-- ALL CATEGORY SECTIONS -->
  {all_sections}

</main>

<footer class="footer">
  THE DAILY HITCH — {date_str} — GENERATED {datetime.now(timezone.utc).strftime('%H:%M UTC')} —
  <a href="feed.json">JSON FEED</a> —
  NO TRACKING. NO ADS. NO MASTERS.
</footer>

</body>
</html>"""


def main():
    date_str = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    print(f"[THE DAILY HITCH] Building briefing for {date_str}")

    all_data = {}
    all_headlines = []

    for category, sources in SOURCES.items():
        print(f"  Fetching: {category}")
        items = fetch_category(category, sources)
        all_data[category] = items
        all_headlines.extend([i["title"] for i in items])

    print("  Generating Hitchens Question via Claude API...")
    hitchens_q = generate_hitchens_question(all_headlines)
    print(f"  Question: {hitchens_q[:80]}...")

    # Write HTML
    html_output = build_html(all_data, hitchens_q, date_str)
    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "index.html").write_text(html_output, encoding="utf-8")
    print("  Written: docs/index.html")

    # Write JSON feed
    feed_data = build_json_feed(all_data, hitchens_q, date_str)
    (out_dir / "feed.json").write_text(json.dumps(feed_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  Written: docs/feed.json")

    print("[DONE] The Daily Hitch briefing generated.")


if __name__ == "__main__":
    main()
