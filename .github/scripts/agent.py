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
        ("Jasper AI",   "https://www.jasper.ai/?fpr=affiliate"),
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
        ("M1 MacBook Air",  "https://amzn.to/affiliate-macbook"),
        ("Keychron K8",     "https://amzn.to/affiliate-keychron"),
        ("LG UltraFine",    "https://amzn.to/affiliate-monitor"),
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


# ── DEV.TO PUBLISH ───────────────────────────────────────
def publish_to_devto(article):
    if not DEVTO_KEY:
        return {"status": "skipped", "reason": "no api key"}
    payload = {"article": {
        "title": article["title"],
        "body_markdown": article["content"],
        "published": True,
        "tags": [t.strip().lower()[:30] for t in article.get("tags", [])[:4]],
        "description": article.get("meta_description", ""),
    }}
    req = Request("https://dev.to/api/articles",
                  data=json.dumps(payload).encode(),
                  headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
                  method="POST")
    resp = json.loads(urlopen(req, timeout=30).read())
    if "url" in resp:
        return {"status": "published", "url": resp["url"]}
    return {"status": "failed", "error": str(resp)[:200]}


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

    # 5. Save as Jekyll post
    post_path = save_jekyll_post(article, topic)
    if post_path is None:
        print("\n⏭️  Already published — skipping.")
        return

    # 6. Publish to Dev.to
    if not DRY_RUN:
        print("📤 Publishing to Dev.to...")
        result = publish_to_devto(article)
        print(f"   Dev.to: {result}")
    else:
        print("🏜️  DRY_RUN mode — skipping Dev.to publish")

    print("\n✨ Done. Next run in ~4 hours.")

if __name__ == "__main__":
    main()
