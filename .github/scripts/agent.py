#!/usr/bin/env python3
"""
Athena — Single-file autonomous article agent for GitHub Actions.
No database, no scheduler, no Playwright. One script, two platforms.
"""
import hashlib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY   = os.environ["DEEPSEEK_API_KEY"]
DEVTO_KEY = os.environ.get("DEVTO_API_KEY", "")
DRY_RUN   = os.environ.get("DRY_RUN", "") == "1"
OUT_DIR   = Path("_posts")

# ── CONFIG ────────────────────────────────────────────────
TOPICS = [
    "AI tools & tutorials",
    "personal productivity",
    "remote work & freelancing",
    "tech reviews",
    "side hustle strategies",
]

AFFILIATE_LINKS = {
    "AI tools & tutorials": [
        ("Jasper AI",   "https://www.amazon.com/dp/B0C1N5P6QK?tag=technolo0b423-20"),
        ("Notion AI",   "https://affiliate.notion.so/"),
        ("Sudowrite",   "https://www.sudowrite.com/"),
    ],
    "personal productivity": [
        ("Notion",      "https://affiliate.notion.so/"),
        ("Todoist",     "https://todoist.com/"),
        ("Toggl Track", "https://toggl.com/track/"),
    ],
    "remote work & freelancing": [
        ("Fiverr",      "https://www.fiverr.com/"),
        ("Upwork",      "https://www.upwork.com/"),
        ("Zoom",        "https://zoom.us/"),
    ],
    "tech reviews": [
        ("M1 MacBook Air",  "https://www.amazon.com/dp/B08N5KWB9H?tag=technolo0b423-20"),
        ("Keychron K8",     "https://www.amazon.com/dp/B08PZ8F88K?tag=technolo0b423-20"),
        ("LG UltraFine",    "https://www.amazon.com/dp/B088G1PKKN?tag=technolo0b423-20"),
    ],
    "side hustle strategies": [
        ("Gumroad",     "https://gumroad.com/"),
        ("Substack",    "https://substack.com/"),
        ("Shopify",     "https://www.shopify.com/"),
    ],
}

# ── LLM CALL ──────────────────────────────────────────────
def call_deepseek(messages, max_tokens=2048, temperature=0.7):
    """Call DeepSeek API (OpenAI-compatible)."""
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
def pick_topic():
    """Pick topic, avoiding the one just used."""
    posts = sorted(OUT_DIR.glob("*.md")) if OUT_DIR.exists() else []
    if not posts:
        return TOPICS[0]
    with open(posts[-1]) as f:
        for line in f:
            if line.startswith("categories:"):
                last_topic = line.split(":", 1)[1].strip()
                if last_topic in TOPICS:
                    idx = TOPICS.index(last_topic)
                    return TOPICS[(idx + 1) % len(TOPICS)]
                break
    return TOPICS[0]


# ── KEYWORDS ─────────────────────────────────────────────
def generate_keywords(topic):
    prompt = f"""Generate 3 long-tail SEO keywords for a blog article about "{topic}".
Return ONLY a JSON array of strings. Example: ["best ai writing tools 2024", "ai tool comparison"]"""
    try:
        text = call_deepseek([{"role": "user", "content": prompt}], max_tokens=200)
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except:
        pass
    return [f"best {topic}", f"{topic} guide", f"{topic} 2024"]


# ── ARTICLE GENERATION ────────────────────────────────────
def generate_article(topic, keywords):
    kw_str = ", ".join(keywords[:3])
    links = AFFILIATE_LINKS.get(topic, [])
    link_hints = ", ".join(f"{name}({url})" for name, url in links)

    prompt = f"""Write a high-quality, SEO-optimized blog article in English.

Topic: {topic}
Keywords to naturally integrate: {kw_str}
Length: 800-1500 words
Format: Markdown with ## and ### headings
Tone: informative, engaging, actionable
Structure: Hook → Problem → Solution → Step-by-step → Comparison table → Conclusion
Important: naturally mention these products where relevant: {link_hints}

OUTPUT: ONLY a JSON object, no markdown outside it:
{{"title": "SEO title (55-65 chars)", "slug": "url-friendly-slug", "meta_description": "150-160 char meta", "tags": ["tag1","tag2","tag3"], "content": "full # markdown ## article ### here"}}"""

    text = call_deepseek([{"role": "user", "content": prompt}], max_tokens=4096, temperature=0.7)

    # Extract JSON
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            article = json.loads(match.group())
            article["word_count"] = len(article["content"].split())
            return article
        except json.JSONDecodeError:
            pass

    # Fallback
    lines = text.strip().split("\n")
    title = lines[0].lstrip("# ").strip()[:65]
    return {"title": title, "slug": re.sub(r"[^a-z0-9]+", "-", title.lower())[:60],
            "meta_description": f"Complete guide to {topic}.", "tags": topic.split(" & "),
            "content": text, "word_count": len(text.split())}


# ── AFFILIATE LINK INSERTION ─────────────────────────────
def insert_affiliate_links(content, topic):
    links = AFFILIATE_LINKS.get(topic, [])
    inserted = False
    for name, url in links:
        if name in content and f"[{name}]" not in content:
            content = content.replace(name, f"[{name}]({url})", 1)
            inserted = True
    if inserted:
        content += "\n\n---\n\n*This article contains affiliate links. I may earn a commission at no extra cost to you.*"
    return content


def _clean_tag(tag: str) -> str:
    """Dev.to tags: lowercase, alphanumeric, max 25 chars, no spaces."""
    clean = re.sub(r"[^a-z0-9]", "", tag.strip().lower())
    return clean[:25] if clean else "tech"


# ── DEV.TO PUBLISH ───────────────────────────────────────
def publish_to_devto(article, topic):
    if not DEVTO_KEY:
        return {"status": "skipped", "reason": "no api key"}
    payload = {"article": {
        "title": article["title"],
        "body_markdown": article["content"],
        "published": True,
        "tags": _pick_devto_tags(topic, article.get("tags", [])),
        "description": article.get("meta_description", ""),
    }}
    try:
        req = Request("https://dev.to/api/articles",
                      data=json.dumps(payload).encode(),
                      headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
                      method="POST")
        resp = json.loads(urlopen(req, timeout=30).read())
        if "url" in resp:
            return {"status": "published", "url": resp["url"]}
        return {"status": "failed", "error": str(resp)[:200]}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


# ── DEV.TO TAG STRATEGY ──────────────────────────────────
# Boost discoverability by always including these high-traffic tags
BOOST_TAGS = {
    "AI tools & tutorials":       ["ai", "tutorial", "productivity"],
    "personal productivity":      ["productivity", "tutorial", "career"],
    "remote work & freelancing":  ["career", "productivity", "beginners"],
    "tech reviews":               ["programming", "webdev", "tutorial"],
    "side hustle strategies":     ["career", "beginners", "productivity"],
}


def _pick_devto_tags(topic: str, article_tags: list[str]) -> list:
    """Smart tag selection: content tags + high-traffic boost tags. Max 4."""
    clean = []
    for t in article_tags:
        tag = re.sub(r"[^a-z0-9]", "", t.strip().lower())[:25]
        if tag and tag not in clean:
            clean.append(tag)

    boost = BOOST_TAGS.get(topic, [])
    for b in boost:
        if b not in clean:
            clean.append(b)

    return clean[:4]


# ── SAVE AS JEKYLL POST ──────────────────────────────────
def save_jekyll_post(article, topic):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = article["slug"]
    filename = f"{date_str}-{slug}.md"
    path = OUT_DIR / filename

    # Check duplicate
    if path.exists():
        print(f"⚠️  Post already exists: {filename}")
        return None

    tags = "\n".join(f"  - {t}" for t in article.get("tags", [])[:5])
    frontmatter = f"""---
layout: post
title: "{article['title']}"
date: {datetime.now(timezone.utc).isoformat()}
categories: {topic}
tags:
{tags}
description: "{article.get('meta_description', '')}"
---

"""
    path.write_text(frontmatter + article["content"])
    print(f"✅ Jekyll post: {filename}")
    return path


# ── MAIN ─────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  🦉 Athena — Article Agent")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # 1. Pick topic
    topic = pick_topic()
    print(f"\n📝 Topic: {topic}")

    # 2. Keywords
    print("🔑 Generating keywords...")
    keywords = generate_keywords(topic)
    print(f"   {keywords}")

    # 3. Generate article
    print("✍️  Writing article...")
    article = generate_article(topic, keywords)
    print(f"   Title: {article['title']}")
    print(f"   Words: {article['word_count']}")

    # 4. Insert affiliate links
    print("💰 Inserting affiliate links...")
    article["content"] = insert_affiliate_links(article["content"], topic)

    # 4.5. Append cross-links to related posts
    article["content"] = append_cross_links(article["content"], article.get("slug", ""))

    # 5. Save as Jekyll post
    post_path = save_jekyll_post(article, topic)
    if post_path is None:
        print("\n⏭️  Already published — skipping.")
        return

    # 6. Publish to Dev.to
    if not DRY_RUN:
        print("📤 Publishing to Dev.to...")
        result = publish_to_devto(article, topic)
        print(f"   Dev.to: {result}")
    else:
        print("🏜️  DRY_RUN mode — skipping Dev.to publish")

    # 7. Regenerate SEO files
    if post_path:
        print("🔍 Updating SEO files...")
        generate_sitemap()
        generate_robots()
        print("   Sitemap + robots.txt updated")

    print("\n✨ Done. Next run in ~4 hours.")


# ── CROSS-LINKING ────────────────────────────────────────
def get_recent_posts(exclude_slug: str = "", count: int = 3) -> list[dict]:
    """Get recent posts for cross-linking, excluding the current one."""
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True) if OUT_DIR.exists() else []
    result = []
    for p in posts:
        if len(result) >= count:
            break
        if exclude_slug and exclude_slug in p.stem:
            continue
        # Extract title from frontmatter
        content = p.read_text()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].split("\n"):
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"')
                        parts2 = p.stem.split("-", 3)
                        if len(parts2) >= 4:
                            y, m, d, slug = parts2[0], parts2[1], parts2[2], parts2[3]
                            url = f"{SITE_URL}/{y}/{m}/{d}/{slug}.html"
                            result.append({"title": title, "url": url})
                        break
    return result


def append_cross_links(content: str, current_slug: str) -> str:
    """Append 'Related Posts' cross-links to the article."""
    recent = get_recent_posts(exclude_slug=current_slug, count=3)
    if len(recent) < 2:
        return content

    links_md = "\n".join(f"- [{p['title']}]({p['url']})" for p in recent)
    return content + f"""

---

### 📚 Related Posts

{links_md}"""


# ── SEO: SITEMAP ─────────────────────────────────────────
SITE_URL = "https://lena2099.github.io/tech-tools-hub"


def generate_sitemap():
    """Generate sitemap.xml from all _posts/*.md files."""
    posts = sorted(OUT_DIR.glob("*.md")) if OUT_DIR.exists() else []
    if not posts:
        return

    urls = []
    # Homepage
    urls.append(f"""  <url>
    <loc>{SITE_URL}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>""")

    for p in posts:
        # Derive URL from filename: YYYY-MM-DD-slug.md
        name = p.stem
        parts = name.split("-", 3)
        if len(parts) >= 4:
            year, month, day, slug = parts[0], parts[1], parts[2], parts[3]
            url = f"{SITE_URL}/{year}/{month}/{day}/{slug}.html"
            urls.append(f"""  <url>
    <loc>{url}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")

    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
"""
    Path("sitemap.xml").write_text(sitemap)
    print(f"   sitemap.xml: {len(urls)} URLs")


# ── SEO: ROBOTS.TXT ──────────────────────────────────────
def generate_robots():
    robots = f"""User-agent: *
Allow: /
Sitemap: {SITE_URL}/sitemap.xml
"""
    Path("robots.txt").write_text(robots)


if __name__ == "__main__":
    main()
