#!/usr/bin/env python3
"""
Structure Enforcer — runs AFTER humanizer.py, BEFORE seo_engine.py.
Detects missing viral review sections and restructures the article.
Works on the actual file content, not relying on LLM compliance.
"""
import re, sys
from pathlib import Path

REQUIRED_H2S = [
    ("## The Verdict", "If you only read one thing: buy the best one for your needs."),
    ("## Why Trust Me", "I tested these products myself. Here is what I actually did."),
    ("## Best Overall", None),
    ("## Runner-Up / Better Value", None),
    ("## Budget Pick Worth Considering", None),
    ("## Don't Waste Your Money On", None),
    ("## FAQ", "Q: Which one is best for most people?\nA: The winner above. It does the job without the gimmicks.\n\nQ: Should I wait for a sale?\nA: If you are not in a rush, prices drop 10-20% around major holidays."),
    ("## The Bottom Line", "Buy the winner if it fits your budget. Skip the rest."),
]

def enforce(filepath: Path) -> int:
    content = filepath.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if len(parts) < 3:
        print("   ❌ No frontmatter found")
        return 1
    
    frontmatter = "---" + parts[1] + "---"
    body = parts[2]
    
    # Remove JSON-LD
    if "<script" in body:
        idx = body.find("</script>")
        jsonld = body[:idx + len("</script>")] if idx >= 0 else ""
        body = body[idx + len("</script>"):].strip() if idx >= 0 else body
    
    # Get existing H2s
    existing_h2s = set()
    for m in re.finditer(r'^## (.+)$', body, re.MULTILINE):
        existing_h2s.add(m.group(1).strip())
    
    fixes = 0
    new_sections = []
    
    for h2_heading, fallback in REQUIRED_H2S:
        h2_name = h2_heading.replace("## ", "")
        # Check if this H2 exists (fuzzy: the heading name appears in any existing H2)
        found = False
        for eh2 in existing_h2s:
            # Match: "Best Overall", "Best Overall: Product ($X)", etc.
            if h2_name.lower() in eh2.lower() or eh2.lower() in h2_name.lower():
                found = True
                break
        
        if not found:
            if fallback:
                new_sections.append(f"{h2_heading}\n\n{fallback}")
            else:
                new_sections.append(f"{h2_heading}\n\n_Analysis coming soon._")
            fixes += 1
    
    if fixes == 0:
        print("   ✅ All 8 sections present")
        return 0
    
    # Append missing sections (don't mess with existing content)
    body = body.rstrip()
    for section in new_sections:
        body += f"\n\n{section}"
    
    # Ensure affiliate disclosure at end
    if "*As an Amazon Associate" not in body:
        body += "\n\n*As an Amazon Associate, I earn from qualifying purchases.*"
    
    new_content = frontmatter + "\n" + body
    filepath.write_text(new_content, encoding="utf-8")
    
    print(f"   🔧 Added {fixes} missing sections: {', '.join(s.split(chr(10))[0].replace('## ','') for s in new_sections)}")
    return 0

def main():
    posts_dir = Path("_posts")
    posts = sorted(posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not posts:
        print("No posts")
        return 0
    
    latest = posts[0]
    print(f"Structure check: {latest.name}")
    return enforce(latest)

if __name__ == "__main__":
    sys.exit(main())
