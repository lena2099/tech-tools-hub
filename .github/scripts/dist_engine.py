#!/usr/bin/env python3
"""
Distribution Engine — Multi-channel content syndication.
Runs after seo_engine.py. Pushes to Dev.to, generates RSS enhancement,
prepares social media payloads.
"""
import json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SITE_URL = "https://lena2099.github.io/tech-tools-hub"
OUT_DIR = Path("_posts")
DIST_DIR = Path("_dist")

# Channel keys — from env (secrets)
DEVTO_KEY = os.environ.get("DEVTO_API_KEY", "")
MEDIUM_TOKEN = os.environ.get("MEDIUM_TOKEN", "")
TWITTER_BEARER = os.environ.get("TWITTER_BEARER_TOKEN", "")


# ══════════════════════════════════════════════════════════
# 1. DEV.TO CROSS-POST with canonical URL
# ══════════════════════════════════════════════════════════
BOOST_TAGS = {
    "noise-cancelling-headphones": ["audio", "reviews", "headphones"],
    "budget-smartphones": ["android", "reviews", "mobile"],
    "home-office-gear": ["productivity", "reviews", "workspace"],
    "smart-home-devices": ["iot", "reviews", "smarthome"],
    "ereaders-tablets": ["books", "reviews", "tablet"],
    "wearables-fitness": ["fitness", "reviews", "wearables"],
    "portable-audio": ["audio", "reviews", "music"],
    "charging-accessories": ["tech", "reviews", "accessories"],
}


def publish_to_devto(article_path: Path, category_slug: str) -> dict:
    """Publish a Jekyll post to Dev.to with canonical URL pointing back."""
    if not DEVTO_KEY:
        return {"status": "skipped", "reason": "no DEVTO_API_KEY"}

    content = article_path.read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {"status": "failed", "reason": "invalid frontmatter"}

    # Parse frontmatter
    title = desc = ""
    for line in parts[1].split("\n"):
        if line.startswith("title:"): title = line.split(":", 1)[1].strip().strip('"')
        if line.startswith("description:"): desc = line.split(":", 1)[1].strip().strip('"')
    body = parts[2]

    # Strip JSON-LD from body (Dev.to doesn't render <script>)
    body_clean = re.sub(r'<script type="application/ld\+json">.*?</script>', '', body, flags=re.DOTALL)

    # Build canonical URL
    pname = article_path.stem
    p_parts = pname.split("-", 3)
    canonical = f"{SITE_URL}/{p_parts[0]}/{p_parts[1]}/{p_parts[2]}/{p_parts[3]}.html" if len(p_parts) >= 4 else SITE_URL

    tags = BOOST_TAGS.get(category_slug, ["reviews", "tech"])[:4]

    payload = {"article": {
        "title": title,
        "body_markdown": body_clean.strip(),
        "published": True,
        "tags": tags,
        "description": desc[:160],
        "canonical_url": canonical,
    }}

    try:
        req = Request("https://dev.to/api/articles",
                      data=json.dumps(payload).encode(),
                      headers={
                          "api-key": DEVTO_KEY,
                          "Content-Type": "application/json",
                          "User-Agent": f"Mozilla/5.0 (compatible; Athena/3.0; +{SITE_URL})",
                      },
                      method="POST")
        resp = json.loads(urlopen(req, timeout=30).read())
        if "url" in resp:
            print(f"   ✅ Dev.to: {resp['url']}")
            return {"status": "published", "url": resp["url"]}
        return {"status": "failed", "error": str(resp)[:200]}
    except Exception as e:
        print(f"   ⚠️ Dev.to: {e}")
        return {"status": "failed", "error": str(e)[:200]}


# ══════════════════════════════════════════════════════════
# 2. MEDIUM CROSS-POST
# ══════════════════════════════════════════════════════════
def publish_to_medium(article_path: Path, category_slug: str) -> dict:
    """Publish to Medium via their API with canonical URL."""
    if not MEDIUM_TOKEN:
        return {"status": "skipped", "reason": "no MEDIUM_TOKEN"}

    content = article_path.read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {"status": "failed", "reason": "invalid frontmatter"}

    title = desc = ""
    for line in parts[1].split("\n"):
        if line.startswith("title:"): title = line.split(":", 1)[1].strip().strip('"')
        if line.startswith("description:"): desc = line.split(":", 1)[1].strip().strip('"')

    # Convert markdown body to HTML for Medium
    body_md = parts[2]
    # Strip JSON-LD
    body_md = re.sub(r'<script type="application/ld\+json">.*?</script>', '', body_md, flags=re.DOTALL)

    # Get user ID first
    try:
        req = Request("https://api.medium.com/v1/me",
                      headers={"Authorization": f"Bearer {MEDIUM_TOKEN}"})
        user_data = json.loads(urlopen(req, timeout=10).read())
        user_id = user_data["data"]["id"]
    except Exception as e:
        return {"status": "failed", "reason": f"auth: {e}"}

    # Publish
    pname = article_path.stem
    p_parts = pname.split("-", 3)
    canonical = f"{SITE_URL}/{p_parts[0]}/{p_parts[1]}/{p_parts[2]}/{p_parts[3]}.html" if len(p_parts) >= 4 else SITE_URL

    tags = BOOST_TAGS.get(category_slug, ["tech", "reviews"])[:5]

    payload = json.dumps({
        "title": title,
        "contentFormat": "markdown",
        "content": body_md.strip(),
        "tags": tags,
        "canonicalUrl": canonical,
        "publishStatus": "public",
    }).encode()

    try:
        req = Request(f"https://api.medium.com/v1/users/{user_id}/posts",
                      data=payload,
                      headers={
                          "Authorization": f"Bearer {MEDIUM_TOKEN}",
                          "Content-Type": "application/json",
                      },
                      method="POST")
        resp = json.loads(urlopen(req, timeout=30).read())
        if "data" in resp:
            print(f"   ✅ Medium: {resp['data'].get('url', 'ok')}")
            return {"status": "published", "url": resp["data"].get("url", "")}
        return {"status": "failed", "error": str(resp)[:200]}
    except Exception as e:
        print(f"   ⚠️ Medium: {e}")
        return {"status": "failed", "error": str(e)[:200]}


# ══════════════════════════════════════════════════════════
# 3. SOCIAL MEDIA POST GENERATOR
# ══════════════════════════════════════════════════════════
def generate_social_posts(article_path: Path) -> dict:
    """Generate social media posts (Twitter/X, LinkedIn, etc.) from article."""
    content = article_path.read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    title = ""
    desc = ""
    for line in parts[1].split("\n"):
        if line.startswith("title:"): title = line.split(":", 1)[1].strip().strip('"')
        if line.startswith("description:"): desc = line.split(":", 1)[1].strip().strip('"')

    pname = article_path.stem
    p_parts = pname.split("-", 3)
    article_url = f"{SITE_URL}/{p_parts[0]}/{p_parts[1]}/{p_parts[2]}/{p_parts[3]}.html" if len(p_parts) >= 4 else SITE_URL

    # Extract first product mention
    body = parts[2]
    product_mention = ""
    for line in body.split("\n"):
        m = re.search(r'\*\*(.+?)\*\*', line)
        if m and ("Best" not in m.group(1)) and len(m.group(1)) > 3:
            product_mention = m.group(1)
            break

    # Generate social variants
    social = {
        "twitter": [],
        "linkedin": None,
    }

    # Twitter variants (max 280 chars)
    if product_mention:
        social["twitter"].append(f"🔥 We compared the {product_mention} against all competitors. Here's the winner:\n\n{article_url}")
        social["twitter"].append(f"Looking for the {title.lower()}? We tested them all. One came out on top.\n\n{article_url} #TechReview")

    social["twitter"].append(f"{title}\n\n{desc[:120]}...\n\n{article_url}")

    # LinkedIn
    social["linkedin"] = f"{title}\n\n{desc}\n\nRead the full comparison → {article_url}\n\n#TechReview #BuyingGuide #AmazonFinds"

    return social


# ══════════════════════════════════════════════════════════
# 4. RSS FEED ENHANCEMENT
# ══════════════════════════════════════════════════════════
def ensure_rss_feed():
    """Jekyll's jekyll-feed plugin generates feed.xml automatically.
    Just verify _config.yml has the plugin enabled."""
    config_path = Path("_config.yml")
    if not config_path.exists():
        print("   ⚠️ _config.yml not found")
        return

    config = config_path.read_text()
    if "jekyll-feed" in config:
        print("   ✅ RSS (jekyll-feed) configured")
    else:
        # Inject it
        if "plugins:" in config:
            new_config = []
            for line in config.split("\n"):
                new_config.append(line)
                if line.strip() == "plugins:":
                    new_config.append("  - jekyll-feed")
            config_path.write_text("\n".join(new_config))
            print("   ✅ RSS (jekyll-feed) injected")


# ══════════════════════════════════════════════════════════
# 5. MAIN — Distribute latest article
# ══════════════════════════════════════════════════════════
def main(post_path: Path = None, category_slug: str = ""):
    print("\n" + "=" * 50)
    print("  📡 Distribution Engine — Syndicating...")
    print("=" * 50)

    DIST_DIR.mkdir(exist_ok=True)

    if post_path is None:
        posts = sorted(OUT_DIR.glob("*.md"), reverse=True)
        if not posts:
            print("  No posts found.")
            return
        post_path = posts[0]

    if not category_slug:
        pc = post_path.read_text()
        pcs = pc.split("---", 2)
        if len(pcs) >= 2:
            for line in pcs[1].split("\n"):
                if line.startswith("categories:"):
                    category_slug = line.split(":", 1)[1].strip()
                    break

    filename = post_path.name
    print(f"\n  📄 Article: {filename}")

    # Step 1: Dev.to
    print("   🌐 Dev.to...")
    devto_result = publish_to_devto(post_path, category_slug)

    # Step 2: Medium
    print("   📝 Medium...")
    medium_result = publish_to_medium(post_path, category_slug)

    # Step 3: Generate social posts
    print("   🐦 Generating social posts...")
    social = generate_social_posts(post_path)

    # Step 4: Save distribution report
    report = {
        "article": filename,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "devto": devto_result,
        "medium": medium_result,
        "social": social,
        "channels_working": {
            "devto": bool(DEVTO_KEY) and devto_result.get("status") == "published",
            "medium": bool(MEDIUM_TOKEN) and medium_result.get("status") == "published",
            "rss": True,  # jekyll-feed handles this
            "twitter": bool(TWITTER_BEARER),
        }
    }

    report_path = DIST_DIR / f"{post_path.stem}_dist.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  📊 Distribution report: {report_path}")

    # Step 5: RSS check
    ensure_rss_feed()

    print("\n  ✅ Distribution complete")
    print("=" * 50)
    return report


if __name__ == "__main__":
    main()
