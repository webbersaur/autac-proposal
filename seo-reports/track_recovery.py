"""Track SEO recovery on the 30 URLs we restored or moved on 2026-05-05.

Pulls GSC page-dimension data for the most recent 30 days, the prior 30 days,
and the pre-restoration baseline (Nov 5 2025 – Feb 3 2026), then renders a
focused HTML scorecard showing recovery for each tracked URL.

Usage:
    /Users/saurus/Documents/workspace/mcp-gsc/.venv/bin/python track_recovery.py

Outputs (next to this script):
    recovery-scorecard-YYYY-MM-DD.html        archived
    recovery-scorecard.html                    latest
    recovery-data-YYYY-MM-DD.json              raw GSC data
"""
from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

HERE = Path(__file__).resolve().parent
ENV_PATH = Path.home() / ".env"
SITE_URL = "https://autacusa.com/"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
MIGRATION_DATE = date(2026, 4, 26)      # New static site went live
RESTORATION_DATE = date(2026, 5, 5)     # Hub-page move + 25 post restorations

# Tracked URLs grouped by category. Order in each list = priority.
TRACKED: list[tuple[str, list[str]]] = [
    ("Hub Pages (URL moved /products/<slug>/ → /<slug>/)", [
        "https://www.autacusa.com/coiled-cords/",
        "https://www.autacusa.com/retractile-cords/",
        "https://www.autacusa.com/curly-cords/",
        "https://www.autacusa.com/cord-sets/",
        "https://www.autacusa.com/color-charts/",
    ]),
    ("Restored Blog Posts (was 404, now serving original WP content)", [
        "https://www.autacusa.com/why-does-a-coiled-extension-lead-heat-up/",
        "https://www.autacusa.com/can-extension-cords-get-wet/",
        "https://www.autacusa.com/how-to-fix-a-coiled-cord-with-ease/",
        "https://www.autacusa.com/telephone-cord/",
        "https://www.autacusa.com/wire-coil-everything-you-need-to-know/",
        "https://www.autacusa.com/the-best-extension-cord-for-power-washers/",
        "https://www.autacusa.com/guide-to-spiral-cord-wraps/",
        "https://www.autacusa.com/ac-power-cable-cord-understanding-its-importance-and-uses/",
        "https://www.autacusa.com/coiled-instrument-cable/",
        "https://www.autacusa.com/cord-cable/",
        "https://www.autacusa.com/power-cord-for-lift-chair/",
        "https://www.autacusa.com/coil-cables/",
        "https://www.autacusa.com/headphone-coiled-extension-cable/",
        "https://www.autacusa.com/choosing-a-coiled-cable-what-you-need-to-know/",
        "https://www.autacusa.com/spiral-cables/",
        "https://www.autacusa.com/phone-extension-cord-everything-you-need-to-know/",
        "https://www.autacusa.com/extension-cord-retractable/",
        "https://www.autacusa.com/coil-cord-wire/",
    ]),
    ("Off-Topic Posts Redirected to Relevant Pages (May 5)", [
        "https://www.autacusa.com/how-to-fix-retractable-cord-on-iron/",
        "https://www.autacusa.com/how-to-fix-a-retractable-badge-reel/",
        "https://www.autacusa.com/how-to-repair-a-retractable-badge-reel/",
        "https://www.autacusa.com/understanding-vga-cable-cord/",
        "https://www.autacusa.com/straight-wiring-a-cooling-fan/",
        "https://www.autacusa.com/tv-cables-cords-everything-you-need-to-know-for-the-best-home-entertainment-setup/",
        "https://www.autacusa.com/how-to-hide-cable-cords-on-a-wall/",
    ]),
]

# Pre-restoration baseline: a known good 90-day period before everything broke.
# Nov 5 2025 – Feb 3 2026. We keep this fixed across runs so the comparison is stable.
BASELINE_START = date(2025, 11, 5)
BASELINE_END = date(2026, 2, 3)


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def gsc_service():
    env = load_env(ENV_PATH)
    creds = Credentials(
        token=None,
        refresh_token=env['GOOGLE_REFRESH_TOKEN'],
        client_id=env['GOOGLE_CLIENT_ID'],
        client_secret=env['GOOGLE_CLIENT_SECRET'],
        token_uri='https://oauth2.googleapis.com/token',
        scopes=SCOPES,
    )
    return build('searchconsole', 'v1', credentials=creds, cache_discovery=False)


def fetch_pages(svc, start: date, end: date) -> dict[str, dict]:
    body = {
        'startDate': start.isoformat(),
        'endDate': end.isoformat(),
        'dimensions': ['page'],
        'rowLimit': 1000,
        'dataState': 'all',
    }
    resp = svc.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()
    return {row['keys'][0]: row for row in resp.get('rows', [])}


def render_html(baseline: dict, premigration: dict, postmigration: dict,
                baseline_range: tuple[date, date],
                premigration_range: tuple[date, date],
                postmigration_range: tuple[date, date]) -> str:
    sections_html = []

    pre_days = (premigration_range[1] - premigration_range[0]).days + 1
    post_days = (postmigration_range[1] - postmigration_range[0]).days + 1
    base_days = (baseline_range[1] - baseline_range[0]).days + 1

    # Normalize comparisons to "impressions per day" so a 90d baseline doesn't
    # dwarf an 8d post-migration window.
    def per_day(impr: int, days: int) -> float:
        return impr / days if days else 0

    grand = {
        'baseline_impr': 0, 'pre_impr': 0, 'post_impr': 0,
        'baseline_clicks': 0, 'pre_clicks': 0, 'post_clicks': 0,
        'recovered_count': 0, 'total': 0,
    }

    for category, urls in TRACKED:
        rows = []
        cat_base = cat_pre = cat_post = 0
        for url in urls:
            b = baseline.get(url, {'impressions': 0, 'clicks': 0, 'position': 0})
            p = premigration.get(url, {'impressions': 0, 'clicks': 0, 'position': 0})
            r = postmigration.get(url, {'impressions': 0, 'clicks': 0, 'position': 0})

            grand['total'] += 1
            grand['baseline_impr'] += b['impressions']
            grand['pre_impr'] += p['impressions']
            grand['post_impr'] += r['impressions']
            grand['baseline_clicks'] += b['clicks']
            grand['pre_clicks'] += p['clicks']
            grand['post_clicks'] += r['clicks']
            cat_base += b['impressions']
            cat_pre += p['impressions']
            cat_post += r['impressions']

            base_per_day = per_day(b['impressions'], base_days)
            pre_per_day = per_day(p['impressions'], pre_days)
            post_per_day = per_day(r['impressions'], post_days)

            # Recovered = post-migration daily rate is at least 25% of baseline daily rate
            recovered = base_per_day > 0 and post_per_day >= base_per_day * 0.25
            if recovered:
                grand['recovered_count'] += 1

            short = url.replace('https://www.autacusa.com', '') or '/'
            if len(short) > 60:
                short = short[:57] + '…'

            recovery_pct = (post_per_day / base_per_day * 100) if base_per_day else 0
            recovery_cls = 'up' if recovery_pct >= 50 else ('flat' if recovery_pct >= 25 else 'down')
            recovery_label = (f'<span class="{recovery_cls}">{recovery_pct:.0f}%</span>'
                              if base_per_day else '<span class="dim">—</span>')

            def cell(total: int, daily: float) -> str:
                return f'{total} <span class="dim">({daily:.1f}/d)</span>' if total else '<span class="flat">0</span>'

            rows.append(
                f'<tr><td><a href="{url}" target="_blank">{short}</a></td>'
                f'<td>{cell(b["impressions"], base_per_day)}</td>'
                f'<td>{cell(p["impressions"], pre_per_day)}</td>'
                f'<td>{cell(r["impressions"], post_per_day)}</td>'
                f'<td>{recovery_label}</td>'
                f'<td>{r["clicks"]}</td></tr>'
            )

        cat_base_pd = per_day(cat_base, base_days)
        cat_post_pd = per_day(cat_post, post_days)
        cat_recovery = (cat_post_pd / cat_base_pd * 100) if cat_base_pd else 0
        sections_html.append(
            f'<h2>{category}</h2>\n'
            f'<p class="cat-summary">Baseline: <strong>{cat_base:,}</strong> impr ({cat_base_pd:.1f}/day) '
            f'· Post-migration: <strong>{cat_post:,}</strong> impr ({cat_post_pd:.1f}/day) '
            f'· Recovery: <strong>{cat_recovery:.0f}%</strong> of baseline daily rate</p>\n'
            '<table><thead><tr>'
            '<th>URL</th>'
            f'<th title="{baseline_range[0]} → {baseline_range[1]} ({base_days} days, pre-decline)">Baseline ({base_days}d)</th>'
            f'<th title="{premigration_range[0]} → {premigration_range[1]} ({pre_days} days, WP-decline period)">Pre-Migration ({pre_days}d)</th>'
            f'<th title="{postmigration_range[0]} → {postmigration_range[1]} ({post_days} days, since new site launch)">Post-Migration ({post_days}d)</th>'
            '<th>% Recovered</th>'
            '<th>Post Clicks</th>'
            '</tr></thead><tbody>\n'
            + '\n'.join(rows) +
            '\n</tbody></table>'
        )

    base_pd = per_day(grand['baseline_impr'], base_days)
    post_pd = per_day(grand['post_impr'], post_days)
    overall_recovery = (post_pd / base_pd * 100) if base_pd else 0

    today = date.today().strftime('%B %-d, %Y')
    days_since_migration = (date.today() - MIGRATION_DATE).days
    days_since_restoration = (date.today() - RESTORATION_DATE).days

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AUTAC Recovery Scorecard</title>
<style>
  :root {{
    --primary: #1a1a2e;
    --accent: #e94560;
    --bg: #f8f9fa;
    --card-bg: #ffffff;
    --text: #2d3436;
    --text-light: #636e72;
    --green: #00b894;
    --red: #d63031;
    --border: #dfe6e9;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem 1.5rem; }}
  .header {{ background: var(--primary); color: white; padding: 2.5rem 0; margin-bottom: 2rem; }}
  .header .container {{ display: flex; justify-content: space-between; align-items: center; }}
  .header h1 {{ font-size: 1.6rem; font-weight: 700; }}
  .header h1 span {{ color: var(--accent); }}
  .header .meta {{ text-align: right; font-size: 0.85rem; opacity: 0.85; }}
  .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: var(--card-bg); border-radius: 8px; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .card .label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-light); margin-bottom: 0.25rem; }}
  .card .value {{ font-size: 1.6rem; font-weight: 700; }}
  .card .value.green {{ color: var(--green); }}
  .card .value.red {{ color: var(--red); }}
  .card .value.yellow {{ color: #e17055; }}
  h2 {{ font-size: 1.1rem; font-weight: 700; margin: 2rem 0 0.5rem; padding: 0.5rem 0; border-bottom: 2px solid var(--accent); color: var(--primary); }}
  .cat-summary {{ font-size: 0.9rem; color: var(--text-light); margin-bottom: 0.75rem; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card-bg); border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 0.5rem; font-size: 0.85rem; }}
  th {{ background: var(--primary); color: white; padding: 0.6rem 0.75rem; text-align: left; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; cursor: help; }}
  th:nth-child(n+2) {{ text-align: right; }}
  td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }}
  td:nth-child(n+2) {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td a {{ color: var(--text); text-decoration: none; }}
  td a:hover {{ color: var(--accent); }}
  tr:hover td {{ background: #f1f3f5; }}
  .up {{ color: var(--green); font-weight: 700; }}
  .down {{ color: var(--red); font-weight: 700; }}
  .flat {{ color: var(--text-light); }}
  .dim {{ color: #b2bec3; font-style: italic; }}
  .footer {{ text-align: center; margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border); font-size: 0.8rem; color: var(--text-light); }}
  .note {{ background: #e8f4fd; border-left: 4px solid #2196f3; padding: 1rem 1.25rem; border-radius: 0 6px 6px 0; margin-bottom: 1.5rem; font-size: 0.9rem; }}
</style>
</head>
<body>
<div class="header">
  <div class="container">
    <h1>AUTAC <span>Recovery Scorecard</span></h1>
    <div class="meta">
      autacusa.com<br>
      {today}<br>
      Day {days_since_migration} since migration ({MIGRATION_DATE.strftime('%b %-d')})
      &middot; Day {days_since_restoration} since restoration ({RESTORATION_DATE.strftime('%b %-d')})
    </div>
  </div>
</div>
<div class="container">

<div class="summary-cards">
  <div class="card">
    <div class="label">URLs Tracked</div>
    <div class="value">{grand['total']}</div>
  </div>
  <div class="card">
    <div class="label">Recovered (≥25% baseline)</div>
    <div class="value {'green' if grand['recovered_count'] >= grand['total']/2 else 'yellow'}">{grand['recovered_count']} / {grand['total']}</div>
  </div>
  <div class="card">
    <div class="label">Baseline Impr/Day</div>
    <div class="value">{base_pd:.1f}</div>
  </div>
  <div class="card">
    <div class="label">Post-Migration Impr/Day</div>
    <div class="value {'green' if overall_recovery >= 50 else ('yellow' if overall_recovery >= 25 else 'red')}">{post_pd:.1f}</div>
  </div>
  <div class="card">
    <div class="label">Recovery vs Baseline</div>
    <div class="value {'green' if overall_recovery >= 50 else ('yellow' if overall_recovery >= 25 else 'red')}">{overall_recovery:.0f}%</div>
  </div>
  <div class="card">
    <div class="label">Post-Migration Clicks</div>
    <div class="value">{grand['post_clicks']}</div>
  </div>
</div>

<div class="note">
  <strong>How to read this:</strong> The new static site went live on <strong>{MIGRATION_DATE.strftime('%b %-d, %Y')}</strong>;
  hub-page restorations + 25 deleted-post restorations shipped on <strong>{RESTORATION_DATE.strftime('%b %-d')}</strong>.
  All numbers are normalized to <strong>impressions per day</strong> so windows of different lengths can be compared fairly.
  <br><br>
  • <strong>Baseline ({base_days}d)</strong>: Nov 5 2025 – Feb 3 2026, before the WP-era ranking decline. The "what we should be earning" target.<br>
  • <strong>Pre-Migration ({pre_days}d)</strong>: the WP-era decline period leading up to the Apr 26 launch.<br>
  • <strong>Post-Migration ({post_days}d)</strong>: live data since the new site went up. Very small sample early on — check back weekly.<br>
  • <strong>% Recovered</strong>: post-migration daily rate as a fraction of baseline daily rate. ≥25% = recovering, ≥50% = strong recovery.
</div>

{chr(10).join(sections_html)}

<div class="footer">
  Prepared by Webbersaurus · Data: Google Search Console API · Re-run with track_recovery.py
</div>
</div>
</body>
</html>"""


def main() -> None:
    today = date.today()
    # Post-migration: from the day after launch to today (inclusive)
    post_start = MIGRATION_DATE + timedelta(days=1)
    post_end = today
    # Pre-migration: the 30 days leading up to launch
    pre_end = MIGRATION_DATE - timedelta(days=1)
    pre_start = pre_end - timedelta(days=29)

    print(f"Baseline:       {BASELINE_START} → {BASELINE_END}")
    print(f"Pre-Migration:  {pre_start} → {pre_end}")
    print(f"Post-Migration: {post_start} → {post_end}")
    print()

    svc = gsc_service()
    print("Fetching baseline…")
    baseline = fetch_pages(svc, BASELINE_START, BASELINE_END)
    print(f"  {len(baseline)} URLs in baseline window")
    print("Fetching pre-migration…")
    premigration = fetch_pages(svc, pre_start, pre_end)
    print(f"  {len(premigration)} URLs in pre-migration window")
    print("Fetching post-migration…")
    postmigration = fetch_pages(svc, post_start, post_end)
    print(f"  {len(postmigration)} URLs in post-migration window")

    stamp = today.isoformat()
    raw = HERE / f'recovery-data-{stamp}.json'
    raw.write_text(json.dumps({
        'baseline': baseline,
        'premigration': premigration,
        'postmigration': postmigration,
        'baseline_range': [BASELINE_START.isoformat(), BASELINE_END.isoformat()],
        'premigration_range': [pre_start.isoformat(), pre_end.isoformat()],
        'postmigration_range': [post_start.isoformat(), post_end.isoformat()],
        'migration_date': MIGRATION_DATE.isoformat(),
        'restoration_date': RESTORATION_DATE.isoformat(),
    }, indent=2))

    html = render_html(
        baseline, premigration, postmigration,
        (BASELINE_START, BASELINE_END),
        (pre_start, pre_end),
        (post_start, post_end),
    )
    archive = HERE / f'recovery-scorecard-{stamp}.html'
    archive.write_text(html)
    shutil.copyfile(archive, HERE / 'recovery-scorecard.html')

    print(f"\nWrote {archive.name} and refreshed recovery-scorecard.html")


if __name__ == '__main__':
    main()
