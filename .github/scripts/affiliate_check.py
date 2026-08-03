#!/usr/bin/env python3
"""
Affiliate link validator — runs after article generation.
Blocks publishing if Amazon affiliate links are absent or insufficient.

Called by agent.yml workflow after seo_engine.py.
"""
import sys, re
from pathlib import Path

MIN_AFFILIATE_LINKS = 2
TAG = "technolo0b423-20"

def validate_article(filepath: Path) -> tuple[int, list[str]]:
    """Returns (count of valid affiliate links, list of issues)."""
    content = filepath.read_text(encoding='utf-8')
    issues = []
    
    # Find ALL Amazon links with affiliate tag (dp, search, and any other)
    dp_links = re.findall(r'https://www\.amazon\.com/dp/[A-Z0-9]+\?tag=' + TAG, content)
    search_links = re.findall(r'https://www\.amazon\.com/s\?k=[^"\s]+.*?tag=' + TAG, content)
    
    total_dp = len(dp_links)
    total_search = len(search_links)
    total = total_dp + total_search
    
    # Also check for the disclosure
    has_disclosure = "Amazon Associate" in content and "qualifying purchases" in content
    
    if total < MIN_AFFILIATE_LINKS:
        issues.append(
            f"Only {total} affiliate links ({total_dp} ASIN + {total_search} search). "
            f"Minimum required: {MIN_AFFILIATE_LINKS}"
        )
    
    if not has_disclosure:
        issues.append("Missing affiliate disclosure")
    
    return total, issues

def main():
    posts_dir = Path("_posts")
    posts = sorted(posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not posts:
        print("⏭️  No posts to validate")
        return 0
    
    # Validate the most recent post
    latest = posts[0]
    print(f"🔍 Validating: {latest.name}")
    
    count, issues = validate_article(latest)
    
    if issues:
        print(f"\n❌ AFFILIATE CHECK FAILED ({count} links):")
        for issue in issues:
            print(f"   → {issue}")
        print(f"\n   This article will NOT be published.")
        print(f"   Fix: add products to products.json for this category,")
        print(f"   or set DRY_RUN=1 to skip the check.")
        return 1
    
    print(f"✅ Affiliate check passed: {count} product links + disclosure")
    return 0

if __name__ == "__main__":
    sys.exit(main())
