#!/usr/bin/env python3
"""
Athena v2 — Buyer-decision article agent for Amazon Associates.
Focus: comparison / best-of / vs-style reviews with high purchase intent.
No database, no scheduler. One script, two platforms.
"""
import hashlib, json, os, random, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY   = os.environ["DEEPSEEK_API_KEY"]
DEVTO_KEY = os.environ.get("DEVTO_API_KEY", "")
INDEXNOW_KEY = "0624a5ea55dc48afaefbe5ce8393c490"
SITE_URL = "https://tech-tools-hub.netlify.app"
DRY_RUN   = os.environ.get("DRY_RUN", "") == "1"
OUT_DIR   = Path("_posts")

# ── CONFIG: BUYER-INTENT TOPICS ───────────────────────────
# Each topic maps to a product category. Scope: tech + tech-adjacent only.
# See TOPIC SCOPE in the prompt for full include/exclude rules.
TOPICS = [
    # ── 1. 核心消费电子 ──
    {
        "slug": "noise-cancelling-headphones",
        "category": "Noise-Cancelling Headphones",
        "angles": [
            "Best Noise-Cancelling Headphones Under $100",
            "Best Premium ANC Headphones Compared",
            "Best Budget Wireless Earbuds with ANC",
            "Best Headphones for Remote Work & Zoom Calls",
            "Over-Ear vs In-Ear Noise Cancelling: Which to Buy",
        ],
    },
    {
        "slug": "budget-smartphones",
        "category": "Budget Smartphones",
        "angles": [
            "Best Smartphones Under $500",
            "Best Camera Phones Under $400",
            "Best Budget Android Phones for 2026",
            "Refurbished vs New: Best Phone Deals",
            "Best Phones for Gaming Under $300",
        ],
    },
    {
        "slug": "laptops-computers",
        "category": "Laptops & Computers",
        "angles": [
            "Best Laptops Under $800 for Work & Study",
            "MacBook Air vs Windows Ultrabook: Which to Buy",
            "Best Mini PCs for Home Office",
            "Best Budget Chromebooks for Students",
            "Best Used ThinkPads: Value King",
        ],
    },
    # ── 2. 桌面与外设 ──
    {
        "slug": "home-office-gear",
        "category": "Home Office Gear",
        "angles": [
            "Best Standing Desk & Ergonomic Chair Combos",
            "Best Budget Monitor for Programming & Design",
            "Best Webcam & Mic Setup for Video Calls",
            "Best Ergonomic Keyboard & Mouse for All-Day Use",
            "Best Desk Lamps & Lighting for Eye Comfort",
        ],
    },
    {
        "slug": "gaming-gear",
        "category": "Gaming Gear",
        "angles": [
            "Best Gaming Mouse Under $80",
            "Best Mechanical Keyboard for Gaming vs Typing",
            "Best Budget Gaming Headset with Good Mic",
            "Best Controller for PC Gaming",
            "Best Gaming Monitor: 144Hz vs 240Hz Worth It?",
        ],
    },
    # ── 3. 平板与阅读器 ──
    {
        "slug": "ereaders-tablets",
        "category": "eReaders & Tablets",
        "angles": [
            "Kindle vs Kobo vs reMarkable: Which eReader",
            "Best Budget Tablet for Reading & Note-Taking",
            "Best Tablet for Kids: Parent's Guide",
            "Best iPad Alternatives Under $300",
            "Best Drawing Tablet for Beginners",
        ],
    },
    # ── 4. 可穿戴与健身 ──
    {
        "slug": "wearables-fitness",
        "category": "Wearables & Fitness Tech",
        "angles": [
            "Best Fitness Tracker Under $100",
            "Best Smartwatch for iPhone vs Android Users",
            "Best Sleep Trackers & Rings Compared",
            "Best Running Headphones & Earbuds",
            "Best Smart Scale & Health Monitors",
        ],
    },
    # ── 5. 音频 ──
    {
        "slug": "portable-audio",
        "category": "Portable Audio",
        "angles": [
            "Best Bluetooth Speakers Under $80",
            "Best Portable Speaker for Beach & Outdoors",
            "JBL vs Bose vs Sony: Best Portable Sound",
            "Best Mini Speaker for Desk & Travel",
            "Best Party Speaker with Bass",
        ],
    },
    {
        "slug": "home-audio",
        "category": "Home Audio & HiFi",
        "angles": [
            "Best Soundbar Under $300 for TV",
            "Best Budget Bookshelf Speakers",
            "Best DAC & Amp Combo for Headphones",
            "Best Turntable for Beginners",
            "Best Desktop Speakers for Music & Gaming",
        ],
    },
    # ── 6. 智能家居 ──
    {
        "slug": "smart-home-devices",
        "category": "Smart Home Devices",
        "angles": [
            "Best Smart Home Starter Kit Under $200",
            "Best Video Doorbell & Security Cameras",
            "Best Smart Plugs & Lights for Beginners",
            "Best Smart Speakers: Echo vs Nest vs HomePod",
            "Best Robot Vacuums Under $400",
        ],
    },
    {
        "slug": "smart-home-security",
        "category": "Smart Home Security",
        "angles": [
            "Best DIY Home Security System No Subscription",
            "Best Smart Lock for Apartments",
            "Best Video Doorbell: Wired vs Battery",
            "Best Outdoor Security Camera Wireless",
            "Best Smart Smoke & CO Detector",
        ],
    },
    # ── 7. 智能厨房家电 ──
    {
        "slug": "smart-kitchen",
        "category": "Smart Kitchen Appliances",
        "angles": [
            "Best Air Fryer for Small Kitchens",
            "Best Instant Pot vs Ninja Multi-Cooker",
            "Best Smart Coffee Maker with App Control",
            "Best Sous Vide Machine for Home Cooks",
            "Best Smart Kitchen Scale & Thermometer",
        ],
    },
    {
        "slug": "kitchen-appliances",
        "category": "Kitchen Appliances",
        "angles": [
            "Best Countertop Ice Maker for Summer",
            "Best Rice Cooker: Zojirushi vs Cuckoo vs Instant",
            "Best Blender for Smoothies: Vitamix vs Ninja vs NutriBullet",
            "Best Electric Kettle with Temperature Control",
            "Best Toaster Oven vs Air Fryer: Do You Need Both?",
        ],
    },
    # ── 8. 智能宠物 ──
    {
        "slug": "smart-pet-gear",
        "category": "Smart Pet Gear",
        "angles": [
            "Best Automatic Pet Feeder for Cats & Dogs",
            "Best Smart Pet Water Fountain",
            "Best Self-Cleaning Litter Box Worth It?",
            "Best GPS Pet Tracker for Dogs",
            "Best Pet Camera with Treat Dispenser",
        ],
    },
    # ── 9. 充电与电源 ──
    {
        "slug": "charging-accessories",
        "category": "Charging & Power Accessories",
        "angles": [
            "Best USB-C Charging Station for Multi-Device",
            "Best Portable Power Bank for Travel",
            "Best GaN Chargers: Anker vs Ugreen vs Satechi",
            "Best MagSafe Accessories for iPhone",
            "Best Portable Power Station for Camping & Outages",
        ],
    },
    # ── 10. 汽车科技 ──
    {
        "slug": "car-tech",
        "category": "Car Tech & Accessories",
        "angles": [
            "Best Dash Cam Front & Rear Under $200",
            "Best Wireless CarPlay/Android Auto Adapter",
            "Best Tire Inflator Portable for Car",
            "Best Jump Starter Power Bank",
            "Best OBD2 Scanner for DIY Diagnostics",
        ],
    },
    # ── 11. 摄影与影像 ──
    {
        "slug": "photography-video",
        "category": "Photography & Video Gear",
        "angles": [
            "Best Budget Mirrorless Camera for Beginners",
            "Best Action Camera: GoPro vs DJI vs Insta360",
            "Best Tripod for Travel Photography",
            "Best Webcam vs DSLR as Webcam: Which to Use",
            "Best Gimbal for iPhone & Android Video",
        ],
    },
    {
        "slug": "drones",
        "category": "Drones & Aerial Photography",
        "angles": [
            "Best Beginner Drone Under $300",
            "DJI Mini vs Air: Which Drone for You?",
            "Best FPV Drone Kit for Beginners",
            "Best Drone for Real Estate Photography",
            "Best Budget Drone with 4K Camera",
        ],
    },
    # ── 12. 家庭清洁家电 ──
    {
        "slug": "home-cleaning",
        "category": "Home Cleaning Appliances",
        "angles": [
            "Best Robot Vacuum & Mop Combo",
            "Best Cordless Stick Vacuum: Dyson vs Shark vs Tineco",
            "Best Carpet Cleaner for Pet Owners",
            "Best Window Cleaning Robot Worth It?",
            "Best Air Purifier for Allergies & Pets",
        ],
    },
    # ── 13. 网络与存储 ──
    {
        "slug": "networking",
        "category": "Networking & Wi-Fi",
        "angles": [
            "Best Mesh Wi-Fi System for Large Homes",
            "Best Wi-Fi 7 Router Worth the Upgrade?",
            "Best Budget NAS for Home Media Server",
            "Best VPN Router for Privacy",
            "Best Wi-Fi Extender vs Mesh: Which to Buy",
        ],
    },
    # ── 14. 户外与旅行科技 ──
    {
        "slug": "outdoor-tech",
        "category": "Outdoor & Travel Tech",
        "angles": [
            "Best Portable Solar Panel for Camping",
            "Best Camping Lantern Rechargeable",
            "Best Bike Computer & GPS",
            "Best Handheld GPS for Hiking",
            "Best Portable Bluetooth Speaker Waterproof",
        ],
    },
    # ── 15. 健康与个人护理电器 ──
    {
        "slug": "health-wellness",
        "category": "Health & Wellness Tech",
        "angles": [
            "Best Electric Toothbrush: Oral-B vs Sonicare vs Quip",
            "Best Water Flosser for Home Use",
            "Best Massage Gun for Recovery",
            "Best Posture Corrector Wearable",
            "Best Light Therapy Lamp for SAD",
        ],
    },
    # ── 16. 显示器与屏幕 ──
    {
        "slug": "monitors-displays",
        "category": "Monitors & Displays",
        "angles": [
            "Best 4K Monitor for Work Under $500",
            "Best Ultrawide Monitor for Productivity",
            "Best Portable Monitor for Laptop",
            "Best Monitor for MacBook: USB-C Worth It?",
            "Best Budget Gaming Monitor 1440p",
        ],
    },
]

# Amazon affiliate tag
AMZN_TAG = "technolo0b423-20"

# ── PRODUCT CATALOG (verified ASINs) ──────────────────────
def load_products():
    """Load product whitelist from products.json."""
    p = Path("products.json")
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {}

def pick_products(category_slug: str, count: int = 4) -> list:
    """Pick products for a category from the whitelist."""
    catalog = load_products()
    products = catalog.get(category_slug, [])
    if not products:
        return []
    with_asin = [p for p in products if p.get("asin")]
    without_asin = [p for p in products if not p.get("asin")]
    selected = with_asin[:count]
    if len(selected) < count:
        selected += without_asin[:count - len(selected)]
    return selected

def format_product_links(products: list) -> str:
    """Format product list for prompt injection."""
    lines = []
    for p in products:
        asin = p.get("asin")
        name = p["name"]
        price = p.get("price", "?")
        note = p.get("note", "")
        if asin:
            url = f"https://www.amazon.com/dp/{asin}?tag=technolo0b423-20"
            lines.append(f"- {name}: {url} (${price}, {note})")
        else:
            # Product without ASIN — skip, don't generate search link
            continue
    return "\n".join(lines)

# Subscription bounties (PA API product links, NOT search redirects)
AMZN_SUBS = [
    ("Kindle Unlimited", "https://www.amazon.com/kindle-dbs/hz/subscribe/ku?tag=technolo0b423-20",
     "Free 30-day trial, unlimited reading"),
    ("Audible Premium Plus", "https://www.audible.com/ep/affiliate?tag=technolo0b423-20",
     "Free 30-day trial, 1 free audiobook"),
    ("Amazon Prime", "https://www.amazon.com/amazonprime?tag=technolo0b423-20",
     "Free 30-day trial, free shipping + Prime Video"),
    ("Amazon Music Unlimited", "https://www.amazon.com/music/unlimited?tag=technolo0b423-20",
     "Free 30-day trial, 100M songs"),
]


# ── LLM CALL ──────────────────────────────────────────────
def call_deepseek(messages, max_tokens=2048, temperature=0.7):
    req = Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps({
            "model": "deepseek-chat",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    resp = json.loads(urlopen(req, timeout=120).read())
    return resp["choices"][0]["message"]["content"]



# ── COMMISSION-WEIGHTED TOPIC SELECTION ──────────────────
# Amazon Associates 2026 commission rates by category:
#   10%: furniture (home-office-gear)
#    8%: home improvement (home-cleaning)
#    5%: pets, kitchen, auto, outdoor
#    3%: electronics, cameras, drones, networking, etc.
COMMISSION_WEIGHTS = {
    "home-office-gear":       10,   # chairs, desks, office furniture
    "home-cleaning":           8,   # robot vacuums, cordless vacuums, air purifiers
    "smart-pet-gear":          5,   # feeders, fountains, litter boxes, GPS trackers
    "smart-kitchen":           5,   # air fryers, coffee makers, sous vide
    "kitchen-appliances":      5,   # ice makers, rice cookers, blenders, kettles
    "car-tech":                5,   # dashcams, CarPlay, tire inflators, jump starters
    "outdoor-tech":            5,   # solar panels, camping lanterns, bike computers
    "health-wellness":         5,   # electric toothbrushes, water flossers, massage guns
    "smart-home-devices":      4,   # robot vacuums overflow, smart lights
    "smart-home-security":     4,   # doorbells, cameras, smart locks
    "portable-audio":          3,   # BT speakers
    "home-audio":              3,   # soundbars, bookshelf speakers, DACs
    "noise-cancelling-headphones": 3,
    "budget-smartphones":      3,
    "laptops-computers":       3,
    "gaming-gear":             3,
    "ereaders-tablets":        3,
    "wearables-fitness":       3,
    "charging-accessories":    3,
    "photography-video":       3,
    "drones":                  3,
    "networking":              3,
    "monitors-displays":       3,
}

def weighted_topic_pick(available: list) -> dict:
    """Pick from available topics weighted by commission rate."""
    if not available:
        # Should not happen but fallback
        return TOPICS[0]
    # Sum weights, every slug gets at least weight=1 (so 3% categories still show up)
    import random
    weights = [COMMISSION_WEIGHTS.get(t["slug"], 3) for t in available]
    total = sum(weights)
    # Normalized weighted random
    r = random.uniform(0, total)
    cumulative = 0
    for topic, w in zip(available, weights):
        cumulative += w
        if r <= cumulative:
            return topic
    return available[-1]  # fallback
# ── TOPIC ROTATION ───────────────────────────────────────
def pick_topic_and_angle():
    """Pick next topic and a fresh angle, avoiding recent repeats."""
    now = datetime.now(timezone.utc)
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True) if OUT_DIR.exists() else []

    # Get last-used slugs
    recent_slugs = []
    for p in posts[:5]:
        content = p.read_text()
        for line in content.split("\n"):
            if line.startswith("categories:"):
                recent_slugs.append(line.split(":", 1)[1].strip())
                break

    # Pick least-recently-used topic, weighted by commission rate
    available = [t for t in TOPICS if t["slug"] not in recent_slugs[:2]]
    if not available:
        available = TOPICS
    topic = weighted_topic_pick(available)

    # Pick angle not used in last 2 articles for this slug
    used_angles = set()
    for p in posts:
        content = p.read_text()
        for line in content.split("\n"):
            if line.startswith("title:"):
                used_angles.add(line.split(":", 1)[1].strip().strip('"'))
                break

    fresh_angles = [a for a in topic["angles"] if a not in used_angles]
    if not fresh_angles:
        fresh_angles = topic["angles"]
    angle = fresh_angles[random.randint(0, len(fresh_angles) - 1)]

    return topic, angle


# ── ARTICLE GENERATION ────────────────────────────────────
def generate_article(topic: dict, angle: str):
    current_date = datetime.now(timezone.utc)
    # Pick verified products from catalog
    products = pick_products(topic['slug'])
    product_block = format_product_links(products)
    if not product_block:
        product_block = "(NO verified products for this category. You MUST find real ASIN links on Amazon and use them. Search links (/s?k=) are PROHIBITED.)"
    month_year = current_date.strftime("%B %Y")
    this_year = current_date.strftime("%Y")

    subs_text = "\n".join(
        f"  - {name}: {url} ({desc})" for name, url, desc in AMZN_SUBS
    )

    prompt = f"""Write a BUYER-DECISION blog article. The reader is shopping — help them choose.

VOICE RULES — THIS IS THE MOST IMPORTANT PART:

You are LENA, a tech reviewer in Shenzhen. Your persona:
- You read Reddit and YouTube obsessively for real user opinions, not sponsored reviews
- You're in digital enthusiast circles — you actually use the products you write about
- You compare overseas (Amazon) vs Chinese (JD/Taobao) pricing: "is it worth ¥XXX more?"
- Honesty is your brand: a ¥249 product at 90% quality beats a ¥2299 flagship every time
- Voice: texting a friend who asked "what should I buy?" — casual, opinionated, first-person
- Signatures: "先说结论", "Reddit上有个老外说...", "省下这笔钱吧"

HUMAN-WRITING RULES (from human-writing skill):
1. OPEN WITH PUNCHLINE. First sentence = strongest opinion. No buildup, no context-setting.
   ❌ "In this article, we will explore the best standing desks..."
   ✅ "I returned two desks before finding one that didn't wobble at standing height."
2. BE SPECIFIC. Every claim needs a number, a quote, or a comparison.
   ❌ "Great battery life" → ✅ "Lasted 7.5 hours on a Teams call"
   ❌ "Many users complain" → ✅ "Reddit has 47 threads about the hinge snapping"
3. ADMIT FLAWS. Every recommended product gets at least one honest complaint.
   "The ANC is excellent but the ear cups get hot after 45 minutes."
4. NO CORPORATE SPEAK. No "leveraging", "best-in-class", "seamlessly", "unlock your potential"
5. NO HEDGING. "Might help" → "Helps". "Could be useful" → "Use this when..."
6. ACTIVE VOICE, PRESENT TENSE. "I tested this" not "This was tested."
7. SHOW DON'T TELL. "Reddit user /u/throwaway: 'the hinge broke in month 3'" beats "Users report issues."
8. END WITH ACTION. "Buy the X if you care about Y. Skip it if Z matters more." No "In conclusion..."
9. SHORT PARAGRAPHS. 40-80 words max. Contractions (don't, can't, I've). Grade 8-10 readability.
10. NEVER LIE. Don't say "I tested" if you haven't. Say "most reviewers report" or "based on specs."

BANNED PHRASES — any of these = article rejected:
"In today's digital age", "In the fast-paced world of", "Whether you're a seasoned professional",
"We're excited/thrilled/delighted", "Game-changing/Revolutionary/Cutting-edge",
"Unlock your potential", "Take your X to the next level", "Let's dive in",
"Without further ado", "At the end of the day", "Leveraging", "Seamlessly",
"Imagine you're", "Picture this", "In conclusion", "To sum up"

- Write like a real person who actually owns and uses tech products. First-person, casual, opinionated.
- NEVER use these AI phrases: "You're looking for X but the market is confusing/overwhelming", "After hours of testing", "the truth is", "game-changer", "revolutionary", "whether you're on a budget or want premium", "let's dive deep", "without further ado".
- DON'T sound like a marketing copywriter. Sound like someone texting a friend about what to buy.
- Include at least one personal experience detail: a specific thing that annoyed you, a feature you didn't expect to use but now love, something you returned.
- Every product should have at least one honest CON: not just "no backlight", but real stuff — "the software requires an account just to remap keys", "the ear tips don't fit small ears".
- Use contractions (don't, can't, I've, you're). Short paragraphs. 40-80 words max per paragraph.
- READABILITY: grade 8-10. Short sentences. No corporate buzzwords.
- NEVER lie. Don't say "I tested" if you haven't. Say "most reviewers report" or "based on specs".

CONTENT RULES:
- Today is {current_date.strftime('%B %d, %Y')}. ONLY real, currently-available products. No 2024 models unless they're still sold new.
- This is a shopping guide, not a tutorial.

REVIEW-SPECIFIC WRITING RULES — the patterns that make a review worth reading:

1. COMPARATIVE STRUCTURE — don't review in isolation. Every product sits in a landscape.
   ❌ "The XM5 has great ANC at 30dB reduction." (spec recitation)
   ✅ "The XM5 blocks out 30dB. The QC Ultra blocks 28dB but feels quieter because of better ear seal. For $20 more, the Sony wins."

2. "WHO SHOULD BUY / WHO SHOULD SKIP" — the highest-converting paragraph in any review.
   End EVERY section or article with a clear verdict per product:
   ✅ "Buy the XM5 if you: fly twice a month, want top ANC, have $328."
   ✅ "Skip the XM5 if: you only use headphones at home. Get the $79 Space A40 instead — 80% of the ANC for 24% of the price."

3. REDDIT VOICE — your core advantage. Weave in real community sentiment naturally.
   Weak:  "Many users report hinge durability issues."
   Strong: "Reddit上有个老外发帖：'用了三个月，转轴自己裂了。客服说这是外观损坏不保修。' 下面47条回复全是同样的问题。Sony 还没公开回应。"
   Pattern: specific Reddit anecdote + scale (47 replies) + company's response (or silence).

4. PRICE ANCHORING — make the price comparison visceral.
   Weak:  "At $249, it's a good value."
   Strong: "¥249 的漫步者 vs ¥2299 的 Sony。差了10倍价格，差距有没有10倍？我听完：没有。Sony 好，但不是10倍好。"

5. SUBJECTIVE → OBJECTIVE — turn feelings into evidence readers can trust.
   Weak:  "The sound quality is amazing." (empty adjective)
   Weak:  "The highs are crystal clear." (audio reviewer cliché)
   Strong: "我在一首歌里听到了之前从没注意过的贝斯线。不是'音质好'，是真的听到了新的东西。"
   Strong: "Wore them for a 6-hour flight. My ears didn't sweat. My old pair made my ears wet by hour 3."
   Rule: describe what you NOTICED, not what you JUDGED. Let the reader judge.

6. REVIEW-SPECIFIC BANNED WORDS — these destroy credibility instantly:
   - "This thing is a beast" / "absolute unit"
   - "Punches above its weight" (every reviewer says this)
   - "Best bang for your buck" (lazy, no data)
   - "Build quality is premium" (what does that even mean?)
   - "Blows the competition out of the water" (hyperbole)
   - "An absolute must-have" (no product is a must-have for everyone)
   - "Kills it in every category" (nothing kills it in EVERY category)
   - "Buttery smooth" (unless it's literally butter)
   - "Crystal clear" (audio cliché — describe what you actually heard)
   - "Tank-like build" (unless you dropped it from a tank)

7. LENA'S SIGNATURE MOVES — these make you recognizable:
   - Open with a personal failure: "I returned two desks before finding this one."
   - The Reddit reality check: "Reddit上有个老外说..."
   - The price gut-punch: "差了10倍价格，差距有没有10倍？"
   - The honest letdown: "It's great at X. But I can't recommend it if you care about Y."
   - The save-your-money closer: "省下这笔钱吧。买¥249那个，剩下的¥2000去吃顿好的。"

- Verified products (use these exact ASIN links. NO search links /s?k=):
{product_block}
- WRITING STYLE (ABSOLUTE):
  10. Open with a strong opinion, not a description. "I returned three pairs before finding these."
  11. Use specific numbers, not vague adjectives. "7.5 hours on a Teams call" not "great battery."
  12. Admit flaws: every product you recommend MUST have at least one honest complaint.
  13. No banned phrases. No corporate speak. No "In today's digital age."
  14. End with action: "Buy the X if you care about Y. Skip it if Z matters more."
  15. Read aloud test: if it wouldn't come out of a real person's mouth, rewrite.
- LINK FORMAT RULES (ABSOLUTE — violation = article rejected):
  1. EVERY product you discuss MUST have an Amazon link. 5 products = 5 links. Non-negotiable.
  2. Use ASIN product links ONLY: `https://www.amazon.com/dp/ASIN?tag=technolo0b423-20`
  3. SEARCH LINKS (/s?k=) are STRICTLY PROHIBITED. Never use them. Ever.
  4. For products NOT in the verified list: find the real ASIN on Amazon yourself.
     The ASIN is the 10-char alphanumeric code in the URL after /dp/
     Example: amazon.com/dp/B0BT35C89P → ASIN = B0BT35C89P
  5. INLINE links: put links directly on product names in the body.
     Good: "The [Sony WH-1000XM5](https://www.amazon.com/dp/B0BZR6H4R5?tag=technolo0b423-20) is $328"
     Bad: "[Check price on Amazon](link)" at the end of the article
  6. NO "Check price on Amazon" blocks. NO link dumps at the bottom.
- No comparison table with fake star ratings. Describe differences in plain sentences.
- No numbered feature lists. Tell me what matters.
- Skip the "Quick Picks" box. Skip the "Verdict" with "Best Overall/Budget/Premium" labels. Just tell the reader what to buy and why.
- FAQ section: 2 questions max. Keep answers 2-3 sentences.
- Mention subscriptions ONLY if genuinely relevant. Don't cram Kindle Unlimited into a keyboard review.
- Affiliate disclosure at the very end: "*As an Amazon Associate, I earn from qualifying purchases.*"

TOPIC SCOPE — what you CAN and CANNOT write about:
- ✅ IN SCOPE: Anything tech, electronics, gadgets, or tech-adjacent gear. Examples:
  • Core tech: headphones, phones, laptops, tablets, monitors, keyboards, mice, webcams
  • Smart home: robot vacuums, smart lights, smart plugs, doorbells, smart locks, thermostats
  • Smart pet gear: automatic pet feeders, smart water fountains, GPS pet trackers, self-cleaning litter boxes, pet cameras
  • Smart kitchen: air fryers, Instant Pots, smart coffee makers, sous vide machines, smart scales
  • Health & fitness: smartwatches, fitness trackers, sleep trackers, smart rings, smart scales, massage guns, posture correctors
  • Office & ergonomics: standing desks, ergonomic chairs, monitor arms, standing desk mats, footrests
  • Audio: speakers, soundbars, earbuds, DACs, microphones, audio interfaces
  • Gaming: controllers, gaming mice, gaming keyboards, headsets, capture cards, racing wheels
  • Charging & power: power banks, GaN chargers, charging stations, surge protectors, UPS units
  • Photography: cameras, lenses, tripods, gimbals, action cameras, drones
  • E-readers & tablets: Kindle, Kobo, reMarkable, iPad, drawing tablets
  • Car tech: dashcams, OBD2 scanners, tire inflators, jump starters, phone mounts, CarPlay adapters
  • Networking: mesh Wi-Fi, routers, range extenders, NAS, mini PCs
  • Outdoor tech: portable solar panels, power stations, camping lanterns, bike computers
  • Any product that plugs in, charges, connects via Bluetooth/Wi-Fi, or has a battery: ✅
- 🚫 OUT OF SCOPE — DO NOT write about these:
  • Fashion: clothing, shoes, bags, jewelry, watches (non-smart)
  • Beauty: makeup, skincare, perfume
  • Food & drink: supplements, snacks, coffee beans
  • Home decor (non-tech): curtains, rugs, picture frames, artificial plants
  • Sports equipment (non-smart): yoga mats, dumbbells, resistance bands
  • Books, music, movies (content — Kindle/Kindle Unlimited is fine, but not specific book recommendations)
  • Basically: if it doesn't have a battery, a plug, a Bluetooth chip, or a CPU, skip it.
- When in doubt, err on the side of IN SCOPE. Better to write about a borderline product with Amazon links than to skip a revenue opportunity.
- If the topic suggestion system picks something out of scope, REPLACE it with a nearby tech-adjacent alternative.
  Example: "Best Running Shoes 2026" → replace with "Best Running Earbuds 2026"

ARTICLE INFO:
- Title: {angle} — keep it under 60 chars, include {this_year}
- Category: {topic['category']}
- Length: 600-900 words. Short is better than padded.

STRUCTURE (flexible — don't follow this rigidly):
1. Opening: personal anecdote or strong opinion. Not a generic "market is confusing" hook.
2. What actually matters: 2-3 things buyers overlook but should know.
3. Product recommendations: 3-4 products, 100-150 words each, with honest pros and cons.
4. Closing: one sentence telling the reader which one to buy and why.
5. FAQ: 2 questions.
6. Disclosure line.

OUTPUT: ONLY a JSON object:
{{"title": "...", "slug": "url-friendly-slug", "meta_description": "150-160 chars", "tags": ["tag1","tag2"], "content": "FULL # markdown article"}}"""

    text = call_deepseek([{"role": "user", "content": prompt}], max_tokens=3072, temperature=0.7)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            article = json.loads(match.group())
            article["word_count"] = len(article["content"].split())
            return article
        except json.JSONDecodeError:
            pass

    lines = text.strip().split("\n")
    title = lines[0].lstrip("# ").strip()[:65]
    return {"title": title, "slug": re.sub(r"[^a-z0-9]+", "-", title.lower())[:60],
            "meta_description": f"Best {topic['category']} for {this_year}. Expert comparison & buying guide.",
            "tags": ["review", "buying-guide", "tech"],
            "content": text, "word_count": len(text.split())}


# ── DEV.TO PUBLISH ───────────────────────────────────────
def publish_to_devto(article, topic: dict):
    if not DEVTO_KEY:
        return {"status": "skipped", "reason": "no api key"}
    payload = {"article": {
        "title": article["title"],
        "body_markdown": article["content"],
        "published": True,
        "tags": _pick_devto_tags(topic, article.get("tags", [])),
        "description": article.get("meta_description", ""),
        "canonical_url": f"{SITE_URL}/",
    }}
    try:
        req = Request("https://dev.to/api/articles",
                      data=json.dumps(payload).encode(),
                      headers={"api-key": DEVTO_KEY, "Content-Type": "application/json",
                               "User-Agent": "Mozilla/5.0 (compatible; Athena/2.0; +https://lena2099.github.io/tech-tools-hub)"},
                      method="POST")
        resp = json.loads(urlopen(req, timeout=30).read())
        return resp if "url" in resp else {"status": "failed", "error": str(resp)[:200]}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


def _pick_devto_tags(topic: dict, article_tags: list) -> list:
    boost_map = {
        "noise-cancelling-headphones": ["reviews", "headphones", "tech"],
        "budget-smartphones": ["reviews", "android", "tech"],
        "home-office-gear": ["productivity", "reviews", "tech"],
        "smart-home-devices": ["iot", "reviews", "tech"],
        "ereaders-tablets": ["reviews", "books", "tech"],
        "wearables-fitness": ["reviews", "fitness", "tech"],
        "portable-audio": ["reviews", "music", "tech"],
        "charging-accessories": ["reviews", "tech", "tutorial"],
    }
    clean = []
    for t in article_tags:
        tag = re.sub(r"[^a-z0-9]", "", t.strip().lower())[:25]
        if tag and tag not in clean:
            clean.append(tag)
    for b in boost_map.get(topic["slug"], ["reviews", "tech"]):
        if b not in clean:
            clean.append(b)
    return clean[:4]


# ── SAVE AS JEKYLL POST ──────────────────────────────────
def save_jekyll_post(article, topic: dict):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = article["slug"]
    filename = f"{date_str}-{slug}.md"
    path = OUT_DIR / filename
    if path.exists():
        print(f"⚠️  Already exists: {filename}")
        return None
    tags = "\n".join(f"  - {t}" for t in article.get("tags", [])[:5])
    frontmatter = f"""---
layout: post
title: "{article['title']}"
date: {datetime.now(timezone.utc).isoformat()}
categories: {topic['slug']}
tags:
{tags}
description: "{article.get('meta_description', '')}"
---
"""
    path.write_text(frontmatter + article["content"])
    print(f"✅ Jekyll post: {filename}")
    return path


# ── CROSS-LINKING ────────────────────────────────────────
def get_recent_posts(exclude_slug: str = "", count: int = 3) -> list[dict]:
    posts = sorted(OUT_DIR.glob("*.md"), reverse=True) if OUT_DIR.exists() else []
    result = []
    for p in posts:
        if len(result) >= count:
            break
        if exclude_slug and exclude_slug in p.stem:
            continue
        content = p.read_text()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].split("\n"):
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"')
                        parts2 = p.stem.split("-", 3)
                        if len(parts2) >= 4:
                            url = f"{SITE_URL}/{parts2[0]}/{parts2[1]}/{parts2[2]}/{parts2[3]}.html"
                            result.append({"title": title, "url": url})
                        break
    return result


def append_cross_links(content: str, current_slug: str) -> str:
    recent = get_recent_posts(exclude_slug=current_slug, count=3)
    if len(recent) < 2:
        return content
    links_md = "\n".join(f"- [{p['title']}]({p['url']})" for p in recent)
    return content + f"\n\n---\n\n### 📚 Related Buying Guides\n\n{links_md}"


# ── SEO FILES ─────────────────────────────────────────────
def generate_sitemap():
    posts = sorted(OUT_DIR.glob("*.md")) if OUT_DIR.exists() else []
    if not posts:
        return
    urls = [f"""  <url>
    <loc>{SITE_URL}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""]
    for p in posts:
        parts = p.stem.split("-", 3)
        if len(parts) >= 4:
            url = f"{SITE_URL}/{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}.html"
            urls.append(f"""  <url>
    <loc>{url}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")
    Path("sitemap.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
""")
    print(f"   sitemap.xml: {len(urls)} URLs")


def generate_robots():
    Path("robots.txt").write_text(f"""User-agent: *
Allow: /
Sitemap: {SITE_URL}/sitemap.xml
""")


def ping_search_engines(article: dict):
    sitemap_url = f"{SITE_URL}/sitemap.xml"
    article_url = article.get("canonical_url", "")
    indexnow_payload = json.dumps({
        "host": "lena2099.github.io", "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": [article_url, sitemap_url],
    }).encode()
    try:
        resp = urlopen(Request("https://api.indexnow.org/indexnow",
                               data=indexnow_payload,
                               headers={"Content-Type": "application/json"}), timeout=10)
        print(f"   IndexNow: HTTP {resp.getcode()}")
    except Exception as e:
        print(f"   IndexNow: {e}")
    try:
        urlopen(Request(f"https://www.google.com/ping?sitemap={sitemap_url}"), timeout=10)
        print("   Google: pinged")
    except Exception as e:
        print(f"   Google ping: {e}")


# ── MAIN ─────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  🦉 Athena v2 — Buyer-Decision Article Agent")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    topic, angle = pick_topic_and_angle()
    print(f"\n📝 Category: {topic['category']}")
    print(f"🎯 Angle: {angle}")

    print("✍️  Writing article...")
    article = generate_article(topic, angle)
    print(f"   Title: {article['title']}")
    print(f"   Words: {article['word_count']}")

    print("🔗 Cross-linking...")
    article["content"] = append_cross_links(article["content"], article.get("slug", ""))

    post_path = save_jekyll_post(article, topic)
    if post_path is None:
        print("\n⏭️  Already published — skipping.")
        return

    if not DRY_RUN:
        print("📤 Publishing to Dev.to...")
        result = publish_to_devto(article, topic)
        print(f"   Dev.to: {result}")
    else:
        print("🏜️  DRY_RUN — skipping Dev.to")

    if post_path:
        print("🔍 Updating SEO...")
        generate_sitemap()
        generate_robots()
        print("   Sitemap + robots.txt updated")

    if post_path and not DRY_RUN:
        ping_search_engines(article)

    print("\n✨ Done. Next run in ~4 hours.")


if __name__ == "__main__":
    main()
