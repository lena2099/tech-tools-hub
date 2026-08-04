#!/usr/bin/env python3
"""
SEO Engine — Post-publication optimization for Athena.
Runs after agent.py. Injects structured data, builds internal link clusters,
fixes IndexNow, generates enhanced sitemap + RSS.
"""
import json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SITE_URL = "https://tech-tools-hub.netlify.app"
INDEXNOW_KEY = "0624a5ea55dc48afaefbe5ce8393c490"
OUT_DIR = Path("_posts")
GA4_ID = os.environ.get("GA4_MEASUREMENT_ID", "G-XXXXXXXXXX")


# ══════════════════════════════════════════════════════════
# 1. SCHEMA.ORG — Inject JSON-LD into articles
# ══════════════════════════════════════════════════════════
def generate_schema_jsonld(post_path: Path) -> str:
    """Read a Jekyll post, generate Product + Review + FAQ JSON-LD."""
    content = post_path.read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content

    frontmatter = parts[1]
    body = parts[2]

    # Parse frontmatter
    title = ""
    desc = ""
    slug = ""
    date_str = ""
    for line in frontmatter.split("\n"):
        if line.startswith("title:"): title = line.split(":", 1)[1].strip().strip('"')
        if line.startswith("description:"): desc = line.split(":", 1)[1].strip().strip('"')
        if line.startswith("categories:"): slug = line.split(":", 1)[1].strip()
        if line.startswith("date:"): date_str = line.split(":", 1)[1].strip()

    if not title:
        return content

    # Derive URL
    pname = post_path.stem
    parts_url = pname.split("-", 3)
    post_url = f"{SITE_URL}/{parts_url[0]}/{parts_url[1]}/{parts_url[2]}/{parts_url[3]}.html" if len(parts_url) >= 4 else SITE_URL

    # Extract product names and prices from the comparison table
    products = []
    table_lines = []
    in_table = False
    for line in body.split("\n"):
        if line.strip().startswith("|") and ("Product" in line or "Price" in line):
            in_table = True
            continue
        if in_table:
            if line.strip().startswith("|") and not line.strip().startswith("|---"):
                table_lines.append(line)
            elif not line.strip().startswith("|"):
                in_table = False

    for line in table_lines:
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) >= 2:
            name = cols[0].replace("[","").replace("]","").split("(")[0].strip()
            # Extract price
            price_str = cols[1] if len(cols) > 1 else ""
            price_match = re.search(r'\$?([\d,.]+)', price_str)
            price = price_match.group(1) if price_match else "0"
            products.append({"name": name, "price": price})

    # Build JSON-LD
    now_iso = datetime.now(timezone.utc).isoformat()
    publisher = {
        "@type": "Organization",
        "name": "Tech & Tools Hub",
        "url": SITE_URL
    }

    # Article schema
    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": desc,
        "url": post_url,
        "datePublished": date_str,
        "dateModified": now_iso,
        "author": {"@type": "Person", "name": "Lena"},
        "publisher": publisher,
        "mainEntityOfPage": {"@type": "WebPage", "@id": post_url}
    }

    # Product list schema (for comparison articles)
    if len(products) >= 2:
        product_schema = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "itemListElement": [],
            "name": f"Top {len(products)} {title}",
            "description": desc,
        }
        for i, p in enumerate(products):
            product_schema["itemListElement"].append({
                "@type": "ListItem",
                "position": i + 1,
                "item": {
                    "@type": "Product",
                    "name": p["name"],
                    "offers": {
                        "@type": "Offer",
                        "price": p["price"],
                        "priceCurrency": "USD"
                    }
                }
            })
    else:
        product_schema = None

    # FAQ schema — extract Q&A pairs
    # Patterns: "### 1. Question?" or "**Q:** ..." or "### Question?"
    faq = []
    faq_lines = body.split("\n")
    
    # Find FAQ section start
    faq_start = -1
    for i, line in enumerate(faq_lines):
        low = line.strip().lower().lstrip('#').strip()
        if low in ('faq', 'frequently asked questions', 'faqs', 'frequently asked questions (faq)'):
            faq_start = i
            break
    if faq_start < 0:
        faq = []  # no FAQ section
    else:
        for i in range(faq_start + 1, len(faq_lines)):
            ls = faq_lines[i].strip()
            if not ls:
                continue
            # Stop before next major section
            if ls.startswith("##") and 'faq' not in ls.lower().lstrip('#').strip():
                break
            
            # Style A: ### N. Question? — answer on next non-empty line
            m = re.match(r'^###?\s+(\d+)[\.)]\s+(.+?)(\?)?\s*$', ls)
            if m:
                q = m.group(2).strip()
                for j in range(i + 1, min(len(faq_lines), i + 5)):
                    a = faq_lines[j].strip()
                    if not a: continue
                    if a.startswith('#'): break
                    faq.append({"q": q[:150], "a": a[:300]})
                    break
                continue
            
            # Style B: **Q: Question?** — answer on next line starting with "A:"
            m = re.match(r'\*\*Q:\s*(.+?)\*?\*\*?\s*$', ls)
            if m:
                q = m.group(1).strip().rstrip('*').strip()
                for j in range(i + 1, min(len(faq_lines), i + 5)):
                    a = faq_lines[j].strip()
                    if not a: continue
                    if a.startswith('A:'):
                        faq.append({"q": q[:150], "a": a[2:].strip()[:300]})
                        break
                    if a.startswith('**') or a.startswith('#'): break
                continue
            
            # Style C: **N. Question?** — answer on next non-empty line
            m = re.match(r'\*\*\s*(\d+)[\.)]\s+(.+?\??)\*\*\s*$', ls)
            if m:
                q = m.group(2).strip()
                for j in range(i + 1, min(len(faq_lines), i + 5)):
                    a = faq_lines[j].strip()
                    if not a: continue
                    if a.startswith('**') or a.startswith('#'): break
                    faq.append({"q": q[:150], "a": a[:300]})
                    break
                continue

    faq_schema = None
    if faq:
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
                for f in faq[:5]
            ]
        }

    # Assemble all JSON-LD blocks
    jsonld_blocks = [json.dumps(article_schema, ensure_ascii=False)]
    if product_schema:
        jsonld_blocks.append(json.dumps(product_schema, ensure_ascii=False))
    if faq_schema:
        jsonld_blocks.append(json.dumps(faq_schema, ensure_ascii=False))

    jsonld_html = "\n\n".join(f'<script type="application/ld+json">\n{block}\n</script>' for block in jsonld_blocks)

    # Insert after frontmatter, before body content
    return f"---\n{frontmatter}\n---\n\n{jsonld_html}\n\n{body.strip()}"


# ══════════════════════════════════════════════════════════
# 2. SMART INTERNAL LINKING
# ══════════════════════════════════════════════════════════
CLUSTER_MAP = {
    "noise-cancelling-headphones": ["portable-audio", "wearables-fitness"],
    "budget-smartphones": ["ereaders-tablets", "charging-accessories"],
    "home-office-gear": ["smart-home-devices", "charging-accessories"],
    "smart-home-devices": ["home-office-gear", "noise-cancelling-headphones"],
    "ereaders-tablets": ["budget-smartphones", "portable-audio"],
    "wearables-fitness": ["noise-cancelling-headphones", "portable-audio"],
    "portable-audio": ["noise-cancelling-headphones", "wearables-fitness"],
    "charging-accessories": ["budget-smartphones", "home-office-gear"],
}


def build_link_cluster(post_path: Path, category_slug: str) -> str:
    """Read a post, replace generic 'Related Posts' with smart cluster links."""
    content = post_path.read_text()

    # Find all posts
    all_posts = sorted(OUT_DIR.glob("*.md"), reverse=True)

    # Same-category links
    same_cat = []
    cross_cat = []
    current_slug = post_path.stem.split("-", 3)[-1] if len(post_path.stem.split("-", 3)) >= 4 else ""

    for p in all_posts:
        if p.stem == post_path.stem:
            continue
        pc = p.read_text()
        # Extract category from frontmatter
        cat = ""
        title = ""
        in_fm = False
        for line in pc.split("\n"):
            if line.strip() == "---":
                if not in_fm:
                    in_fm = True
                else:
                    break
                continue
            if in_fm:
                if line.startswith("categories:"): cat = line.split(":", 1)[1].strip()
                if line.startswith("title:"): title = line.split(":", 1)[1].strip().strip('"')

        if not title or not cat:
            continue

        pname = p.stem
        parts = pname.split("-", 3)
        url = f"{SITE_URL}/{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}.html" if len(parts) >= 4 else SITE_URL

        entry = {"title": title, "url": url, "cat": cat}

        if cat == category_slug:
            same_cat.append(entry)
        elif cat in CLUSTER_MAP.get(category_slug, []):
            cross_cat.append(entry)

    # Build the new cross-links section
    links = []
    links.append("### 📚 More Buying Guides\n")

    if same_cat:
        links.append(f"**More {category_slug.replace('-',' ').title()}:**\n")
        for e in same_cat[:3]:
            links.append(f"- [{e['title']}]({e['url']})")
        links.append("")

    if cross_cat:
        links.append("**You might also like:**\n")
        for e in cross_cat[:2]:
            links.append(f"- [{e['title']}]({e['url']})")

    cluster_md = "\n".join(links)

    # Replace the old "Related Buying Guides" section
    if "### 📚 Related Buying Guides" in content:
        content = re.sub(
            r'### 📚 Related Buying Guides.*$',
            '',
            content,
            flags=re.DOTALL
        ).rstrip()
        content += f"\n\n---\n\n{cluster_md}"
    elif "### 📚 Related" not in content:
        content += f"\n\n---\n\n{cluster_md}"

    return content


# ══════════════════════════════════════════════════════════
# 3. INDEXNOW — Fixed URL format
# ══════════════════════════════════════════════════════════
def ping_indexnow(urls: list[str]):
    """Ping IndexNow with correct GitHub Pages URL format."""
    payload = json.dumps({
        "host": "lena2099.github.io",
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }).encode()
    try:
        req = Request("https://api.indexnow.org/indexnow",
                      data=payload,
                      headers={"Content-Type": "application/json; charset=utf-8"})
        resp = urlopen(req, timeout=10)
        print(f"   ✅ IndexNow: HTTP {resp.getcode()}")
    except Exception as e:
        print(f"   ⚠️ IndexNow: {e}")


# ══════════════════════════════════════════════════════════
# 4. ENHANCED SITEMAP with lastmod + changefreq
# ══════════════════════════════════════════════════════════
def generate_enhanced_sitemap():
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True)
    if not posts:
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = []

    # Homepage — always
    urls.append(f"""  <url>
    <loc>{SITE_URL}/</loc>
    <lastmod>{now}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>""")

    for i, p in enumerate(posts):
        parts = p.stem.split("-", 3)
        if len(parts) < 4:
            continue
        # Read category from frontmatter
        category = ""
        try:
            pc = p.read_text()
            for line in pc.split("\n"):
                if line.strip() == "---":
                    continue
                if line.startswith("categories:"):
                    category = line.split(":", 1)[1].strip()
                    break
                # Stop at second ---
                if line.strip() == "---" and category:
                    break
        except:
            pass
        if category:
            url = f"{SITE_URL}/{category}/{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}.html"
        else:
            url = f"{SITE_URL}/{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}.html"
        # Newest posts get higher priority
        priority = min(1.0, 1.0 - (i * 0.05))
        lastmod = f"{parts[0]}-{parts[1]}-{parts[2]}"
        changefreq = "daily" if i < 3 else "weekly"

        urls.append(f"""  <url>
    <loc>{url}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority:.1f}</priority>
  </url>""")

    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        >
{chr(10).join(urls)}
</urlset>
"""
    Path("sitemap.xml").write_text(sitemap)
    print(f"   ✅ Sitemap: {len(urls)} URLs")


# ══════════════════════════════════════════════════════════
# 5. ROBOTS — Ensure clean
# ══════════════════════════════════════════════════════════
def generate_robots():
    robots = f"""User-agent: *
Allow: /
Sitemap: {SITE_URL}/sitemap.xml

User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /"""
    Path("robots.txt").write_text(robots)
    print("   ✅ robots.txt updated")


# ══════════════════════════════════════════════════════════
# 6. GOOGLE SEARCH CONSOLE — Sitemap submission via public endpoint
# ══════════════════════════════════════════════════════════
def submit_to_google():
    """Submit sitemap to Google via the public ping endpoint (still works)."""
    sitemap_url = f"{SITE_URL}/sitemap.xml"
    try:
        req = Request(f"https://www.google.com/ping?sitemap={sitemap_url}")
        resp = urlopen(req, timeout=10)
        print(f"   ✅ Google sitemap ping: HTTP {resp.getcode()}")
    except Exception as e:
        print(f"   ⚠️ Google ping: {e} (non-critical)")


# ══════════════════════════════════════════════════════════
# 7. GA4 INJECTION — Add tracking snippet to _config.yml
# ══════════════════════════════════════════════════════════
def ensure_ga4_config():
    """Ensure GA4 is in _config.yml."""
    config_path = Path("_config.yml")
    if not config_path.exists():
        print("   ⚠️ _config.yml not found, skip GA4")
        return

    config = config_path.read_text()
    if "google_analytics" in config:
        print("   ✅ GA4 already in _config.yml")
        return

    # jekyll/minima supports `google_analytics` key
    ga_block = f"\n# Google Analytics 4\ngoogle_analytics: {GA4_ID}\n"
    config_path.write_text(config.rstrip() + ga_block)
    print(f"   ✅ GA4 injected: {GA4_ID}")


# ══════════════════════════════════════════════════════════
# 8. MAIN — Apply SEO to latest post
# ══════════════════════════════════════════════════════════
def main(post_path: Path = None, category_slug: str = ""):
    print("\n" + "=" * 50)
    print("  🔍 SEO Engine — Optimizing...")
    print("=" * 50)

    # If no specific post given, find the latest
    if post_path is None:
        posts = sorted(OUT_DIR.glob("*.md"), reverse=True)
        if not posts:
            print("  No posts found.")
            return
        post_path = posts[0]

    # Extract category from post if not provided
    if not category_slug:
        pc = post_path.read_text()
        parts = pc.split("---", 2)
        if len(parts) >= 2:
            for line in parts[1].split("\n"):
                if line.startswith("categories:"):
                    category_slug = line.split(":", 1)[1].strip()
                    break

    filename = post_path.name
    print(f"\n  📄 Processing: {filename}")

    # Step 1: Schema.org JSON-LD
    print("   🧩 Injecting Schema.org...")
    enriched = generate_schema_jsonld(post_path)
    post_path.write_text(enriched)

    # Step 2: Smart internal linking
    if category_slug and category_slug in CLUSTER_MAP:
        print("   🔗 Building link cluster...")
        clustered = build_link_cluster(post_path, category_slug)
        post_path.write_text(clustered)

    # Step 3: Enhanced sitemap
    print("   📊 Generating enhanced sitemap...")
    generate_enhanced_sitemap()

    # Step 4: Robots
    print("   🤖 Updating robots.txt...")
    generate_robots()

    # Step 5: GA4
    print("   📈 Checking GA4...")
    ensure_ga4_config()

    # Step 6: IndexNow — notify all search engines
    print("   📡 Notifying search engines...")
    pname = post_path.stem
    parts = pname.split("-", 3)
    if len(parts) >= 4:
        post_url = f"{SITE_URL}/{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}.html"
        ping_indexnow([post_url, f"{SITE_URL}/sitemap.xml"])
    submit_to_google()

    print(f"\n  ✅ SEO optimization complete for: {filename}")
    print("=" * 50)


if __name__ == "__main__":
    main()
