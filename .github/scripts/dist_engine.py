#!/usr/bin/env python3
"""
Distribution Engine v3 — Multi-channel syndication.
Runs after seo_engine.py.

What it does (automatic, no tokens needed):
  1. IndexNow → instant Bing/Yandex/Seznam indexing (FREE)
  2. Google Sitemap Ping → ask Google to re-crawl (FREE)
  3. Bluesky → social signal (FREE, needs BLUESKY_HANDLE + BLUESKY_APP_PASSWORD)
  4. RSS verification → jekyll-feed auto-generates (FREE)

What it generates (for manual publishing):
  5. _social/latest-reddit.md → copy-paste ready Reddit post
  6. _social/latest-threads.txt → copy-paste ready for social posts
  7. _social/latest-dist.json → full distribution report
"""
import json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

SITE_URL = "https://lena2099.github.io/tech-tools-hub"
SITEMAP_URL = f"{SITE_URL}/sitemap.xml"
OUT_DIR = Path("_posts")
DIST_DIR = Path("_dist")
SOCIAL_DIR = Path("_social")

INDEXNOW_KEY = "0624a5ea55dc48afaefbe5ce8393c490"
INDEXNOW_ENDPOINTS = [
    "https://www.bing.com/indexnow",
    "https://yandex.com/indexnow",
    "https://search.seznam.cz/indexnow",
]

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")


def call_deepseek(messages, max_tokens=1024, temperature=0.8):
    if not API_KEY:
        return ""
    try:
        req = Request("https://api.deepseek.com/chat/completions",
                      data=json.dumps({"model": "deepseek-chat", "messages": messages,
                                       "max_tokens": max_tokens, "temperature": temperature}).encode(),
                      headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
        resp = json.loads(urlopen(req, timeout=60).read())
        return resp["choices"][0]["message"]["content"]
    except:
        return ""


# ══════════════════════════════════════════════════════════
# 1. INDEXNOW
# ══════════════════════════════════════════════════════════
def submit_indexnow(urls):
    payload = json.dumps({"host": "lena2099.github.io", "key": INDEXNOW_KEY,
                          "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
                          "urlList": urls}).encode()
    results = {}
    for ep in INDEXNOW_ENDPOINTS:
        eng = ep.split("//")[1].split(".")[0]
        try:
            resp = urlopen(Request(ep, data=payload,
                                   headers={"Content-Type": "application/json"}), timeout=15)
            results[eng] = f"OK({resp.status})"
            print(f"   ✅ IndexNow → {eng}: {resp.status}")
        except Exception as e:
            results[eng] = str(e)[:80]
            print(f"   ⚠️ IndexNow → {eng}: {e}")
    return results


# ══════════════════════════════════════════════════════════
# 2. GOOGLE PING
# ══════════════════════════════════════════════════════════
def ping_google():
    try:
        resp = urlopen(Request(f"https://www.google.com/ping?sitemap={quote(SITEMAP_URL)}",
                               headers={"User-Agent": "Athena/3.0"}), timeout=15)
        print(f"   ✅ Google Sitemap Ping: {resp.status}")
        return {"status": "pinged"}
    except Exception as e:
        print(f"   ⚠️ Google Ping: {e}")
        return {"status": "failed"}


# ══════════════════════════════════════════════════════════
# 3. BLUESKY
# ══════════════════════════════════════════════════════════
def post_to_bluesky(title, desc, url):
    if not BLUESKY_HANDLE or not BLUESKY_PASSWORD:
        print("   ⏭  Bluesky: no credentials — skipping")
        return {"status": "skipped"}
    try:
        sp = json.dumps({"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD}).encode()
        session = json.loads(urlopen(Request(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            data=sp, headers={"Content-Type": "application/json"}), timeout=15).read())
        token = session["accessJwt"]
        text = f"{title}\n\n{desc[:180]}\n\n{url}"[:300]
        pp = json.dumps({"repo": session["did"], "collection": "app.bsky.feed.post",
                          "record": {"text": text,
                                     "createdAt": datetime.now(timezone.utc).isoformat()}}).encode()
        json.loads(urlopen(Request(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            data=pp, headers={"Authorization": f"Bearer {token}",
                              "Content-Type": "application/json"}), timeout=15).read())
        print(f"   ✅ Bluesky: posted")
        return {"status": "published"}
    except Exception as e:
        print(f"   ⚠️ Bluesky: {e}")
        return {"status": "failed", "error": str(e)[:200]}


# ══════════════════════════════════════════════════════════
# 4. GENERATE MANUAL-PUBLISH CONTENT
# ══════════════════════════════════════════════════════════
def generate_manual_content(title, body, url, category):
    """Generate copy-paste ready content for manual publishing."""
    excerpt = body[:3000]

    # Reddit post
    reddit_prompt = f"""Write a Reddit post for r/{category} or r/gadgets or r/techreviews. Rules:
- Start with personal experience or strong opinion (NOT "I wrote this")
- 2-3 specific product names with one-sentence verdict each
- End with the link
- NO "hey Reddit", NO "hope this helps", NO emoji
- Sound like a real person, casual, max 800 chars

TITLE: {title}
CONTENT (first 3000 chars): {excerpt}
LINK: {url}

Return the post text starting with the subreddit suggestion in [brackets]."""

    reddit_text = call_deepseek([{"role": "user", "content": reddit_prompt}], max_tokens=800) or ""

    # Social post variants
    social_prompt = f"""Write 3 social media posts for this article:
1. Threads/Bluesky/Twitter — hooky, max 280 chars, include link
2. LinkedIn — professional tone, 3 short paragraphs, include link  
3. Short — just the verdict, 150 chars max, include link

Article: {title}
URL: {url}

Return as:
POST 1 (Threads/Bluesky): ...
POST 2 (LinkedIn): ...
POST 3 (Short): ..."""

    social_text = call_deepseek([{"role": "user", "content": social_prompt}], max_tokens=800) or ""

    return reddit_text, social_text


# ══════════════════════════════════════════════════════════
# 5. RSS CHECK
# ══════════════════════════════════════════════════════════
def check_rss():
    try:
        resp = urlopen(Request(f"{SITE_URL}/feed.xml",
                               headers={"User-Agent": "Athena/3.0"}), timeout=15)
        content = resp.read().decode()
        entries = content.count("<entry>") or content.count("<item>")
        print(f"   ✅ RSS: {entries} entries")
        return {"status": "ok", "entries": entries}
    except Exception as e:
        print(f"   ⚠️ RSS: {e}")
        return {"status": "fail"}


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════
def main():
    DIST_DIR.mkdir(exist_ok=True)
    SOCIAL_DIR.mkdir(exist_ok=True)

    posts = sorted(OUT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not posts:
        print("No articles")
        return

    post_path = posts[0]
    content = post_path.read_text()
    parts = content.split("---", 2)

    title = desc = cat = ""
    if len(parts) >= 3:
        for line in parts[1].split("\n"):
            if line.startswith("title:"): title = line.split(":", 1)[1].strip().strip('"')
            if line.startswith("description:"): desc = line.split(":", 1)[1].strip().strip('"')
            if line.startswith("categories:"): cat = line.split(":", 1)[1].strip()

    body = parts[2] if len(parts) >= 3 else ""
    pname = post_path.stem
    p = pname.split("-", 3)
    url = f"{SITE_URL}/{p[0]}/{p[1]}/{p[2]}/{p[3]}.html" if len(p) >= 4 else SITE_URL

    print(f"\n{'='*60}")
    print(f"📡 Distributing: {post_path.name}")
    print(f"   {url}")
    print(f"   {title[:80]}")
    print(f"{'='*60}")

    # Step 1: Search engine indexing (automatic)
    print("\n🌍 IndexNow (Bing/Yandex/Seznam)...")
    idx = submit_indexnow([url])
    print("\n🔍 Google Sitemap Ping...")
    goog = ping_google()

    # Step 2: Bluesky (automatic if credentials set)
    print("\n🦋 Bluesky...")
    bs = post_to_bluesky(title, desc, url)

    # Step 3: Generate manual-publish content
    print("\n✍️  Generating copy-paste content...")
    reddit_text, social_text = generate_manual_content(title, body, url, cat)

    # Save Reddit post
    reddit_path = SOCIAL_DIR / "latest-reddit.md"
    with open(reddit_path, "w") as f:
        f.write(f"# Reddit Post — {title}\n\n")
        f.write(f"**Article URL:** {url}\n\n")
        f.write(f"---\n\n")
        f.write(reddit_text if reddit_text else f"(Reddit post generation skipped — no API key)\n\nLink: {url}")
    print(f"   📝 Reddit post: {reddit_path}")

    # Save social posts
    social_path = SOCIAL_DIR / "latest-social.txt"
    with open(social_path, "w") as f:
        f.write(f"# Social Posts — {title}\n\n")
        f.write(f"Article: {url}\n\n")
        f.write(f"---\n\n")
        f.write(social_text if social_text else f"📱 {title}\n{desc[:200]}\n\n{url}")
    print(f"   📝 Social posts: {social_path}")

    # Step 4: RSS check
    print("\n📡 RSS verification...")
    rss = check_rss()

    # Save distribution report
    report = {
        "article": post_path.name,
        "url": url,
        "title": title,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "auto_published": {"indexnow": idx, "google_ping": goog, "bluesky": bs, "rss": rss},
        "manual_publish": {"reddit": str(reddit_path), "social": str(social_path)},
        "channels_working": {
            "indexnow": all("OK" in str(v) for v in idx.values()),
            "google_ping": goog.get("status") == "pinged",
            "bluesky": bs.get("status") == "published",
            "rss": rss.get("status") == "ok",
            "manual_reddit": bool(reddit_text),
            "manual_social": bool(social_text),
        }
    }

    report_path = DIST_DIR / f"{post_path.stem}_dist.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"📊 Distribution Report: {report_path}")
    print(f"   IndexNow:     {idx.get('bing', '?')}")
    print(f"   Google:       {goog.get('status', '?')}")
    print(f"   Bluesky:      {bs.get('status', '?')}")
    print(f"   RSS:          {rss.get('status', '?')}")
    print(f"   Reddit (手动): {reddit_path}")
    print(f"   社交 (手动):    {social_path}")
    print(f"{'='*60}")

    return report


if __name__ == "__main__":
    main()
