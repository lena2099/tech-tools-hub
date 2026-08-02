#!/usr/bin/env python3
"""
Humanizer — Post-processes Athena articles to remove AI markers.
Runs after agent.py, before SEO engine.
Uses DeepSeek to rewrite the article in a natural, personal voice.
"""
import json, os, re, sys
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY = os.environ["DEEPSEEK_API_KEY"]
OUT_DIR = Path("_posts")

def humanize_article(content: str) -> str:
    """Rewrite article to sound human, keeping all Amazon links intact."""
    
    # Extract frontmatter and body
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content
    frontmatter = parts[1]
    body = parts[2]
    
    # Extract Amazon links so we can preserve them
    amzn_links = re.findall(r'\[([^\]]*)\]\((https://www\.amazon\.com/[^)]+)\)', body)
    
    prompt = f"""Rewrite this article to sound like a real person wrote it. Rules:

MUST DO:
- First-person, casual, opinionated (like texting a friend)
- At least one personal experience detail or specific opinion
- Short paragraphs (2-4 sentences max)
- Contractions (don't, can't, I've)
- Keep all Amazon links exactly as they are
- Keep the heading structure (#, ##)
- Keep affiliate disclosure line

MUST NOT:
- NO "You're looking for X but the market is confusing"
- NO "After hours of testing" or "I've tested"
- NO "game-changer", "revolutionary", "whether you're on a budget or"
- NO numbered feature lists
- NO phrases like "let's dive in", "the truth is", "without further ado"
- NO generic pros/cons lists — give specific, honest drawbacks

Amazon links to preserve (use exactly as-is):
{chr(10).join(f'  [{text}]({url})' for text, url in amzn_links)}

Article:
{body[:3000]}

Return ONLY the rewritten body, no JSON, no explanations."""

    try:
        req = Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 3072,
                "temperature": 0.8,
            }).encode(),
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        )
        resp = json.loads(urlopen(req, timeout=120).read())
        rewritten = resp["choices"][0]["message"]["content"]
        
        # Reassemble
        return f"---{frontmatter}---\n{rewritten}"
    except Exception as e:
        print(f"  ⚠️ Humanizer failed: {e}. Using original.")
        return content


def main():
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True)
    if not posts:
        print("No posts found")
        return
    
    latest = posts[0]
    content = latest.read_text()
    
    print(f"🖊️  Humanizing: {latest.name}")
    humanized = humanize_article(content)
    latest.write_text(humanized)
    print(f"   Done. {len(humanized)} chars → {len(content)} chars")


if __name__ == "__main__":
    main()
