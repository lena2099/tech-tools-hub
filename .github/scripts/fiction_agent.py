#!/usr/bin/env python3
"""
Athena Fiction Agent — Daily LitRPG chapter generator.
Generates one chapter per run, persists story state, auto-publishes.
"""
import json, os, re, sys, textwrap
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY = os.environ["DEEPSEEK_API_KEY"]
FICTION_DIR = Path("_fiction")
STATE_FILE = FICTION_DIR / "story_state.json"
CHAPTERS_DIR = Path("_chapters")
SITE_URL = "https://lena2099.github.io/tech-tools-hub"
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"


# ── STATE PERSISTENCE ────────────────────────────────────
def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── LLM ──────────────────────────────────────────────────
def call_deepseek(messages, max_tokens=4096, temperature=0.8):
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
    resp = json.loads(urlopen(req, timeout=180).read())
    return resp["choices"][0]["message"]["content"]


# ── CHAPTER ──────────────────────────────────────────────
def generate_chapter(state: dict) -> dict:
    chapter_num = state["chapters_published"] + 1
    last_summary = state["last_chapter_summary"]

    # Build the system prompt — world rules + current state
    p = state["protagonist"]
    s = state["system"]
    w = state["world"]

    system_prompt = textwrap.dedent(f"""\
    You are a LitRPG fiction writer. Write the next chapter of the ongoing serial: "{state['title']}".

    ── STORY CONTEXT ──
    Protagonist: {p['name']}, {p['age']}, {p['background']}. Class: {p['class']}. Personality: {p['personality']}. Goal: {p['goal']}.
    System: {s['name']}. Personality: {s['personality']}. Core ability: {s['core_ability']}. Stats: {', '.join(s['stats'])}.
    World: {w['name']} — {w['setting']}. Factions: {', '.join(w['factions'])}.
    Story threads: {'; '.join(state['story_threads'])}.

    ── LAST CHAPTER SUMMARY ──
    {last_summary}

    ── RULES ──
    1. Write ONLY Chapter {chapter_num}. Do NOT summarize previous chapters in narrative.
    2. Length: 1500-2000 words.
    3. Every chapter MUST include at least one system interaction — stat display, skill check, level-up, or N.E.X.U.S banter.
    4. End with a hook/cliffhanger that makes readers want the next chapter.
    5. Format: clean Markdown. Use ## for scene breaks. Use > for system messages.
    6. At the very end, write an `<!-- SUMMARY: ... -->` HTML comment with a 2-sentence summary of what happened (for state tracking).
    7. Do NOT write "Chapter X:" header — I'll add that separately.
    """)

    user_prompt = f"Write Chapter {chapter_num} of System Breaker. Last chapter ended with: {last_summary}. Make it gripping."

    print(f"\n✍️  Generating Chapter {chapter_num}...")
    content = call_deepseek(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        max_tokens=4096, temperature=0.85,
    )

    # Extract summary from the <!-- SUMMARY: ... --> comment
    summary_match = re.search(r"<!--\s*SUMMARY:\s*(.+?)\s*-->", content, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else f"Chapter {chapter_num} continues the story."
    content = re.sub(r"<!--\s*SUMMARY:.*?-->", "", content, flags=re.DOTALL).strip()

    return {
        "number": chapter_num,
        "content": content,
        "summary": summary,
        "word_count": len(content.split()),
    }


# ── SAVE ─────────────────────────────────────────────────
def save_chapter(chapter: dict, state: dict) -> Path:
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    ch = str(chapter["number"]).zfill(4)
    filename = f"ch{ch}-system-breaker.md"
    path = CHAPTERS_DIR / filename

    full_content = f"""# Chapter {chapter['number']}

{chapter['content']}

---

_[System Breaker]({SITE_URL}/fiction/) — Chapter {chapter['number']}. Read all chapters [here]({SITE_URL}/fiction/)._
"""
    path.write_text(full_content)
    print(f"✅ Saved: {filename} ({chapter['word_count']} words)")

    # Update state
    state["chapters_published"] = chapter["number"]
    state["last_chapter_summary"] = chapter["summary"]
    save_state(state)
    print(f"   State updated: {chapter['number']} chapters published")

    return path


# ── INDEX PAGE ────────────────────────────────────────────
def update_fiction_index():
    """Regenerate the fiction index page listing all chapters."""
    chapters = sorted(CHAPTERS_DIR.glob("*.md"))
    if not chapters:
        return

    rows = []
    for c in chapters:
        num = int(c.stem.split("-")[0].lstrip("ch"))
        rows.append(f"| {num} | [Chapter {num}]({SITE_URL}/_chapters/{c.name.replace('.md', '.html')}) |")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>System Breaker — LitRPG Web Serial</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 700px; margin: 40px auto; padding: 20px; line-height: 1.7;
         color: #e0e0e0; background: #1a1a2e; }}
  h1 {{ color: #00d4ff; font-size: 2em; }}
  h2 {{ color: #7b61ff; }}
  a {{ color: #00d4ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
  th, td {{ padding: 10px 15px; text-align: left; border-bottom: 1px solid #333; }}
  th {{ color: #7b61ff; }}
  .tagline {{ font-size: 1.1em; color: #aaa; margin-bottom: 30px; }}
  .system-msg {{ background: #16213e; border-left: 3px solid #00d4ff; padding: 10px 15px; margin: 20px 0; }}
</style>
</head>
<body>
<h1>⚔️ System Breaker</h1>
<p class="tagline">He didn't get a system. He found its source code.</p>
<div class="system-msg">&gt; N.E.X.U.S: {len(chapters)} chapters loaded. Story integrity: STABLE. Enjoy your reading, meatbag.</div>

<h2>📖 Chapters</h2>
<table>
<tr><th>#</th><th>Title</th></tr>
{chr(10).join(rows)}
</table>

<p style="margin-top:40px;color:#666;font-size:0.9em;">
A LitRPG web serial by L.C. — auto-generated by <a href="https://github.com/lena2099/tech-tools-hub">Athena</a>.
</p>
</body>
</html>"""

    (Path("fiction") / "index.html").parent.mkdir(parents=True, exist_ok=True)
    (Path("fiction") / "index.html").write_text(html)
    print(f"📚 Fiction index updated: {len(chapters)} chapters")


# ── MAIN ─────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  🖊️  System Breaker — LitRPG Agent")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    state = load_state()
    print(f"\n📖 Chapter {state['chapters_published'] + 1} of {state['title']}")
    print(f"   Last: {state['last_chapter_summary'][:80]}...")

    chapter = generate_chapter(state)
    path = save_chapter(chapter, state)
    update_fiction_index()

    summary_preview = chapter['summary'][:100]
    print(f"\n✨ Chapter {chapter['number']} done. {chapter['word_count']} words.")
    print(f"   Summary: {summary_preview}...")

    # If there are 8+ chapters and DRY_RUN is off, print a Patreon note
    if state['chapters_published'] >= 8 and not DRY_RUN:
        print("\n💡 8+ chapters. Consider promoting Patreon: readers pay $3/mo for 3 chapters ahead.")

if __name__ == "__main__":
    main()
