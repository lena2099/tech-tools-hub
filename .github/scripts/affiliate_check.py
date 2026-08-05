#!/usr/bin/env python3
"""
Affiliate link validator — runs after article generation.
REQUIRES: ASIN product links (/dp/), inline in body, no search links (/s?k/).
Blocks publishing if any rule is violated.
"""
import sys, re
from pathlib import Path

MIN_AFFILIATE_LINKS = 2
TAG = "technolo0b423-20"

def validate_article(filepath: Path) -> tuple[int, list[str]]:
    content = filepath.read_text(encoding='utf-8')

    issues = []

    # Find ALL Amazon links
    dp_links = re.findall(r'https://www\.amazon\.com/dp/[A-Z0-9]+\?tag=' + TAG, content)
    search_links = re.findall(r'https://www\.amazon\.com/s\?k=[^"\s]+.*?tag=' + TAG, content)
    all_links = re.findall(r'https://www\.amazon\.com/[^"\s]*?tag=' + TAG, content)

    total_dp = len(dp_links)
    total_search = len(search_links)
    total = len(all_links)

    # ═══ HARD BLOCKERS ═══

    # 1. Search links are FORBIDDEN
    if total_search > 0:
        issues.append(
            f"BLOCKED: Found {total_search} search link(s) (/s?k=). "
            f"Search links are prohibited. Use ASIN product links (/dp/ASIN) only."
        )

    # 2. Minimum link count
    if total < MIN_AFFILIATE_LINKS:
        issues.append(
            f"BLOCKED: Only {total} affiliate link(s). Minimum required: {MIN_AFFILIATE_LINKS}"
        )

    # 3. Links must be inline (not dumped at bottom)
    # Check for "Check price on Amazon" pattern (indicates link dump)
    if re.search(r'Check price on Amazon', content, re.IGNORECASE):
        issues.append(
            "BLOCKED: 'Check price on Amazon' link dump detected. "
            "Links must be INLINE on product names in body text."
        )

    # 4. All links should be dp links
    non_dp = total - total_dp - total_search
    if total_dp < total * 0.7 and total > 0:
        issues.append(
            f"BLOCKED: Only {total_dp}/{total} links are ASIN product links (/dp/). "
            f"At least 70% must be ASIN links."
        )

    # 5. Disclosure check
    has_disclosure = "Amazon Associate" in content and "qualifying purchases" in content
    if not has_disclosure:
        issues.append("Missing affiliate disclosure")

    return total, issues

def main():
    posts_dir = Path("_posts")
    posts = sorted(posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not posts:
        print("⏭️  No posts to validate")
        return 0

    latest = posts[0]
    print(f"🔍 Validating: {latest.name}")

    count, issues = validate_article(latest)

    if issues:
        print(f"\n❌ AFFILIATE CHECK FAILED:")
        for issue in issues:
            print(f"   → {issue}")
        print(f"\n   Status: ASIN links={len(re.findall(r'/dp/', latest.read_text()))}, search links blocked")
        return 1

    print(f"✅ Affiliate check passed: {count} ASIN product links + disclosure + inline format")

    return 0

if __name__ == "__main__":
    sys.exit(main())
