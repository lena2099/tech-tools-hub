#!/usr/bin/env python3
"""
Bluesky Opinion Engine — Standalone Lena opinion posts.
Runs independent of article distribution. Posts 2-3 standalone opinions per week.

What it does:
  1. Reads latest articles for content hooks
  2. Generates opinionated, non-promotional posts
  3. Posts to Bluesky with proper facets
  4. Avoids duplicating article-distribution posts
"""
import json, os, random
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

OPINION_TEMPLATES = [
    "hot_take",
    "price_rant", 
    "reddit_gem",
    "comparison_zing",
    "what_i_returned",
    "unpopular_opinion",
]

def call_deepseek(messages, max_tokens=512, temperature=0.9):
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

def generate_opinion():
    """Generate one Lena opinion post. Returns (text, url_if_any) or None."""
    template = random.choice(OPINION_TEMPLATES)
    
    prompts = {
        "hot_take": """You are Lena, a tech reviewer in Shenzhen. Write ONE Bluesky post (max 250 chars) with a hot take about a tech product. 
        Be provocative but honest. Mention a specific product name and price. 
        No hashtags unless naturally part of sentence. No links. 
        Style: "Just tried [product]. [unexpected observation]. [Price] is [adjective]." 
        If you wouldn't say it to a friend over coffee, don't write it.""",
        
        "price_rant": """You are Lena. Write ONE Bluesky post (max 250 chars) about a tech product whose price makes no sense.
        Compare a cheap product that's 80% as good to an expensive one. Name both products and prices.
        No links. No hashtags.
        Style: "¥249 的 [cheap] vs ¥2299 的 [expensive]。差10倍价格，差距有没有10倍？[结论]。" """,
        
        "reddit_gem": """You are Lena. Write ONE Bluesky post (max 250 chars) sharing an interesting Reddit finding.
        Quote or paraphrase a real-sounding Reddit complaint about a popular tech product.
        Add your take. No links. No hashtags.
        Format: "Reddit上有人发了条：[quote]。看完我只有一个想法：[your reaction]。" """,
        
        "comparison_zing": """You are Lena. Write ONE Bluesky post (max 250 chars) comparing two products in the same category.
        One surprising winner, one surprising loser. Prices. No links. No hashtags.
        Style: "[Product A] is $XXX. [Product B] is $XX. You'd think [A is better], but actually [surprise]." """,
        
        "what_i_returned": """You are Lena. Write ONE Bluesky post (max 250 chars) about a product you returned and why.
        Make it sound like a real, disappointing experience. Specific reason. No links.
        Style: "退了[product]。不是因为[obvious reason]。是因为[specific annoying thing that matters]。" """,
        
        "unpopular_opinion": """You are Lena. Write ONE Bluesky post (max 250 chars) with an unpopular tech opinion.
        Something that goes against Reddit consensus. Be specific. Name products. No links.
        Style: "Unpopular opinion: [statement]. Everyone says [consensus], but [your counter]. [One sentence proof]." """,
    }
    
    prompt = prompts.get(template, prompts["hot_take"])
    result = call_deepseek([{"role": "user", "content": prompt}], max_tokens=300, temperature=0.9)
    
    if not result or len(result) < 30:
        return None
    
    # Clean up — remove quotes, limit length
    text = result.strip().strip('"').strip("'")
    if len(text) > 280:
        text = text[:277] + "..."
    
    return text

def post_to_bluesky(text: str):
    """Post a standalone opinion to Bluesky."""
    if not BLUESKY_HANDLE or not BLUESKY_PASSWORD:
        print("   ⏭️  No Bluesky credentials")
        return False

    try:
        sp = json.dumps({"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD}).encode()
        session = json.loads(urlopen(Request(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            data=sp, headers={"Content-Type": "application/json"}), timeout=15).read())
        token = session["accessJwt"]

        record = {
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        pp = json.dumps({"repo": session["did"], "collection": "app.bsky.feed.post", "record": record}).encode()
        urlopen(Request("https://bsky.social/xrpc/com.atproto.repo.createRecord",
            data=pp, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}), timeout=15)
        return True
    except Exception as e:
        print(f"   ⚠️  Bluesky post failed: {e}")
        return False

def should_post_today() -> bool:
    """Check if we should post an opinion today (avoid spamming)."""
    log_path = Path("_dist/opinion_log.json")
    if not log_path.exists():
        return True
    
    try:
        with open(log_path) as f:
            log = json.load(f)
        last = datetime.fromisoformat(log[-1]["timestamp"])
        hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return hours > 18  # At most one opinion per ~18 hours
    except:
        return True

def main():
    print("💬 Bluesky Opinion Engine")
    
    if not should_post_today():
        print("   ⏭️  Already posted recently — skipping")
        return
    
    opinion = generate_opinion()
    if not opinion:
        print("   ❌ Generation failed")
        return
    
    print(f"   Generated: {opinion[:80]}...")
    
    ok = post_to_bluesky(opinion)
    if ok:
        print(f"   ✅ Posted to Bluesky")
        # Log it
        log_path = Path("_dist/opinion_log.json")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = []
        if log_path.exists():
            with open(log_path) as f:
                log = json.load(f)
        log.append({"timestamp": datetime.now(timezone.utc).isoformat(), "text": opinion})
        with open(log_path, "w") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
    else:
        print("   ❌ Post failed")

if __name__ == "__main__":
    main()
