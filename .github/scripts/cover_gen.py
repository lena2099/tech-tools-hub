#!/usr/bin/env python3
"""
Cover Generator — Unified Lena brand visuals for every article.
Creates: assets/covers/{slug}.png

Brand identity:
  - Color: #FF6B35 (warm orange — Lena's signature)
  - Font: system default bold for titles
  - Layout: product emoji top-left, title centered, "Lena的数码买手记" watermark bottom-right
  - Size: 1200×630px (Open Graph optimal)
"""
import os, sys
from pathlib import Path
from datetime import datetime, timezone

OUT_DIR = Path("assets/covers")
BRAND_COLOR = (255, 107, 53)      # #FF6B35
DARK_BG = (25, 25, 35)            # #191923
WHITE = (255, 255, 255)
LIGHT_GRAY = (180, 180, 190)
DIMENSIONS = (1200, 630)

# Category → emoji map
CATEGORY_EMOJI = {
    "noise-cancelling-headphones": "🎧",
    "budget-smartphones": "📱",
    "laptops-computers": "💻",
    "home-office-gear": "🪑",
    "gaming-gear": "🎮",
    "ereaders-tablets": "📖",
    "wearables-fitness": "⌚",
    "portable-audio": "🔊",
    "home-audio": "🔉",
    "smart-home-devices": "🏠",
    "smart-home-security": "🔒",
    "smart-kitchen": "🍳",
    "kitchen-appliances": "🍽️",
    "smart-pet-gear": "🐱",
    "charging-accessories": "🔌",
    "car-tech": "🚗",
    "photography-video": "📷",
    "drones": "🛸",
    "home-cleaning": "🧹",
    "networking": "🌐",
    "outdoor-tech": "🏕️",
    "health-wellness": "💪",
    "monitors-displays": "🖥️",
}

def create_cover(title: str, category: str, slug: str) -> str:
    """Generate a branded cover image. Returns file path."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("   ⚠️  Pillow not installed — skipping cover generation")
        return ""

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUT_DIR / f"{slug}.png"

    # Create canvas
    img = Image.new("RGB", DIMENSIONS, DARK_BG)
    draw = ImageDraw.Draw(img)

    # Try to load a nice font
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 52)
        subtitle_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except:
            title_font = ImageFont.load_default()
            subtitle_font = title_font
            small_font = title_font

    # Emoji / category label
    emoji = CATEGORY_EMOJI.get(category, "⚡")
    draw.text((50, 40), emoji, fill=BRAND_COLOR, font=title_font)

    # Accent bar
    draw.rectangle([50, 120, 200, 126], fill=BRAND_COLOR)

    # Title (wrapped)
    max_width = 1000
    words = title.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = current_line + " " + word if current_line else word
        try:
            bbox = draw.textbbox((0, 0), test_line, font=title_font)
            w = bbox[2] - bbox[0]
        except:
            w = len(test_line) * 25
        if w < max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    y = 180
    for line in lines[:4]:
        draw.text((50, y), line, fill=WHITE, font=title_font)
        y += 70

    # Subtitle
    draw.text((50, y + 30), "Honest review. Real opinions. No sponsors.", fill=LIGHT_GRAY, font=subtitle_font)

    # Watermark
    watermark = "Lena的数码买手记  ·  tech-tools-hub.netlify.app"
    bbox = draw.textbbox((0, 0), watermark, font=small_font)
    tw = bbox[2] - bbox[0]
    draw.text((DIMENSIONS[0] - tw - 40, DIMENSIONS[1] - 40), watermark, fill=LIGHT_GRAY, font=small_font)

    img.save(output_path, "PNG")
    print(f"   🎨 Cover: {output_path} ({DIMENSIONS[0]}×{DIMENSIONS[1]})")
    return str(output_path)

def main():
    posts_dir = Path("_posts")
    posts = sorted(posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not posts:
        print("No posts found")
        return

    latest = posts[0]
    content = latest.read_text(encoding="utf-8")
    
    # Extract frontmatter
    title = ""
    category = ""
    for line in content.split("\n"):
        if line.startswith("title:"):
            title = line.split(":", 1)[1].strip().strip('"')
        if line.startswith("categories:"):
            category = line.split(":", 1)[1].strip()
        if title and category:
            break

    if not title:
        print("No title found in frontmatter")
        return

    slug = latest.stem
    path = create_cover(title, category, slug)
    if path:
        print(f"✅ Cover generated: {path}")

if __name__ == "__main__":
    main()
