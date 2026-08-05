#!/usr/bin/env python3
"""
One-shot: rewrite all existing articles with human-writing rules.
Runs in GitHub Actions (has access to ${{ secrets.DEEPSEEK_API_KEY }}).
"""
import json, os, re, base64, time
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
REPO = "lena2099/tech-tools-hub"
HEADERS = {"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"}

if not API_KEY:
    print("❌ DEEPSEEK_API_KEY not set")
    exit(1)
if not GH_TOKEN:
    print("❌ GH_TOKEN not set")
    exit(1)

REWRITE_PROMPT = """You are a ruthless human-writing editor. Rewrite the following tech product review to sound like a real person, not AI.

RULES (violation = rewrite again):
1. OPEN WITH PUNCHLINE. First sentence = strongest opinion. No buildup.
   ❌ "In this article..." / "Looking for..." / generic context
   ✅ "I returned two pairs before finding these." / "The Sony XM6 is not worth $50 more than the XM5."
2. SPECIFICS > ADJECTIVES. "7.5 hours on a Teams call" not "great battery life"
3. EVERY product gets an honest FLAW. Not "no backlight" but real complaints.
4. ZERO corporate speak. No "leveraging", "best-in-class", "game-changing"
5. ACTIVE voice, present tense. "I tested" not "was tested."
6. SHORT paragraphs. 40-80 words max. Contractions. Grade 8-10.
7. END with a takeaway, not "In conclusion..."
8. VOICE: texting a friend who asked "what should I buy?" — casual, opinionated, first-person.
9. PRESERVE all markdown links ([text](url)) exactly as-is. Do not change any URLs.
10. PRESERVE all product names. Add specific Reddit/community details if you can infer them naturally.

BANNED:
- "In today's digital age", "fast-paced world", "seasoned professional or just starting out"
- "We're excited/thrilled/delighted", "game-changing", "revolutionary", "cutting-edge"
- "Unlock your potential", "take your X to the next level", "Let's dive in"
- "Without further ado", "At the end of the day", "In conclusion", "To sum up"
- "Leveraging", "Seamlessly", "Best-in-class", "Enterprise-grade"
- Any sentence starting with "Imagine..." or "Picture this"

Rewrite the ENTIRE article body below. Keep the same structure (headings, sections) but make every sentence sound human.
Output ONLY the rewritten body — no explanations, no "Here's the rewrite:", no markdown fences.

---
"""

def call_deepseek(prompt: str, max_tokens: int = 4096) -> str:
    """Call DeepSeek API with retries."""
    for attempt in range(3):
        try:
            req = Request("https://api.deepseek.com/chat/completions",
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                }).encode(),
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
            resp = json.loads(urlopen(req, timeout=120).read())
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  ⚠️  Attempt {attempt+1}: {e}")
            time.sleep(5)
    return ""

def get_all_posts():
    """Get list of all post files from GitHub."""
    req = Request(f"https://api.github.com/repos/{REPO}/contents/_posts", headers=HEADERS)
    data = json.loads(urlopen(req, timeout=15).read())
    return sorted(data, key=lambda x: x["name"])

def update_post(post):
    """Rewrite a single post and push to GitHub."""
    name = post["name"]
    sha = post["sha"]
    
    # Read current content
    req = Request(post["url"], headers=HEADERS)
    data = json.loads(urlopen(req, timeout=15).read())
    content = base64.b64decode(data["content"]).decode()
    
    # Split: frontmatter + JSON-LD + body
    # Find the second --- (end of frontmatter)
    fm_end = content.find("---", 4)
    if fm_end < 0:
        print(f"  ⚠️  {name}: can't parse frontmatter")
        return False
    
    frontmatter = content[:fm_end+3]
    rest = content[fm_end+3:].strip()
    
    # Find JSON-LD block
    jsonld_end = rest.find("</script>")
    if jsonld_end >= 0:
        jsonld = rest[:jsonld_end+9]
        body = rest[jsonld_end+9:].strip()
    else:
        jsonld = ""
        body = rest
    
    if len(body) < 100:
        print(f"  ⚠️  {name}: body too short ({len(body)} chars)")
        return False
    
    print(f"  📝 {name} ({len(body)} chars) → rewriting...")
    
    # Call DeepSeek
    prompt = REWRITE_PROMPT + body
    new_body = call_deepseek(prompt, max_tokens=min(len(body) * 2, 4096))
    
    if not new_body or len(new_body) < 50:
        print(f"  ❌ {name}: API returned empty/short response")
        return False
    
    # Clean up response (sometimes DeepSeek adds markdown fences)
    new_body = new_body.strip()
    if new_body.startswith("```"):
        new_body = re.sub(r'^```\w*\n?', '', new_body)
        new_body = re.sub(r'\n?```$', '', new_body)
    
    # Reassemble
    if jsonld:
        new_content = f"{frontmatter}\n{jsonld}\n\n{new_body.strip()}"
    else:
        new_content = f"{frontmatter}\n{new_body.strip()}"
    
    # Quick quality check
    banned = ["in today's digital age", "game-changing", "revolutionary", "cutting-edge",
              "we're excited", "let's dive in", "without further ado", "unlock your potential",
              "leveraging", "seamlessly", "best-in-class", "enterprise-grade"]
    violations = [b for b in banned if b in new_body.lower()]
    if violations:
        print(f"  ⚠️  {name}: {len(violations)} banned phrases remain: {violations[:3]}")
    
    # Push to GitHub
    payload = {
        "message": f"rewrite: human-writing skill applied to {name.replace('.md','')[:40]}",
        "content": base64.b64encode(new_content.encode()).decode(),
        "sha": sha,
    }
    
    for attempt in range(3):
        try:
            req3 = Request(
                f"https://api.github.com/repos/{REPO}/contents/_posts/{name}",
                headers=HEADERS,
                data=json.dumps(payload).encode(),
                method="PUT"
            )
            resp3 = json.loads(urlopen(req3, timeout=15).read())
            print(f"  ✅ {name}: pushed {resp3['content']['sha'][:12]}")
            return True
        except Exception as e:
            print(f"  ⚠️  Push attempt {attempt+1}: {e}")
            time.sleep(3)
    return False

def main():
    posts = get_all_posts()
    print(f"📚 {len(posts)} articles to rewrite\n")
    
    rewritten = 0
    failed = 0
    
    for i, post in enumerate(posts):
        print(f"[{i+1}/{len(posts)}] ", end="")
        if update_post(post):
            rewritten += 1
        else:
            failed += 1
        
        # Rate limit: 3s between API calls
        time.sleep(3)
    
    print(f"\n{'='*60}")
    print(f"Done: {rewritten} rewritten, {failed} failed")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
