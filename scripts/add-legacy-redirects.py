#!/usr/bin/env python3
"""Merge legacy-URL 301s into vercel.json.

After the WordPress migration a long tail of old URLs kept earning impressions
while returning 404. Google was still ranking them for our core commercial terms
(29 different URLs surfaced for "retractile cord" alone), which split relevance
across dead pages instead of consolidating it on the hubs.

Each mapping below sends a dead URL to the closest *topically equivalent* live
page. That constraint matters: a 301 from an unrelated page is treated as a soft
404 and helps nothing, so genuinely off-topic legacy content (hose reels,
magnetic-field physics explainers, a spiral staircase page) is deliberately left
to 404. Those are listed in LEAVE_404 with the reason.

Idempotent - existing sources are never duplicated. Run:

    python3 scripts/add-legacy-redirects.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "vercel.json"

REDIRECTS: dict[str, str] = {}


def route(destination: str, *sources: str) -> None:
    for src in sources:
        REDIRECTS[src] = destination


# --- Coiled cord product terms -------------------------------------------
route(
    "/coiled-cords/",
    # Restored WP posts consolidated into the hub 2026-09-08. They ranked 41-61
    # for the hub's own head terms with 0 clicks and 1-2 internal links each,
    # splitting "coil cable" / "coiled cord" relevance four ways.
    "/coil-cables/",
    "/coil-cord-wire/",
    "/coiled-instrument-cable/",
    "/spiral-cables/",
    "/understanding-the-coiled-cord-design-working-principles-uses-and-advantages/",
    "/flexy-coiled-extension-cords-the-ultimate-guide-for-functionality-and-efficiency/",
    "/the-complete-guide-to-coiled-extension-cables-and-flexible-cord-solutions/",
    "/coiled-usb-extension-cable-features-benefits-uses-and-buying-guide/",
    "/retractable-coil-cables-design-functionality-applications-and-advantages/",
    "/expert-coiled-cables-the-ultimate-guide-to-performance-and-durability/",
    "/what-is-the-purpose-of-coiled-cords-ultimate-guide/",
    "/retractable-coiled-electrical-cables/",
    "/retractable-coil-cables/",
    "/coiled-keyboard-cables/",
    "/braided-keyboard-cables/",
    "/custom-coiled-cord/",
    "/power-cord-coil/",
)

# --- Retractile cord product terms ---------------------------------------
route(
    "/retractile-cords/",
    "/retractile-power-cords-retractable-coil-cable/",
    # Still indexed and 404ing as of 2026-08-21 (found via GSC page dimension):
    "/retractile-cords-manufacturer-in-branford-ct/",
    "/retractile-cords-and-electric-cables-from-autac-inc/",
    "/retractile-cords-the-primary-benefits-associated-with-them/",
    "/retractile-cords-the-ultimate-cable-management-solution/",
    "/installing-your-retractable-power-lead/",
    "/guide-to-retractile-power-cords/",
    "/retractable-electric-extension-cord/",
    "/retractile-power-cords-ct/",
    "/retractable-cords-and-cables/",
    "/retractable-extension-lead/",
    "/retractile-power-cord/",
    "/retractable-power-cords/",
    "/retractable-power-lead/",
    "/autac-retractile-cords/",
    "/retractile-cord/",
)

# --- Curly / telephone cord terms ----------------------------------------
route(
    "/curly-cords/",
    "/curly-phone-cord/",  # restored WP post, consolidated 2026-09-08
    "/telephone-spiral-cables-a-comprehensive-guide-to-coiled-communication-cords/",
    "/white-telephone-coil-cord-the-sleek-upgrade-for-modern-communication/",
    "/high-quality-telephone-line-cables-coil-cords-reliable-connectivity/",
    "/why-choose-a-curly-power-cord-benefits-uses-explained/",
    "/retractable-telephone-cords/",
    "/retractable-phone-cords/",
)

# --- Cord set / custom assembly terms ------------------------------------
route(
    "/cord-sets/",
    "/international-rated-cables-global-safety-standards-applications-compliance-guide/",
    "/international-power-cords-global-plug-types-compatibility-travel-power-solutions/",
    "/how-to-choose-the-right-custom-electric-cable-for-your-project/",
    "/custom-electrical-cables-tailored-solutions-for-your-needs/",
    "/multi-hole-plug-board-efficient-power-distribution-for-every-space/",
    "/the-comprehensive-guide-to-electrical-cord-accessories/",
    "/how-to-choose-industrial-electric-cord/",
    "/custom-molded-power-cords/",
    "/flexible-cords-with-extension/",
    "/electric-shield-power-cord/",
    "/custom-cable-wire/",
)

# --- Spiral cable terms (guide page folded into the hub 2026-09-08) --------
route(
    "/coiled-cords/",
    "/complete-best-guide-on-spiral-cable-keyboard-in-2025/",
    "/spiral-lightning-cable-the-perfect-solution/",
    "/spiral-cable-vs-traditional-cords/",
    "/cable-with-magnetic-cord/",
    "/spiral-cable/",
)

# --- Informational posts with a live equivalent --------------------------
route("/how-to-fix-retractable-cord-on-iron/", "/retractable-cord-steam-iron/")
route("/how-to-repair-a-retractable-badge-reel/", "/retractable-badge-reel/")
route(
    "/extension-cords-recoil-maintenance-and-repair-guide/",
    "/how-to-repair-extension-cord-recoil-step-by-step-repair-guide/",
)
route(
    "/the-best-extension-cord-for-power-washers/",
    "/extension-cord-for-your-power-washer/",
)
route(
    "/blog/",
    "/say-goodbye-to-tangles-the-best-cable-cords-for-every-setup/",
    "/retractable-cord-reel-for-small-appliances-design-benefits-and-applications/",
    "/reel-extension-leads-types-benefits-and-safe-usage-guide/",
    "/best-cable-cords-for-every-setup/",
    "/extension-cords-make-life-easy-ct/",
    "/reel-extension-leads/",
)

# --- Company / solutions -------------------------------------------------
route("/solutions/", "/communications-and-security-solutions/")
route(
    "/news/",
    "/marie-louise-burkle-graduates-national-speakers-academy-class-of-2019/",
    "/marie-louise-burkle-hits-20-year-milestone-as-ceo/",
)

# WordPress taxonomy remnants. Regex sources so paginated variants
# (/tag/foo/page/4/) collapse too.
TAXONOMY = [
    (r"/tag/(.*)", "/blog/"),
    (r"/category/(.*)", "/blog/"),
]

# Deliberately NOT redirected - off topic for a cord manufacturer, so a 301 to
# any hub would read as a soft 404. Left to return 404 and drop out of the index.
LEAVE_404 = {
    "/magnetic-field-in-a-straight-wire-...": "physics explainer, not a product",
    "/magnetic-field-of-a-straight-wire-...": "physics explainer, not a product",
    "/what-are-the-ayleid-retractable-garden-hose-reel/": "garden hose reels",
    "/best-guide-on-water-hose-reel-retractable/": "garden hose reels",
    "/best-guide-on-retractable-water-hose-reel/": "garden hose reels",
    "/what-are-self-retracting-garden-hose-reel/": "garden hose reels",
    "/self-retracting-marvels-...-hose-reels/": "garden hose reels",
    "/ultimate-guide-on-hozelock-spiral-garden-hose-...": "garden hose reels",
    "/the-complete-guide-to-air-retractable-hose-reels-...": "hose reels",
    "/retractable-air-hose-reel/": "hose reels",
    "/outdoor-retractable-cord-reel/": "cord reels, a product we do not make",
    "/outdoor-power-cord-reel/": "cord reels, a product we do not make",
    "/right-outdoor-electric-cord-reel/": "cord reels, a product we do not make",
    "/retractable-electric-cord-reels/": "cord reels, a product we do not make",
    "/spiral-staircase-loft-extensions/": "staircases",
    "/retraction-cord-in-dentistry/": "dental retraction cord, unrelated product",
    "/how-to-straight-wire-ac-compressor-...": "automotive repair",
    "/experience-with-the-straight-wire/": "audio cable brand, unrelated",
    "/straight-wire-cables-structure-...": "straight wire, not our product",
    "/best-guide-on-coil-on-plug-extension-lead-in-2026/": "automotive ignition coils",
}


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    existing = {r["source"] for r in cfg.get("redirects", [])}
    by_source = {r["source"]: r for r in cfg.get("redirects", [])}

    added, skipped, repointed = [], [], []
    for source, destination in REDIRECTS.items():
        if source in existing:
            if by_source[source]["destination"] != destination:
                by_source[source]["destination"] = destination
                repointed.append(source)
            else:
                skipped.append(source)
            continue
        cfg["redirects"].append(
            {"source": source, "destination": destination, "permanent": True}
        )
        added.append(source)

    for source, destination in TAXONOMY:
        if source in existing:
            skipped.append(source)
            continue
        cfg["redirects"].append(
            {"source": source, "destination": destination, "permanent": True}
        )
        added.append(source)

    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"added {len(added)} redirects, repointed {len(repointed)}, skipped {len(skipped)} already present")
    print(f"vercel.json now has {len(cfg['redirects'])} redirects")
    print(f"{len(LEAVE_404)} off-topic legacy URLs deliberately left to 404")


if __name__ == "__main__":
    main()
