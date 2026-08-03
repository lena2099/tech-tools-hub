#!/usr/bin/env python3
"""
Pinterest 自动发 Pin 脚本 — Tech & Tools Hub
=============================================
每篇新文章发布后自动创建 1 个 Pin，包含：
  - 文章标题
  - 文章链接（直连 GitHub Pages → Amazon 变现）
  - 文章 OG 图片作为 Pin 图
  - 文章描述

使用前需要先获取 OAuth Access Token：
    python pinterest_poster.py --auth --app-id YOUR_ID --app-secret YOUR_SECRET

然后正常发 Pin：
    python pinterest_poster.py --access-token TOKEN --url "https://..."

参考：https://developers.pinterest.com/docs/api/v5/
"""

import os
import sys
import json
import argparse
import requests
import urllib.parse
from typing import Optional, Dict


# ============================================================
# Pinterest API Client (v5)
# ============================================================

PINTEREST_API = "https://api.pinterest.com/v5"


class PinterestClient:
    def __init__(self, access_token: str):
        self.token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def get_user_info(self) -> Dict:
        resp = requests.get(
            f"{PINTEREST_API}/user_account",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    def list_boards(self) -> list:
        """List all boards. Returns board objects with 'id' and 'name'."""
        boards = []
        bookmark = None
        while True:
            params = {"page_size": 50}
            if bookmark:
                params["bookmark"] = bookmark
            resp = requests.get(
                f"{PINTEREST_API}/boards",
                headers=self.headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            boards.extend(data.get("items", []))
            bookmark = data.get("bookmark")
            if not bookmark:
                break
        return boards

    def create_board(self, name: str, description: str = "") -> Dict:
        """Create a new board."""
        resp = requests.post(
            f"{PINTEREST_API}/boards",
            headers=self.headers,
            json={
                "name": name,
                "description": description,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def create_pin(
        self,
        board_id: str,
        title: str,
        description: str,
        link: str,
        image_url: Optional[str] = None,
        image_file: Optional[str] = None,
    ) -> Dict:
        """Create a new Pin on a board.

        Either image_url (public URL) or image_file (local path) must be provided.
        """
        pin_data = {
            "board_id": board_id,
            "title": title[:100],  # max 100 chars
            "description": description[:500],  # max 500 chars
            "link": link,
        }

        if image_url:
            pin_data["media_source"] = {
                "source_type": "image_url",
                "url": image_url,
            }
        elif image_file:
            # Upload to Pinterest media first
            media = self._upload_image(image_file)
            pin_data["media_source"] = {
                "source_type": "image_id",
                "media_id": media["media_id"],
            }

        resp = requests.post(
            f"{PINTEREST_API}/pins",
            headers=self.headers,
            json=pin_data,
        )
        resp.raise_for_status()
        return resp.json()

    def _upload_image(self, file_path: str) -> Dict:
        """Upload an image to Pinterest media."""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/png"

        # Step 1: register upload
        resp = requests.post(
            f"{PINTEREST_API}/media",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            json={"media_type": mime_type},
        )
        resp.raise_for_status()
        media = resp.json()

        # Step 2: upload binary
        with open(file_path, "rb") as f:
            upload_headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": mime_type,
            }
            upload_resp = requests.post(
                media["upload_url"],
                headers=upload_headers,
                data=f.read(),
                params=media.get("upload_parameters", {}),
            )
            # Some upload endpoints return 204 or 200

        # Step 3: confirm upload
        confirm_resp = requests.post(
            f"{PINTEREST_API}/media/{media['media_id']}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        confirm_resp.raise_for_status()
        return confirm_resp.json()


# ============================================================
# OAuth Flow — run once to get an access token
# ============================================================

def do_oauth(app_id: str, app_secret: str) -> str:
    """Complete OAuth 2.0 flow and return an access token.

    Opens a browser for user authorization, then exchanges the code for a token.
    The token is saved to 'pinterest_token.json' for future use.
    """
    import webbrowser
    import http.server
    import threading
    import time
    from urllib.parse import urlencode, parse_qs, urlparse

    redirect_uri = "http://localhost:8085/"
    scopes = [
        "boards:read", "boards:write",
        "pins:read", "pins:write",
    ]

    auth_url = (
        f"https://www.pinterest.com/oauth/?"
        + urlencode({
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(scopes),
            "state": "pinterest_oauth_state",
        })
    )

    # We'll use a simple approach: print the URL and let user paste the code
    print("\n" + "=" * 60)
    print("STEP 1: Open this URL in your browser and authorize:")
    print("=" * 60)
    print(f"\n{auth_url}\n")
    print("After authorization, you'll be redirected to a non-working page.")
    print("Copy the FULL URL from your browser address bar.\n")

    redirect_url = input("Paste the full redirect URL here: ").strip()
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    code = params.get("code", [None])[0]

    if not code:
        print("ERROR: No authorization code found in URL. Try again.")
        sys.exit(1)

    # Exchange code for token
    print("\nExchanging code for access token...")
    resp = requests.post(
        "https://api.pinterest.com/v5/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(app_id, app_secret),
    )
    resp.raise_for_status()
    token_data = resp.json()

    # Save token
    token_info = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "scopes": token_data.get("scopes", scopes),
        "app_id": app_id,
    }
    token_path = os.path.join(os.path.dirname(__file__), "pinterest_token.json")
    with open(token_path, "w") as f:
        json.dump(token_info, f, indent=2)
    os.chmod(token_path, 0o600)

    print(f"\n✅ Access token saved to {token_path}")
    print(f"   Token: {token_data['access_token'][:20]}...")
    return token_data["access_token"]


# ============================================================
# Pin Content Generator
# ============================================================

def generate_pin_content(
    article_url: str,
    title: Optional[str] = None,
    category: str = "",
) -> tuple:
    """Scrape article page for OG tags, return (title, description, image_url).

    Returns a tuple of (title, description, image_url) for the Pin.
    """
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(article_url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
    except ImportError:
        # No BeautifulSoup — return basic info from URL
        slug = article_url.rstrip("/").split("/")[-1].replace(".html", "")
        title = title or slug.replace("-", " ").title()
        return (title[:100], f"Best {title} — honest review from Tech & Tools Hub", None)

    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"]
        else:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else "Tech Review"

    # Get description
    og_desc = soup.find("meta", property="og:description")
    description = og_desc["content"] if og_desc and og_desc.get("content") else ""

    # Get image
    og_image = soup.find("meta", property="og:image")
    image_url = og_image["content"] if og_image and og_image.get("content") else None

    # Build pin description with hashtags
    hashtags = ["#techreview", "#gadgets", "#buyingguide"]
    cat_tags = {
        "headphones": ["#headphones", "#noisecancelling"],
        "noise-cancelling-headphones": ["#headphones", "#noisecancelling"],
        "wearables-fitness": ["#smartwatch", "#wearables"],
        "smartwatch": ["#smartwatch", "#applewatch"],
        "home-office-gear": ["#homeoffice", "#desksetup"],
        "budget-smartphones": ["#smartphone", "#budget"],
        "portable-audio": ["#speaker", "#audio"],
        "ereaders-tablets": ["#tablet", "#reading"],
        "charging-accessories": ["#charging", "#usbc"],
        "smart-home-devices": ["#smarthome", "#security"],
    }
    for k, v in cat_tags.items():
        if k in category.lower() or k.replace("-", " ") in title.lower():
            hashtags.extend(v)
            break
    hashtags.append("#techtoolshub")

    pin_desc = f"{description[:300]}\n\n{article_url}\n\n{' '.join(sorted(set(hashtags)))}"
    return (title[:100], pin_desc[:500], image_url)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Create Pinterest Pins for articles")
    parser.add_argument("--auth", action="store_true", help="Run OAuth flow to get access token")
    parser.add_argument("--app-id", help="Pinterest App ID")
    parser.add_argument("--app-secret", help="Pinterest App Secret")
    parser.add_argument("--access-token", help="Pinterest access token (or set PINTEREST_TOKEN env var)")
    parser.add_argument("--url", help="Article URL to pin")
    parser.add_argument("--title", help="Custom Pin title (auto-detected if omitted)")
    parser.add_argument("--category", default="", help="Category for hashtag matching")
    parser.add_argument("--board", help="Board name to pin to (creates if not found)")
    parser.add_argument("--create-boards", action="store_true", help="Create all category boards")
    parser.add_argument("--list-boards", action="store_true", help="List existing boards")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pinned")
    args = parser.parse_args()

    # --- Auth mode ---
    if args.auth:
        if not args.app_id or not args.app_secret:
            print("ERROR: --app-id and --app-secret required for auth")
            sys.exit(1)
        do_oauth(args.app_id, args.app_secret)
        return

    # --- Token ---
    token = args.access_token or os.environ.get("PINTEREST_TOKEN")
    if not token:
        # Try loading from saved file
        token_path = os.path.join(os.path.dirname(__file__), "pinterest_token.json")
        if os.path.exists(token_path):
            with open(token_path) as f:
                token = json.load(f).get("access_token")
    if not token:
        print("ERROR: No access token. Run with --auth first.")  
        sys.exit(1)

    client = PinterestClient(token)

    # --- List boards ---
    if args.list_boards:
        boards = client.list_boards()
        for b in boards:
            print(f"  [{b['id']}] {b['name']} — {b.get('description','')[:50]}")
        return

    # --- Create boards ---
    if args.create_boards:
        board_names = [
            ("headphones-audio", "Headphones & Audio — honest reviews and comparisons"),
            ("smartwatches-wearables", "Smartwatches & Wearables — tested picks"),
            ("home-office-gear", "Home Office Gear — desks, chairs, keyboards, monitors"),
            ("smartphones-tablets", "Smartphones & Tablets — budget to premium"),
            ("charging-accessories", "Charging & Accessories — cables, stations, power banks"),
            ("smart-home", "Smart Home — doorbells, cameras, lighting"),
        ]
        existing = {b["name"]: b["id"] for b in client.list_boards()}
        for name, desc in board_names:
            if name in existing:
                print(f"  ⏭️  Board '{name}' already exists")
            else:
                board = client.create_board(name, desc)
                print(f"  ✅ Created board '{name}' → {board['id']}")
        return

    # --- Pin mode ---
    if not args.url:
        print("ERROR: --url required for pinning")
        sys.exit(1)

    title, description, image_url = generate_pin_content(args.url, args.title, args.category)

    # Find or create board
    board_name = args.board or "tech-tools-hub-pins"
    boards = client.list_boards()
    board_id = None
    for b in boards:
        if b["name"].lower() == board_name.lower():
            board_id = b["id"]
            break

    if not board_id:
        if args.board:
            board = client.create_board(board_name, "Pins from Tech & Tools Hub")
            board_id = board["id"]
        else:
            # Use first available board
            board_id = boards[0]["id"]
            board_name = boards[0]["name"]

    if args.dry_run:
        print("=" * 50)
        print(f"DRY RUN — would pin to board: {board_name}")
        print(f"Title:       {title}")
        print(f"Link:        {args.url}")
        print(f"Image:       {image_url or '(none)'}")
        print(f"Description: {description[:200]}...")
        print("=" * 50)
        return

    result = client.create_pin(
        board_id=board_id,
        title=title,
        description=description,
        link=args.url,
        image_url=image_url,
    )
    print(f"✅ Pinned: {result.get('id', 'unknown')} to board '{board_name}'")
    print(f"   URL: {result.get('link', args.url)}")


if __name__ == "__main__":
    main()
