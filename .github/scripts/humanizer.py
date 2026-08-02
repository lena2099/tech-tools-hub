#!/usr/bin/env python3
"""
Humanizer v2 — Post-processes Athena articles with structural randomization.
Each run picks a different structural template so consecutive articles
never feel like the same person wrote them back-to-back.
"""
import json, os, random, re, sys
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY = os.environ["DEEPSEEK_API_KEY"]
OUT_DIR = Path("_posts")
TAG = "technolo0b423-20"

# ═══════════════════════════════════════════════════════════
# STRUCTURE POOL — 6 distinct article shapes
# ═══════════════════════════════════════════════════════════

STRUCTURES = [
    {
        "name": "personal-journey",
        "opening": "Start with a specific personal story — a product you bought, a mistake you made, a realization you had. Concrete details. Then pivot: 'If you're in the same boat, here's what I'd tell you.'",
        "body_flow": "No sections, no subheadings beyond product names. Just write conversationally about each product as it comes up. Transition naturally ('I tried X too, but...' or 'The alternative is...')",
        "product_style": "One paragraph per product. Don't list pros/cons. Weave them into the paragraph: 'The hinge is flimsy but the screen is gorgeous and I've dropped it twice without a scratch.'",
        "closing": "End abruptly. No summary. Just a closing thought or another personal observation. Like you ran out of things to say.",
        "avoid": "No tables, no comparison lists, no 'here are the options', no numbered recommendations.",
    },
    {
        "name": "direct-answer",
        "opening": "First sentence IS the recommendation. 'Buy the Sony. Here's why.' Then backfill the reasoning. No buildup, no story.",
        "body_flow": "Explain the winner first (2-3 paragraphs why it's the best). Then one paragraph each on alternatives and when you'd pick them instead. Don't use headings — just paragraph breaks.",
        "product_style": "Focus on what each product does DIFFERENTLY from the winner. 'The Bose is more comfortable but costs $100 more. If you wear glasses, it's worth it.'",
        "closing": "One sentence: 'Get the [winner] unless [specific exception].'",
        "avoid": "No comparison tables, no feature lists, no pros/cons format. No introduction — jump straight in.",
    },
    {
        "name": "myth-busting",
        "opening": "Start by calling out a common belief: 'Everyone says you need X. They're wrong.' Or 'The most popular recommendation is actually bad advice.' Provocative, opinionated.",
        "body_flow": "Tear down the myth first (2 paragraphs). Then give the real answer. Each product recommendation answers a different actual need — not the myth.",
        "product_style": "Frame each product as 'here's when this actually makes sense.' No generic praise. Only recommend when the use case is real.",
        "closing": "Reinforce the contrarian take. 'Stop buying X. Start buying based on Y.'",
        "avoid": "No balanced 'on one hand/on the other hand' tone. Pick a side. No disclaimers until the very end.",
    },
    {
        "name": "scene-setting",
        "opening": "Describe a scene. 'It's 2 AM, your deadline is in 6 hours, and your current setup just gave you a blue screen.' Or 'You're on a beach, trying to hear your music over the waves, and your phone speaker isn't cutting it.' Paint the moment.",
        "body_flow": "Stay in the scene, then zoom out. 'That's when you realize what actually matters is...' Then talk products through the lens of that specific scenario.",
        "product_style": "Evaluate each product against the scene: 'This one would have survived the beach. That one would have died in the first 10 minutes.'",
        "closing": "Return to the scene. Circle back. 'Next time you're in that situation, you'll know what to reach for.'",
        "avoid": "No bullet points, no specs tables. No generic 'here are the best products' framing.",
    },
    {
        "name": "question-chain",
        "opening": "Open with 2-3 rapid-fire questions: 'Do you actually need 4K? Can your laptop even drive it? Are you putting this on a 60cm-deep desk?' Reader answers in their head, self-qualifies.",
        "body_flow": "Each question leads to a product recommendation. 'If you answered yes to Q1, get X. If no, Y is better.' No long paragraphs — quick, decisive.",
        "product_style": "One sentence to identify the best user for each product. Then 1-2 sentences of color. Don't over-explain.",
        "closing": "A single question to the reader: 'So — which setup are you on?' Or 'Which one fits your situation?'",
        "avoid": "No backstory. No 'when I was shopping.' No filler. Tight.",
    },
    {
        "name": "what-id-buy",
        "opening": "Start with 'If I had to spend my own money today, I'd buy...' Give the answer immediately. No suspense, no buildup.",
        "body_flow": "Explain your pick (2 paragraphs). Then mention what you'd buy if budget were different (one cheaper pick, one more expensive pick). Explain why you're NOT buying the obvious alternatives.",
        "product_style": "Strong opinions. 'I would not buy X because...' 'I returned Y after a week because...' Don't be neutral.",
        "closing": "Reiterate the pick. 'Seriously. Just get the [product]. You'll thank me in 6 months.'",
        "avoid": "No balanced review tone. No 'depends on your needs.' Pick and defend. One clear recommendation.",
    },
]


# ═══════════════════════════════════════════════════════════
# HUMANIZER
# ═══════════════════════════════════════════════════════════

def pick_structure(latest_post_name: str = "") -> dict:
    """Pick a random structure deterministically offset from the previous article.
    Uses the filename hash so consecutive runs vary without external state."""
    # Use the post filename to seed a deterministic-but-varying pick
    # Each new post has a different name → different structure
    seed = sum(ord(c) for c in latest_post_name)
    rng = random.Random(seed)
    # Pick any of the 6 structures, deterministic per post
    return STRUCTURES[rng.randint(0, len(STRUCTURES) - 1)]


def humanize_article(content: str, structure: dict) -> str:
    """Rewrite article using a specific structural template."""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content
    frontmatter = parts[1]
    body = parts[2]

    # Extract all Amazon links
    amzn_links = re.findall(
        r'\[([^\]]*)\]\((https://www\.amazon\.com/[^)]+)\)', body
    )

    prompt = f"""Rewrite this product recommendation article. Follow the structural template exactly.

STRUCTURAL TEMPLATE: "{structure['name']}"

OPENING STYLE:
{structure['opening']}

BODY FLOW:
{structure['body_flow']}

HOW TO DESCRIBE PRODUCTS:
{structure['product_style']}

CLOSING STYLE:
{structure['closing']}

WHAT TO AVOID:
{structure['avoid']}

VOICE RULES (ALWAYS):
- First person, casual. Like texting a knowledgeable friend.
- Short paragraphs (2-4 sentences).
- Contractions (don't, can't, I've).
- At least one honest, specific thing you dislike about a product. Not vague — real details.
- One personal detail or observation. Something you actually noticed using the product.
- No AI phrases: "game-changer", "revolutionary", "whether you're on a budget", "after hours of testing", "let's dive in", "the truth is", "without further ado".
- No numbered feature lists. No comparison tables.
- Grade 8-10 readability. Short sentences. No corporate jargon.

AMAZON LINKS — preserve EXACTLY:
{chr(10).join(f'  [{text}]({url})' for text, url in amzn_links)}

AFFILIATE DISCLOSURE — keep at the bottom:
*As an Amazon Associate, I earn from qualifying purchases.*

ARTICLE:
{body[:4000]}

Return ONLY the rewritten body in Markdown. No JSON, no explanations. Keep all Amazon links exactly as provided."""

    try:
        req = Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 3072,
                "temperature": 0.85,
            }).encode(),
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        )
        resp = json.loads(urlopen(req, timeout=120).read())
        rewritten = resp["choices"][0]["message"]["content"]
        return f"---{frontmatter}---\n{rewritten}"
    except Exception as e:
        print(f"  ⚠️  Humanizer failed: {e}. Using original.")
        return content


def main():
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True)
    if not posts:
        print("No posts found")
        return

    latest = posts[0]
    content = latest.read_text()

    structure = pick_structure(latest.name)
    print(f"🎲 Structure: {structure['name']}")
    print(f"🖊️  Humanizing: {latest.name}")

    humanized = humanize_article(content, structure)
    latest.write_text(humanized)

    print(f"   Done. {len(humanized)} chars")


if __name__ == "__main__":
    main()
