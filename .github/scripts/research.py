#!/usr/bin/env python3
"""
Research Engine v1 — Demand-driven topic selection.
Runs BEFORE agent.py. Outputs research_findings.json.

What it does:
  1. Google Trends — scan 23 categories for rising search interest
  2. Seasonal awareness — boost categories based on time of year
  3. Amazon search intent — which products are actually being shopped
  4. Output: recommended topic + target keywords + buyer intent signals

No API keys needed. Uses pytrends (free, unofficial Google Trends client)
and public data sources.
"""
import json, random, re, os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

# ══════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════
CATEGORY_KEYWORDS = {
    "noise-cancelling-headphones": ["best noise cancelling headphones", "wireless earbuds ANC", "Sony XM5 review", "Bose QC Ultra vs Sony"],
    "budget-smartphones":      ["best budget phone", "phones under 500", "best android 2026", "refurbished phone deals"],
    "laptops-computers":       ["best laptop 2026", "budget chromebook", "MacBook Air M4", "mini PC for office"],
    "home-office-gear":        ["standing desk", "ergonomic chair", "office chair back pain", "best monitor for work", "desk setup ideas"],
    "gaming-gear":             ["best gaming mouse", "mechanical keyboard", "gaming headset", "best gaming monitor 1440p"],
    "ereaders-tablets":        ["best ereader 2026", "Kindle vs Kobo", "budget tablet note taking", "drawing tablet beginner"],
    "wearables-fitness":       ["best fitness tracker", "smartwatch 2026", "sleep tracker ring", "best running watch"],
    "portable-audio":          ["bluetooth speaker outdoor", "JBL Flip vs Bose", "portable speaker beach"],
    "home-audio":              ["best soundbar", "desktop speakers music", "turntable beginner", "DAC amp headphone"],
    "smart-home-devices":      ["smart home starter", "smart plug setup", "smart speaker", "best robot vacuum"],
    "smart-home-security":     ["video doorbell", "security camera wireless", "smart lock apartment", "DIY home security"],
    "smart-kitchen":           ["best air fryer", "instant pot recipes", "sous vide machine", "smart coffee maker"],
    "kitchen-appliances":      ["rice cooker best", "blender smoothie", "electric kettle temperature", "toaster oven air fryer"],
    "smart-pet-gear":          ["automatic pet feeder", "self cleaning litter box", "GPS dog tracker", "pet water fountain"],
    "charging-accessories":    ["USB C charger GaN", "portable power bank", "MagSafe charger iPhone", "portable power station camping"],
    "car-tech":                ["best dash cam", "wireless CarPlay adapter", "tire inflator portable", "jump starter car"],
    "photography-video":       ["best mirrorless camera", "GoPro vs DJI action camera", "phone gimbal stabilizer", "travel tripod"],
    "drones":                  ["beginner drone", "DJI Mini 4 review", "FPV drone kit", "drone 4K camera budget"],
    "home-cleaning":           ["robot vacuum mop", "cordless stick vacuum", "air purifier allergies", "carpet cleaner pet"],
    "networking":              ["mesh wifi system", "WiFi 7 router", "home NAS media server", "VPN router"],
    "outdoor-tech":            ["handheld GPS hiking", "portable solar panel", "camping lantern rechargeable", "bike computer GPS"],
    "health-wellness":         ["electric toothbrush best", "water flosser", "massage gun recovery", "light therapy lamp"],
    "monitors-displays":       ["best 4K monitor", "ultrawide monitor productivity", "portable monitor laptop", "gaming monitor 1440p 165Hz"],
}

# Seasonal boost — multiply search relevance by month
SEASONAL_BOOST = {
    1:  {"home-office-gear": 1.5, "health-wellness": 1.8, "charging-accessories": 1.3},   # New Year
    2:  {"smart-home-devices": 1.3, "home-audio": 1.2},   # Valentine's home nesting
    3:  {"outdoor-tech": 1.4, "car-tech": 1.3},            # Spring prep
    4:  {"home-cleaning": 1.5, "kitchen-appliances": 1.3}, # Spring cleaning
    5:  {"outdoor-tech": 1.8, "portable-audio": 1.6, "car-tech": 1.4},  # Summer kickoff
    6:  {"outdoor-tech": 2.0, "portable-audio": 2.0, "drones": 1.6},    # Peak summer
    7:  {"outdoor-tech": 1.8, "portable-audio": 1.8, "drones": 1.5},    # Summer
    8:  {"laptops-computers": 1.6, "budget-smartphones": 1.4, "gaming-gear": 1.5},  # Back to school
    9:  {"laptops-computers": 1.6, "budget-smartphones": 1.4, "home-office-gear": 1.3},  # School + office
    10: {"home-cleaning": 1.4, "smart-home-devices": 1.3, "health-wellness": 1.3},  # Fall prep
    11: {"noise-cancelling-headphones": 2.0, "budget-smartphones": 2.0, "laptops-computers": 2.0, "wearables-fitness": 1.8, "home-audio": 1.5, "monitors-displays": 1.5, "gaming-gear": 1.8, "drones": 1.4},  # Black Friday = electronics peak
    12: {"noise-cancelling-headphones": 1.8, "budget-smartphones": 1.8, "laptops-computers": 1.8, "wearables-fitness": 1.8, "home-audio": 1.4, "monitors-displays": 1.4, "gaming-gear": 1.8},  # Holiday
}

# ══════════════════════════════════════════════════════════
# 1. GOOGLE TRENDS SCANNER
# ══════════════════════════════════════════════════════════
def try_import_pytrends():
    """Import pytrends if available, otherwise return None."""
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='en-US', tz=360)
        return pytrends
    except ImportError:
        return None
    except Exception:
        return None

def scan_google_trends():
    """
    Scan rising search terms for all 23 categories.
    Returns {category_slug: [trending_keywords]} or {} if pytrends unavailable.
    """
    pytrends = try_import_pytrends()
    if not pytrends:
        print("   ⚠️  pytrends not available — using season + static keyword data")
        return {}

    trends = {}
    # Sample 6-8 high-value categories per run to avoid rate limiting
    sample_categories = random.sample(list(CATEGORY_KEYWORDS.keys()), min(8, len(CATEGORY_KEYWORDS)))
    
    for slug in sample_categories:
        kw = CATEGORY_KEYWORDS[slug][:2]  # Use first 2 keywords as probes
        try:
            pytrends.build_payload(kw, timeframe='today 3-m', geo='US')
            related = pytrends.related_queries()
            rising = {}
            for k in kw:
                if k in related and related[k] and 'rising' in related[k] and related[k]['rising'] is not None:
                    rising[k] = related[k]['rising']['query'].head(5).tolist()
            if rising:
                trends[slug] = rising
        except Exception:
            pass
    
    return trends

# ══════════════════════════════════════════════════════════
# 2. SEASONAL + DEMAND SIGNAL AGGREGATOR
# ══════════════════════════════════════════════════════════
def get_seasonal_score(slug: str, month: int) -> float:
    """Get seasonal demand multiplier for a category this month."""
    month_boost = SEASONAL_BOOST.get(month, {})
    return month_boost.get(slug, 1.0)

def get_category_demand_score(slug: str, month: int, trends: dict) -> dict:
    """
    Calculate composite demand score for a category.
    Returns {score, signals, recommended_angles}
    """
    seasonal = get_seasonal_score(slug, month)
    has_trending = slug in trends and bool(trends[slug])
    
    # Base demand: 3 (electronics) to 10 (furniture/cleaning) from commission weights
    commission_weights = {
        "home-office-gear": 10, "home-cleaning": 8, "smart-pet-gear": 5,
        "smart-kitchen": 5, "kitchen-appliances": 5, "car-tech": 5,
        "outdoor-tech": 5, "health-wellness": 5, "smart-home-devices": 4,
        "smart-home-security": 4,
    }
    base_demand = commission_weights.get(slug, 3)
    
    # Composite score: base × seasonal × trending bonus
    trending_bonus = 1.3 if has_trending else 1.0
    score = base_demand * seasonal * trending_bonus
    
    signals = []
    if seasonal > 1.3:
        signals.append(f"🔥 Seasonal peak (boost: {seasonal:.1f}x)")
    if has_trending:
        signals.append(f"📈 Google Trends rising queries detected")
    if base_demand >= 8:
        signals.append(f"💰 High commission ({base_demand}%)")
    
    # Generate 3 demand-driven angles from keywords
    kw_list = CATEGORY_KEYWORDS.get(slug, [slug])
    angles = [
        f"Best {kw_list[0].title()} in 2026",
        f"{kw_list[1].title()} — Buyer's Guide",
        f"{kw_list[0].title()} Under $XXX — Best Value Picks",
    ] if len(kw_list) >= 2 else [f"Best {slug.replace('-', ' ').title()} 2026"]
    
    return {
        "score": round(score, 1),
        "base_demand": base_demand,
        "seasonal_multiplier": round(seasonal, 2),
        "trending": has_trending,
        "signals": signals,
        "target_keywords": kw_list[:3],
        "suggested_angles": angles,
        "buyer_intent": "HIGH" if base_demand >= 5 else ("MEDIUM" if base_demand >= 3 else "LOW"),
    }

# ══════════════════════════════════════════════════════════
# 3. MAIN — Produce research_findings.json
# ══════════════════════════════════════════════════════════
def main():
    now = datetime.now(timezone.utc)
    month = now.month
    print(f"\n{'='*60}")
    print(f"🔬 Research Engine — {now.strftime('%B %Y')}")
    print(f"{'='*60}")
    
    # Scan trends
    print("\n📊 Google Trends scan...")
    trends = scan_google_trends()
    if trends:
        print(f"   ✅ Found trending data for {len(trends)} categories")
        for slug, data in list(trends.items())[:3]:
            print(f"      {slug}: {sum(len(v) for v in data.values())} rising queries")
    else:
        print("   Using seasonal + static keyword data")
    
    # Calculate demand scores for all categories
    print("\n📈 Demand scoring...")
    results = {}
    for slug in CATEGORY_KEYWORDS:
        results[slug] = get_category_demand_score(slug, month, trends)
    
    # Sort by composite score
    ranked = sorted(results.items(), key=lambda x: x[1]["score"], reverse=True)
    
    # Top 5 recommendations
    print("\n🏆 TOP 5 RECOMMENDED CATEGORIES:")
    for i, (slug, data) in enumerate(ranked[:5]):
        signals_str = " | ".join(data["signals"][:2]) if data["signals"] else "baseline"
        print(f"   {i+1}. {slug} (score: {data['score']}) — {signals_str}")
    
    # Pick the recommended topic
    # Weighted random among top 8 (not just #1, to maintain variety)
    top8 = ranked[:8]
    weights = [d["score"] for _, d in top8]
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0
    pick = top8[0]
    for (slug, data), w in zip(top8, weights):
        cumulative += w
        if r <= cumulative:
            pick = (slug, data)
            break
    
    picked_slug, picked_data = pick
    
    # Pick best angle
    angle = picked_data["suggested_angles"][0]
    
    # Seasonal insights for the intro
    month_names = ["", "January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    seasonal_note = ""
    if picked_data["seasonal_multiplier"] > 1.3:
        seasonal_note = f"{month_names[month]} is peak search season for {picked_slug.replace('-', ' ')}. Capitalize now."
    
    findings = {
        "generated_at": now.isoformat(),
        "month": month_names[month],
        "month_num": month,
        "all_categories_scored": {slug: {
            "score": d["score"],
            "buyer_intent": d["buyer_intent"],
            "seasonal": d["seasonal_multiplier"] > 1.2,
        } for slug, d in ranked},
        "recommended": {
            "slug": picked_slug,
            "angle": angle,
            "demand_score": picked_data["score"],
            "buyer_intent": picked_data["buyer_intent"],
            "target_keywords": picked_data["target_keywords"],
            "signals": picked_data["signals"],
            "seasonal_note": seasonal_note,
            "writing_tips": generate_writing_tips(picked_slug, picked_data),
        },
        "top5_categories": [{"slug": s, "score": d["score"]} for s, d in ranked[:5]],
    }
    
    out_path = Path("research_findings.json")
    with open(out_path, "w") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Research complete → {out_path}")
    print(f"   Pick: {picked_slug}")
    print(f"   Angle: {angle}")
    print(f"   Keywords: {', '.join(picked_data['target_keywords'])}")
    print(f"   {seasonal_note}")
    
    return findings

def generate_writing_tips(slug: str, data: dict) -> list[str]:
    """Generate category-specific writing tips based on demand signals."""
    tips = [
        "Open with your strongest opinion — don't bury the verdict.",
        "Include at least one Reddit user quote or anecdote.",
        "End every product section with 'Buy this if / Skip if'.",
    ]
    if data["buyer_intent"] == "HIGH":
        tips.append("HIGH buyer intent: emphasize value-for-money and comparison to premium alternatives.")
    if data["seasonal_multiplier"] > 1.3:
        tips.append("Seasonal peak — mention the timing in the intro ('If you're shopping this month...').")
    return tips

if __name__ == "__main__":
    main()
