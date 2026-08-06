#!/usr/bin/env python3
"""
Newsletter Digest Engine — "This Week's Best 3 Buys" 
Runs every 3 days. Generates copy-paste ready email/newsletter content.

Output: _social/latest-newsletter.md — formatted for email, Bluesky thread, or substack.
"""
import json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
SITE_URL = "https://tech-tools-hub.netlify.app"
POSTS_DIR = Path("_posts")
OUT_DIR = Path("_social")

def call_deepseek(messages, max_tokens=1024, temperature=0.7):
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

def get_recent_posts(days: int = 3) -> list:
    """Get posts from the last N days."""
    posts = sorted(POSTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    recent = []
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    
    for p in posts:
        if p.stat().st_mtime > cutoff:
            content = p.read_text(encoding="utf-8")
            title = ""
            cat = ""
            desc = ""
            for line in content.split("\n"):
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"')
                if line.startswith("categories:"):
                    cat = line.split(":", 1)[1].strip()
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip('"')
                if title and cat:
                    break
            
            # Extract verdict section
            body = content.split("---", 2)[-1] if "---" in content else ""
            verdict = ""
            for section in ["The Verdict", "Best Overall", "The Bottom Line"]:
                idx = body.find(section)
                if idx >= 0:
                    snippet = body[idx:idx+400]
                    # Get first paragraph after heading
                    para = snippet.split("\n\n")[1] if "\n\n" in snippet else snippet[:200]
                    verdict = para[:200].strip()
                    break
            
            recent.append({
                "title": title,
                "category": cat,
                "description": desc,
                "verdict": verdict,
                "slug": p.stem,
            })
    
    return recent[:8]  # Max 8

def generate_newsletter(posts: list) -> str:
    """Generate newsletter from recent posts using AI."""
    if not posts:
        return "_No new articles this period._"
    
    # Build context for AI
    post_summaries = []
    for i, p in enumerate(posts[:5]):
        post_summaries.append(f"{i+1}. {p['title']}\n   Verdict: {p['verdict'][:150]}")
    
    context = "\n".join(post_summaries)
    
    prompt = f"""You are Lena, a tech reviewer in Shenzhen. Write a "This Week's Best 3 Buys" newsletter.

Style rules:
- Casual, like texting a friend. "Hey — here's what's actually worth buying this week."
- Pick the 3 BEST products from the list below. Rank them #1, #2, #3.
- For each: 1-2 sentences why it won + one honest flaw + price
- Format:
  # This Week's Best 3 Buys
  _[date range]_
  
  Hey,
  
  [2 sentence intro. Casual. Mention something about what you tested.]
  
  ## #1: [Product Name]
  [Why it wins. What you noticed. One flaw. Price.]
  
  ## #2: [Product Name]
  [Same format]
  
  ## #3: [Product Name]
  [Same format]
  
  ## Also worth a look:
  - [Product name] — [One sentence take]
  - [Product name] — [One sentence take]
  
  [One sentence closer. "省下这笔钱" or similar.]
  
  — Lena
  
  MAX 400 words total. No emoji in headers. No "I'm excited". Just honest recommendations.

Here are this period's articles:
{context}"""

    result = call_deepseek([{"role": "user", "content": prompt}], max_tokens=800, temperature=0.7)
    return result if result else ""

def main():
    print("\n📧 Newsletter Digest Engine")
    
    posts = get_recent_posts(days=3)
    if len(posts) < 2:
        # Extend to 5 days if not enough
        posts = get_recent_posts(days=5)
    
    print(f"   Found {len(posts)} recent articles")
    
    if len(posts) < 2:
        print("   ⏭️  Not enough articles for newsletter — need at least 2")
        return
    
    newsletter = generate_newsletter(posts)
    if not newsletter:
        print("   ❌ Generation failed")
        return
    
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "latest-newsletter.md"
    now = datetime.now(timezone.utc)
    
    with open(out_path, "w") as f:
        f.write(f"# Newsletter Digest — {now.strftime('%Y-%m-%d')}\n\n")
        f.write(f"Generated: {now.isoformat()}\n\n")
        f.write("---\n\n")
        f.write(newsletter)
        f.write("\n\n---\n\n")
        f.write("_Copy and paste into your newsletter platform.\n")
        f.write("Suggested subject line: This Week's Best 3 Buys — [pick one product]\n_")
    
    print(f"   ✅ Newsletter saved: {out_path}")
    word_count = len(newsletter.split())
    print(f"   Words: {word_count}")

if __name__ == "__main__":
    main()
