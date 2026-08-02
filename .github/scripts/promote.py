#!/usr/bin/env python3
"""
Prometheus — Social distribution engine.
Triggered automatically after Athena publishes a new article.
Generates platform-optimized social content, publishes where possible,
saves reports to _social/.
"""
import json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEVTO_KEY = os.environ.get("DEVTO_API_KEY", "")
MEDIUM_TOKEN = os.environ.get("MEDIUM_TOKEN", "")
TWITTER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN", "")
SITE_URL = "https://lena2099.github.io/tech-tools-hub"
OUT_DIR = Path("_posts")
SOCIAL_DIR = Path("_social")


def call_deepseek(messages, max_tokens=2048, temperature=0.8):
    req = Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps({
            "model": "deepseek-chat",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode(),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    resp = json.loads(urlopen(req, timeout=90).read())
    return resp["choices"][0]["message"]["content"]


def generate_twitter_thread(title, body, url):
    excerpt = body[:2000]
    prompt = f"""Write a Twitter/X thread promoting this article.

TWEET 1 (hook): A provocative question or surprising claim. Max 240 chars.
TWEET 2-3: Expand with specific insight or contrarian take. Max 240 chars each.
LAST TWEET: Link: {url}

VOICE: First person, opinionated. Like someone who tests products.
AVOID: Thread emojis, hashtags over 2, corporate speak, "check out my article".

TITLE: {title}
EXCERPT: {excerpt}

Return ONLY a JSON array: ["tweet1","tweet2",...]"""
    try:
        text = call_deepseek([{"role": "user", "content": prompt}], max_tokens=1500)
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())[:5]
    except:
        pass
    return [f"{title}\n{url}"]


def generate_reddit_post(title, body, url):
    excerpt = body[:1500]
    prompt = f"""Write a Reddit post promoting this article. Rules:
- Personal experience or hot take (NOT "I wrote an article")
- 1-2 specific product recommendations
- End: "I went deeper: {url}"
- NO "hey Reddit", "hope this helps", "let me know"
- Max 800 chars. Real redditor voice.

TITLE: {title}
CONTENT: {excerpt}

Return ONLY the post text."""
    try:
        return call_deepseek([{"role": "user", "content": prompt}], max_tokens=800)
    except:
        return f"{excerpt[:400]}...\n\nFull guide: {url}"


def generate_linkedin_post(title, body, url):
    excerpt = body[:1500]
    prompt = f"""Write a LinkedIn post. Rules:
- Bold statement or counterintuitive observation
- 3-4 short paragraphs, 2-3 sentences each
- One practical takeaway
- End: {url}
- NO hashtags, NO emoji spam, NO "excited to share", NO corporate tone
- Casual but professional.

TITLE: {title}
CONTENT: {excerpt}

Return ONLY the post text."""
    try:
        return call_deepseek([{"role": "user", "content": prompt}], max_tokens=600)
    except:
        return f"{title}\n\n{excerpt[:300]}...\n{url}"


def publish_to_x(tweets):
    if not TWITTER_TOKEN:
        return {"status": "skipped", "reason": "no token"}
    posted = []
    reply_to = None
    for i, tweet_text in enumerate(tweets):
        payload = {"text": tweet_text}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}
        try:
            req = Request(
                "https://api.twitter.com/2/tweets",
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {TWITTER_TOKEN}", "Content-Type": "application/json"},
                method="POST",
            )
            resp = json.loads(urlopen(req, timeout=15).read())
            tweet_id = resp.get("data", {}).get("id", "")
            posted.append(tweet_id)
            reply_to = tweet_id if i == 0 else reply_to
            time.sleep(2)
        except Exception as e:
            return {"status": "partial" if posted else "failed", "posted": len(posted), "error": str(e)[:150]}
    return {"status": "success", "tweets": len(posted), "ids": posted}


def publish_to_devto(title, body, url, tags):
    if not DEVTO_KEY:
        return {"status": "skipped", "reason": "no key"}
    payload = {"article": {
        "title": title, "body_markdown": body, "published": True,
        "tags": tags[:4], "canonical_url": url,
    }}
    try:
        req = Request(
            "https://dev.to/api/articles",
            data=json.dumps(payload).encode(),
            headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
            method="POST",
        )
        resp = json.loads(urlopen(req, timeout=20).read())
        return resp if "url" in resp else {"status": "failed", "error": str(resp)[:150]}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:150]}


def main():
    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True)
    if not posts:
        print("No posts found")
        return

    latest = posts[0]
    content = latest.read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        print("Invalid frontmatter")
        return

    fm_text = parts[1]
    body = parts[2]

    title = ""
    tags = []
    for line in fm_text.split("\n"):
        if line.startswith("title:"):
            title = line.split(":", 1)[1].strip().strip('"')
        if line.strip().startswith("- ") and not line.startswith("tags:"):
            # Only collect tags after we've seen the tags: line
            pass

    if not title:
        m = re.search(r"^# (.+)$", body, re.MULTILINE)
        title = m.group(1) if m else latest.stem

    # Build article URL
    parts_name = latest.stem.split("-", 3)
    if len(parts_name) >= 4:
        article_url = f"{SITE_URL}/{parts_name[0]}/{parts_name[1]}/{parts_name[2]}/{parts_name[3]}.html"
    else:
        article_url = SITE_URL

    report = {
        "article": title,
        "url": article_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platforms": {},
    }

    print(f"Promoting: {title}")
    print(f"URL: {article_url}")

    # Twitter
    print("\nTwitter/X...")
    tweets = generate_twitter_thread(title, body, article_url)
    report["platforms"]["twitter"] = {
        "tweets": tweets,
        "published": publish_to_x(tweets) if TWITTER_TOKEN else {"status": "skipped"},
    }
    for i, t in enumerate(tweets):
        print(f"  Tweet {i+1}: {t[:80]}...")

    # Reddit
    print("\nReddit...")
    reddit_post = generate_reddit_post(title, body, article_url)
    reddit_file = SOCIAL_DIR / f"{latest.stem}_reddit.md"
    reddit_file.write_text(reddit_post)
    report["platforms"]["reddit"] = {"file": str(reddit_file), "text": reddit_post[:200]}
    print(f"  Saved: {reddit_file}")

    # LinkedIn
    print("\nLinkedIn...")
    linkedin_post = generate_linkedin_post(title, body, article_url)
    linkedin_file = SOCIAL_DIR / f"{latest.stem}_linkedin.md"
    linkedin_file.write_text(linkedin_post)
    report["platforms"]["linkedin"] = {"file": str(linkedin_file), "text": linkedin_post[:200]}
    print(f"  Saved: {linkedin_file}")

    # dev.to
    print("\ndev.to...")
    devto_result = publish_to_devto(title, body, article_url, tags)
    report["platforms"]["devto"] = devto_result
    print(f"  {devto_result.get('status', '?')}")

    # Save report
    report_path = SOCIAL_DIR / f"{latest.stem}_promote.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
