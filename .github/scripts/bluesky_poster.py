#!/usr/bin/env python3
"""
Bluesky 自动发帖脚本 — Tech & Tools Hub
========================================
每篇新文章发布后自动推送到 Bluesky，附带文章链接和 OG 卡片。

用法：
    python bluesky_poster.py \
        --handle "handle.bsky.social" \
        --password "xxxx-xxxx-xxxx-xxxx" \
        --url "https://lena2099.github.io/tech-tools-hub/noise-cancelling-headphones/2026/08/01/article.html"

或从环境变量读取：
    export BLUESKY_HANDLE="handle.bsky.social"
    export BLUESKY_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"

参考：https://atproto.com/blog/create-post
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List


# ============================================================
# Bluesky API Client
# ============================================================

class BlueskyClient:
    BASE_URL = "https://bsky.social/xrpc"

    def __init__(self, handle: str, app_password: str):
        self.handle = handle
        self.app_password = app_password
        self._session: Optional[Dict] = None

    def _login(self) -> Dict:
        resp = requests.post(
            f"{self.BASE_URL}/com.atproto.server.createSession",
            json={"identifier": self.handle, "password": self.app_password},
        )
        resp.raise_for_status()
        self._session = resp.json()
        return self._session

    @property
    def session(self) -> Dict:
        if self._session is None:
            self._login()
        return self._session

    def post(
        self,
        text: str,
        *,
        url: Optional[str] = None,
        langs: Optional[List[str]] = None,
    ) -> Dict:
        """Create a post on Bluesky. Optionally embed a URL as a website card."""
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": now,
        }

        if langs:
            record["langs"] = langs

        # Parse facets: links in text become clickable
        facets = self._parse_facets(text, url)
        if facets:
            record["facets"] = facets

        # If a URL is provided, embed it as a website card
        if url:
            card = self._build_embed_card(url)
            if card:
                record["embed"] = card

        resp = requests.post(
            f"{self.BASE_URL}/com.atproto.repo.createRecord",
            headers={"Authorization": "Bearer " + self.session["accessJwt"]},
            json={
                "repo": self.session["did"],
                "collection": "app.bsky.feed.post",
                "record": record,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_facets(self, text: str, main_url: Optional[str] = None) -> List[Dict]:
        """Parse URLs in text into clickable facets."""
        import re
        facets = []
        text_bytes = text.encode("UTF-8")

        url_regex = rb"https?://[^\s]+"
        for m in re.finditer(url_regex, text_bytes):
            url_str = m.group(0).decode("UTF-8")
            facets.append({
                "index": {"byteStart": m.start(), "byteEnd": m.end()},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url_str}],
            })

        return facets

    def _build_embed_card(self, url: str) -> Optional[Dict]:
        """Build a website card embed (the link preview card)."""
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
        except Exception:
            return None

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
        except ImportError:
            # Light fallback: just the URL without preview
            return {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": url,
                    "title": url,
                    "description": "",
                },
            }

        card = {
            "$type": "app.bsky.embed.external",
            "external": {
                "uri": url,
                "title": url,
                "description": "",
            },
        }

        title_tag = soup.find("meta", property="og:title")
        if title_tag and title_tag.get("content"):
            card["external"]["title"] = title_tag["content"]

        desc_tag = soup.find("meta", property="og:description")
        if desc_tag and desc_tag.get("content"):
            card["external"]["description"] = desc_tag["content"]

        image_tag = soup.find("meta", property="og:image")
        if image_tag and image_tag.get("content"):
            img_url = image_tag["content"]
            try:
                img_resp = requests.get(img_url, timeout=10)
                img_resp.raise_for_status()
                if len(img_resp.content) <= 1000000:
                    blob_resp = requests.post(
                        f"{self.BASE_URL}/com.atproto.repo.uploadBlob",
                        headers={
                            "Content-Type": img_resp.headers.get("Content-Type", "image/png"),
                            "Authorization": "Bearer " + self.session["accessJwt"],
                        },
                        data=img_resp.content,
                    )
                    blob_resp.raise_for_status()
                    card["external"]["thumb"] = blob_resp.json()["blob"]
            except Exception:
                pass

        return card


# ============================================================
# Post Generator — creates engaging Bluesky post text
# ============================================================

def generate_post_text(article_title: str, article_url: str, category: str = "") -> str:
    """Generate a 300-character Bluesky post from article metadata."""
    emoji_map = {
        "headphones": "🎧", "earbuds": "🎧", "audio": "🔊",
        "noise-cancelling": "🎧", "noise-cancelling-headphones": "🎧",
        "smartwatch": "⌚", "wearables": "⌚", "fitness": "⌚",
        "phone": "📱", "smartphone": "📱",
        "charging": "🔌",
        "office-gear": "🪑", "desk": "🖥️", "home-office": "🏠",
        "tablet": "📋", "ereader": "📋",
        "monitor": "🖥️",
        "keyboard": "⌨️",
        "speaker": "🔊",
    }
    emoji = ""
    for k, v in emoji_map.items():
        if k in category.lower() or k in article_title.lower():
            emoji = v
            break

    # Clean title
    title = article_title.replace("| Tech & Tools Hub", "").strip()

    # Truncate to fit 300 char limit (Bluesky is 300)
    body = f"{title}\n\nFull review → {article_url}"
    if emoji:
        body = f"{emoji} {body}"

    return body[:300]


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Post an article to Bluesky")
    parser.add_argument("--handle", help="Bluesky handle (e.g. user.bsky.social)")
    parser.add_argument("--password", help="Bluesky App Password (NOT your login password)")
    parser.add_argument("--url", required=True, help="Article URL to share")
    parser.add_argument("--title", help="Article title (auto-detected from page if omitted)")
    parser.add_argument("--category", default="", help="Article category for emoji selection")
    parser.add_argument("--text", help="Custom post text (overrides auto-generation)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be posted, don't post")
    args = parser.parse_args()

    handle = args.handle or os.environ.get("BLUESKY_HANDLE")
    password = args.password or os.environ.get("BLUESKY_APP_PASSWORD")

    if not handle or not password:
        print("ERROR: Bluesky handle and app password required.", file=sys.stderr)
        print("Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD env vars, or use --handle --password")
        sys.exit(1)

    # Auto-detect title from page
    title = args.title
    if not title:
        try:
            from bs4 import BeautifulSoup
            resp = requests.get(args.url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)
            else:
                title = args.url.split("/")[-1].replace(".html", "").replace("-", " ").title()
        except Exception:
            title = args.url.split("/")[-1].replace(".html", "").replace("-", " ").title()

    post_text = args.text or generate_post_text(title, args.url, args.category)

    if args.dry_run:
        print("=" * 50)
        print("DRY RUN — would post:")
        print(post_text)
        print(f"URL card: {args.url}")
        print("=" * 50)
        return

    client = BlueskyClient(handle, password)
    result = client.post(post_text, url=args.url, langs=["en-US"])
    uri = result.get("uri", "unknown")
    print(f"✅ Posted: {uri}")


if __name__ == "__main__":
    main()
