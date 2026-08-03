#!/usr/bin/env python3
"""
Distribution Engine v3 — Multi-channel syndication that actually works.
Runs after seo_engine.py. 

Strategy: free channels first (IndexNow, Bluesky, RSS), then API channels (Dev.to).
Every channel that fails just gets logged — no single failure blocks the others.

Channels (ordered by impact):
  1. IndexNow → instant Bing/Yandex/Seznam indexing (FREE, no tokens)
  2. Google Sitemap Ping → ping Google to re-crawl (FREE)
  3. Bluesky → social signal + canonical link (FREE, needs app password)
  4. Dev.to → high-DA backlink + audience (needs API key)
  5. RSS → auto-submitted to aggregators (FREE, automatic via jekyll-feed)
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

INDEXNOW_KEY = "0624a5ea55dc48afaefbe5ce8393c490"
INDEXNOW_ENDPOINTS = [
    "https://www.bing.com/indexnow",
    "https://yandex.com/indexnow",
    "https://search.seznam.cz/indexnow",
]

DEVTO_KEY = os.environ.get("DEVTO_API_KEY", "")
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")


def submit_indexnow(urls):
    payload = json.dumps({"host": "lena2099.github.io", "key": INDEXNOW_KEY, "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt", "urlList": urls}).encode()
    results = {}
    for ep in INDEXNOW_ENDPOINTS:
        eng = ep.split("//")[1].split(".")[0]
        try:
            resp = urlopen(Request(ep, data=payload, headers={"Content-Type": "application/json"}), timeout=15)
            results[eng] = f"OK({resp.status})"
            print(f"   ✅ IndexNow → {eng}: {resp.status}")
        except Exception as e:
            results[eng] = str(e)[:80]
            print(f"   ⚠️ IndexNow → {eng}: {e}")
    return results


def ping_google():
    try:
        resp = urlopen(Request(f"https://www.google.com/ping?sitemap={quote(SITEMAP_URL)}", headers={"User-Agent": "Athena/3.0"}), timeout=15)
        print(f"   ✅ Google Sitemap Ping: {resp.status}")
        return {"status": "pinged"}
    except Exception as e:
        print(f"   ⚠️ Google Ping: {e}")
        return {"status": "failed"}


def post_to_bluesky(title, desc, url):
    if not BLUESKY_HANDLE or not BLUESKY_PASSWORD:
        return {"status": "skipped", "reason": "no credentials"}
    try:
        sp = json.dumps({"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD}).encode()
        session = json.loads(urlopen(Request("https://bsky.social/xrpc/com.atproto.server.createSession", data=sp, headers={"Content-Type": "application/json"}), timeout=15).read())
        token = session["accessJwt"]
        text = f"{title}\n\n{desc[:180]}\n\n{url}"[:300]
        pp = json.dumps({"repo": session["did"], "collection": "app.bsky.feed.post", "record": {"text": text, "createdAt": datetime.now(timezone.utc).isoformat()}}).encode()
        result = json.loads(urlopen(Request("https://bsky.social/xrpc/com.atproto.repo.createRecord", data=pp, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}), timeout=15).read())
        print(f"   ✅ Bluesky: posted")
        return {"status": "published"}
    except Exception as e:
        print(f"   ⚠️ Bluesky: {e}")
        return {"status": "failed", "error": str(e)[:200]}


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


def publish_to_devto(post_path, category_slug):
    if not DEVTO_KEY:
        return {"status": "skipped"}
    content = post_path.read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {"status": "failed"}
    title = desc = ""
    for line in parts[1].split("\n"):
        if line.startswith("title:"): title = line.split(":", 1)[1].strip().strip('"')
        if line.startswith("description:"): desc = line.split(":", 1)[1].strip().strip('"')
    body = re.sub(r'<script type="application/ld\+json">.*?</script>', '', parts[2], flags=re.DOTALL)
    pname = post_path.stem
    pparts = pname.split("-", 3)
    canonical = f"{SITE_URL}/{pparts[0]}/{pparts[1]}/{pparts[2]}/{pparts[3]}.html" if len(pparts) >= 4 else SITE_URL
    payload = {"article": {"title": title, "body_markdown": body.strip(), "published": True, "tags": BOOST_TAGS.get(category_slug, ["reviews", "tech"])[:4], "description": desc[:160], "canonical_url": canonical}}
    try:
        resp = json.loads(urlopen(Request("https://dev.to/api/articles", data=json.dumps(payload).encode(), headers={"api-key": DEVTO_KEY, "Content-Type": "application/json", "User-Agent": "Athena/3.0"}, method="POST"), timeout=30).read())
        if "url" in resp:
            print(f"   ✅ Dev.to: {resp['url']}")
            return {"status": "published", "url": resp["url"]}
        return {"status": "failed"}
    except Exception as e:
        print(f"   ⚠️ Dev.to: {e}")
        return {"status": "failed", "error": str(e)[:200]}


def check_rss():
    try:
        resp = urlopen(Request(f"{SITE_URL}/feed.xml", headers={"User-Agent": "Athena/3.0"}), timeout=15)
        entries = resp.read().decode().count("<entry>") or resp.read().decode().count("<item>")
        print(f"   ✅ RSS feed: {entries} entries")
        return {"status": "ok", "entries": entries}
    except Exception as e:
        print(f"   ⚠️ RSS: {e}")
        return {"status": "fail"}


def main():
    DIST_DIR.mkdir(exist_ok=True)
    posts = sorted(OUT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not posts:
        print("No articles")
        return
    post_path = posts[0]
    content = post_path.read_text()
    parts = content.split("---", 2)
    title = desc = cat = slug = ""
    if len(parts) >= 3:
        for line in parts[1].split("\n"):
            if line.startswith("title:"): title = line.split(":", 1)[1].strip().strip('"')
            if line.startswith("description:"): desc = line.split(":", 1)[1].strip().strip('"')
            if line.startswith("categories:"): cat = line.split(":", 1)[1].strip()
    pname = post_path.stem
    p = pname.split("-", 3)
    url = f"{SITE_URL}/{p[0]}/{p[1]}/{p[2]}/{p[3]}.html" if len(p) >= 4 else SITE_URL

    print(f"\n📡 Distributing: {post_path.name}")
    print(f"   {url}")

    print("\n🌍 IndexNow (Bing/Yandex)...")
    idx = submit_indexnow([url])
    print("\n🔍 Google Sitemap Ping...")
    goog = ping_google()
    print("\n🦋 Bluesky...")
    bs = post_to_bluesky(title, desc, url)
    print("\n🔗 Dev.to cross-post...")
    dv = publish_to_devto(post_path, cat)
    print("\n📡 RSS verification...")
    rss = check_rss()

    report = {"article": post_path.name, "url": url, "timestamp": datetime.now(timezone.utc).isoformat(), "indexnow": idx, "google_ping": goog, "bluesky": bs, "devto": dv, "rss": rss}
    rp = DIST_DIR / f"{post_path.stem}_dist.json"
    with open(rp, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report: {rp}")
    return report


if __name__ == "__main__":
    main()
