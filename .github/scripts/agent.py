#!/usr/bin/env python3
"""
Athena v2 — Buyer-decision article agent for Amazon Associates.
Focus: comparison / best-of / vs-style reviews with high purchase intent.
No database, no scheduler. One script, two platforms.
"""
import hashlib, json, os, random, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY   = os.environ["DEEPSEEK_API_KEY"]
DEVTO_KEY = os.environ.get("DEVTO_API_KEY", "")
INDEXNOW_KEY = "0624a5ea55dc48afaefbe5ce8393c490"
SITE_URL = "https://lena2099.github.io/tech-tools-hub"
DRY_RUN   = os.environ.get("DRY_RUN", "") == "1"
OUT_DIR   = Path("_posts")

# ── CONFIG: BUYER-INTENT TOPICS ───────────────────────────
# Each topic maps to a product category + Amazon browse node
TOPICS = [
    {
        "slug": "noise-cancelling-headphones",
        "category": "Noise-Cancelling Headphones",
        "angles": [
            "Best Noise-Cancelling Headphones Under $100",
            "Best Premium ANC Headphones Compared",
            "Best Budget Wireless Earbuds with ANC",
            "Best Headphones for Remote Work & Zoom Calls",
            "Over-Ear vs In-Ear Noise Cancelling: Which to Buy",
        ],
    },
    {
        "slug": "budget-smartphones",
        "category": "Budget Smartphones",
        "angles": [
            "Best Smartphones Under $500",
            "Best Camera Phones Under $400",
            "Best Budget Android Phones for 2026",
            "Refurbished vs New: Best Phone Deals",
            "Best Phones for Gaming Under $300",
        ],
    },
    {
        "slug": "home-office-gear",
        "category": "Home Office Gear",
        "angles": [
            "Best Standing Desk & Ergonomic Chair Combos",
            "Best Budget Monitor for Programming & Design",
            "Best Webcam & Mic Setup for Video Calls",
            "Best Ergonomic Keyboard & Mouse for All-Day Use",
            "Best Desk Lamps & Lighting for Eye Comfort",
        ],
    },
    {
        "slug": "smart-home-devices",
        "category": "Smart Home Devices",
        "angles": [
            "Best Smart Home Starter Kit Under $200",
            "Best Video Doorbell & Security Cameras",
            "Best Smart Plugs & Lights for Beginners",
            "Best Smart Speakers: Echo vs Nest vs HomePod",
            "Best Robot Vacuums Under $400",
        ],
    },
    {
        "slug": "ereaders-tablets",
        "category": "eReaders & Tablets",
        "angles": [
            "Kindle vs Kobo vs reMarkable: Which eReader",
            "Best Budget Tablet for Reading & Note-Taking",
            "Best Tablet for Kids: Parent's Guide",
            "Best iPad Alternatives Under $300",
            "Best eReader for Students & Academics",
        ],
    },
    {
        "slug": "wearables-fitness",
        "category": "Wearables & Fitness Tech",
        "angles": [
            "Best Fitness Tracker Under $100",
            "Best Smartwatch for iPhone vs Android Users",
            "Best Sleep Trackers & Rings Compared",
            "Best Running Headphones & Earbuds",
            "Best Smart Scale & Health Monitors",
        ],
    },
    {
        "slug": "portable-audio",
        "category": "Portable Audio",
        "angles": [
            "Best Bluetooth Speakers Under $80",
            "Best Portable Speaker for Beach & Outdoors",
            "JBL vs Bose vs Sony: Best Portable Sound",
            "Best Mini Speaker for Desk & Travel",
            "Best Party Speaker with Bass",
        ],
    },
    {
        "slug": "charging-accessories",
        "category": "Charging & Accessories",
        "angles": [
            "Best USB-C Charging Station for Multi-Device",
            "Best Portable Power Bank for Travel",
            "Best GaN Chargers: Anker vs Ugreen vs Satechi",
            "Best MagSafe Accessories for iPhone",
            "Best Cable Organizers & Desk Management",
        ],
    },
]

# Amazon affiliate tag
AMZN_TAG = "technolo0b423-20"

# Subscription bounties (PA API product links, NOT search redirects)
AMZN_SUBS = [
    ("Kindle Unlimited", "https://www.amazon.com/kindle-dbs/hz/subscribe/ku?tag=technolo0b423-20",
     "Free 30-day trial, unlimited reading"),
    ("Audible Premium Plus", "https://www.audible.com/ep/affiliate?tag=technolo0b423-20",
     "Free 30-day trial, 1 free audiobook"),
    ("Amazon Prime", "https://www.amazon.com/amazonprime?tag=technolo0b423-20",
     "Free 30-day trial, free shipping + Prime Video"),
    ("Amazon Music Unlimited", "https://www.amazon.com/music/unlimited?tag=technolo0b423-20",
     "Free 30-day trial, 100M songs"),
]


# ── LLM CALL ──────────────────────────────────────────────
def call_deepseek(messages, max_tokens=2048, temperature=0.7):
    req = Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps({
            "model": "deepseek-chat",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    resp = json.loads(urlopen(req, timeout=120).read())
    return resp["choices"][0]["message"]["content"]


# ── TOPIC ROTATION ───────────────────────────────────────
def pick_topic_and_angle():
    """Pick next topic and a fresh angle, avoiding recent repeats."""
    now = datetime.now(timezone.utc)
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True) if OUT_DIR.exists() else []

    # Get last-used slugs
    recent_slugs = []
    for p in posts[:5]:
        content = p.read_text()
        for line in content.split("\n"):
            if line.startswith("categories:"):
                recent_slugs.append(line.split(":", 1)[1].strip())
                break

    # Pick least-recently-used topic
    available = [t for t in TOPICS if t["slug"] not in recent_slugs[:2]]
    if not available:
        available = TOPICS
    topic = available[random.randint(0, len(available) - 1)]

    # Pick angle not used in last 2 articles for this slug
    used_angles = set()
    for p in posts:
        content = p.read_text()
        for line in content.split("\n"):
            if line.startswith("title:"):
                used_angles.add(line.split(":", 1)[1].strip().strip('"'))
                break

    fresh_angles = [a for a in topic["angles"] if a not in used_angles]
    if not fresh_angles:
        fresh_angles = topic["angles"]
    angle = fresh_angles[random.randint(0, len(fresh_angles) - 1)]

    return topic, angle


# ── ARTICLE GENERATION ────────────────────────────────────
def generate_article(topic: dict, angle: str):
    current_date = datetime.now(timezone.utc)
    month_year = current_date.strftime("%B %Y")
    this_year = current_date.strftime("%Y")

    subs_text = "\n".join(
        f"  - {name}: {url} ({desc})" for name, url, desc in AMZN_SUBS
    )

    prompt = f"""Write a BUYER-DECISION blog article. The reader is shopping — help them choose.

VOICE RULES — THIS IS THE MOST IMPORTANT PART:
- Write like a real person who actually owns and uses tech products. First-person, casual, opinionated.
- NEVER use these AI phrases: "You're looking for X but the market is confusing/overwhelming", "After hours of testing", "the truth is", "game-changer", "revolutionary", "whether you're on a budget or want premium", "let's dive deep", "without further ado".
- DON'T sound like a marketing copywriter. Sound like someone texting a friend about what to buy.
- Include at least one personal experience detail: a specific thing that annoyed you, a feature you didn't expect to use but now love, something you returned.
- Every product should have at least one honest CON: not just "no backlight", but real stuff — "the software requires an account just to remap keys", "the ear tips don't fit small ears".
- Use contractions (don't, can't, I've, you're). Short paragraphs. 40-80 words max per paragraph.
- READABILITY: grade 8-10. Short sentences. No corporate buzzwords.
- NEVER lie. Don't say "I tested" if you haven't. Say "most reviewers report" or "based on specs".

CONTENT RULES:
- Today is {current_date.strftime('%B %d, %Y')}. ONLY real, currently-available products. No 2024 models unless they're still sold new.
- This is a shopping guide, not a tutorial.
- Mention 3-4 products max. Not 5. Quality over quantity.
- EVERY product link MUST be an Amazon search link: https://www.amazon.com/s?k=Exact+Product+Name&tag=technolo0b423-20 — NEVER invent fake ASINs.
- NO comparison table with fake star ratings. Instead, describe differences in plain sentences.
- NO numbered list of features. Tell me what matters, not everything.
- Skip the "Quick Picks" box. Skip the "Verdict" with "Best Overall/Budget/Premium" labels. Just tell the reader what to buy and why.
- FAQ section: 2 questions max. Keep answers 2-3 sentences.
- Mention subscriptions ONLY if genuinely relevant. Don't cram Kindle Unlimited into a keyboard review.
- Affiliate disclosure at the very end: "*As an Amazon Associate, I earn from qualifying purchases.*"

ARTICLE INFO:
- Title: {angle} — keep it under 60 chars, include {this_year}
- Category: {topic['category']}
- Length: 600-900 words. Short is better than padded.

STRUCTURE (flexible — don't follow this rigidly):
1. Opening: personal anecdote or strong opinion. Not a generic "market is confusing" hook.
2. What actually matters: 2-3 things buyers overlook but should know.
3. Product recommendations: 3-4 products, 100-150 words each, with honest pros and cons.
4. Closing: one sentence telling the reader which one to buy and why.
5. FAQ: 2 questions.
6. Disclosure line.

OUTPUT: ONLY a JSON object:
{{"title": "...", "slug": "url-friendly-slug", "meta_description": "150-160 chars", "tags": ["tag1","tag2"], "content": "FULL # markdown article"}}"""

    text = call_deepseek([{"role": "user", "content": prompt}], max_tokens=3072, temperature=0.7)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            article = json.loads(match.group())
            article["word_count"] = len(article["content"].split())
            return article
        except json.JSONDecodeError:
            pass

    lines = text.strip().split("\n")
    title = lines[0].lstrip("# ").strip()[:65]
    return {"title": title, "slug": re.sub(r"[^a-z0-9]+", "-", title.lower())[:60],
            "meta_description": f"Best {topic['category']} for {this_year}. Expert comparison & buying guide.",
            "tags": ["review", "buying-guide", "tech"],
            "content": text, "word_count": len(text.split())}


# ── DEV.TO PUBLISH ───────────────────────────────────────
def publish_to_devto(article, topic: dict):
    if not DEVTO_KEY:
        return {"status": "skipped", "reason": "no api key"}
    payload = {"article": {
        "title": article["title"],
        "body_markdown": article["content"],
        "published": True,
        "tags": _pick_devto_tags(topic, article.get("tags", [])),
        "description": article.get("meta_description", ""),
        "canonical_url": f"{SITE_URL}/",
    }}
    try:
        req = Request("https://dev.to/api/articles",
                      data=json.dumps(payload).encode(),
                      headers={"api-key": DEVTO_KEY, "Content-Type": "application/json",
                               "User-Agent": "Mozilla/5.0 (compatible; Athena/2.0; +https://lena2099.github.io/tech-tools-hub)"},
                      method="POST")
        resp = json.loads(urlopen(req, timeout=30).read())
        return resp if "url" in resp else {"status": "failed", "error": str(resp)[:200]}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


def _pick_devto_tags(topic: dict, article_tags: list) -> list:
    boost_map = {
        "noise-cancelling-headphones": ["reviews", "headphones", "tech"],
        "budget-smartphones": ["reviews", "android", "tech"],
        "home-office-gear": ["productivity", "reviews", "tech"],
        "smart-home-devices": ["iot", "reviews", "tech"],
        "ereaders-tablets": ["reviews", "books", "tech"],
        "wearables-fitness": ["reviews", "fitness", "tech"],
        "portable-audio": ["reviews", "music", "tech"],
        "charging-accessories": ["reviews", "tech", "tutorial"],
    }
    clean = []
    for t in article_tags:
        tag = re.sub(r"[^a-z0-9]", "", t.strip().lower())[:25]
        if tag and tag not in clean:
            clean.append(tag)
    for b in boost_map.get(topic["slug"], ["reviews", "tech"]):
        if b not in clean:
            clean.append(b)
    return clean[:4]


# ── SAVE AS JEKYLL POST ──────────────────────────────────
def save_jekyll_post(article, topic: dict):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = article["slug"]
    filename = f"{date_str}-{slug}.md"
    path = OUT_DIR / filename
    if path.exists():
        print(f"⚠️  Already exists: {filename}")
        return None
    tags = "\n".join(f"  - {t}" for t in article.get("tags", [])[:5])
    frontmatter = f"""---
layout: post
title: "{article['title']}"
date: {datetime.now(timezone.utc).isoformat()}
categories: {topic['slug']}
tags:
{tags}
description: "{article.get('meta_description', '')}"
---
"""
    path.write_text(frontmatter + article["content"])
    print(f"✅ Jekyll post: {filename}")
    return path


# ── CROSS-LINKING ────────────────────────────────────────
def get_recent_posts(exclude_slug: str = "", count: int = 3) -> list[dict]:
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True) if OUT_DIR.exists() else []
    result = []
    for p in posts:
        if len(result) >= count:
            break
        if exclude_slug and exclude_slug in p.stem:
            continue
        content = p.read_text()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].split("\n"):
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"')
                        parts2 = p.stem.split("-", 3)
                        if len(parts2) >= 4:
                            url = f"{SITE_URL}/{parts2[0]}/{parts2[1]}/{parts2[2]}/{parts2[3]}.html"
                            result.append({"title": title, "url": url})
                        break
    return result


def append_cross_links(content: str, current_slug: str) -> str:
    recent = get_recent_posts(exclude_slug=current_slug, count=3)
    if len(recent) < 2:
        return content
    links_md = "\n".join(f"- [{p['title']}]({p['url']})" for p in recent)
    return content + f"\n\n---\n\n### 📚 Related Buying Guides\n\n{links_md}"


# ── SEO FILES ─────────────────────────────────────────────
def generate_sitemap():
    posts = sorted(OUT_DIR.glob("*.md")) if OUT_DIR.exists() else []
    if not posts:
        return
    urls = [f"""  <url>
    <loc>{SITE_URL}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""]
    for p in posts:
        parts = p.stem.split("-", 3)
        if len(parts) >= 4:
            url = f"{SITE_URL}/{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}.html"
            urls.append(f"""  <url>
    <loc>{url}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")
    Path("sitemap.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
""")
    print(f"   sitemap.xml: {len(urls)} URLs")


def generate_robots():
    Path("robots.txt").write_text(f"""User-agent: *
Allow: /
Sitemap: {SITE_URL}/sitemap.xml
""")


def ping_search_engines(article: dict):
    sitemap_url = f"{SITE_URL}/sitemap.xml"
    article_url = article.get("canonical_url", "")
    indexnow_payload = json.dumps({
        "host": "lena2099.github.io", "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": [article_url, sitemap_url],
    }).encode()
    try:
        resp = urlopen(Request("https://api.indexnow.org/indexnow",
                               data=indexnow_payload,
                               headers={"Content-Type": "application/json"}), timeout=10)
        print(f"   IndexNow: HTTP {resp.getcode()}")
    except Exception as e:
        print(f"   IndexNow: {e}")
    try:
        urlopen(Request(f"https://www.google.com/ping?sitemap={sitemap_url}"), timeout=10)
        print("   Google: pinged")
    except Exception as e:
        print(f"   Google ping: {e}")


# ── MAIN ─────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  🦉 Athena v2 — Buyer-Decision Article Agent")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    topic, angle = pick_topic_and_angle()
    print(f"\n📝 Category: {topic['category']}")
    print(f"🎯 Angle: {angle}")

    print("✍️  Writing article...")
    article = generate_article(topic, angle)
    print(f"   Title: {article['title']}")
    print(f"   Words: {article['word_count']}")

    print("🔗 Cross-linking...")
    article["content"] = append_cross_links(article["content"], article.get("slug", ""))

    post_path = save_jekyll_post(article, topic)
    if post_path is None:
        print("\n⏭️  Already published — skipping.")
        return

    if not DRY_RUN:
        print("📤 Publishing to Dev.to...")
        result = publish_to_devto(article, topic)
        print(f"   Dev.to: {result}")
    else:
        print("🏜️  DRY_RUN — skipping Dev.to")

    if post_path:
        print("🔍 Updating SEO...")
        generate_sitemap()
        generate_robots()
        print("   Sitemap + robots.txt updated")

    if post_path and not DRY_RUN:
        ping_search_engines(article)

    print("\n✨ Done. Next run in ~4 hours.")


if __name__ == "__main__":
    main()
