"""Refresh the AUTAC keyword position report.

Pulls the last 7 days of GSC data for autacusa.com, then re-renders the HTML
report against the same Dec 2024 baseline as the original Apr 13 report.

Usage:
    /Users/saurus/Documents/workspace/mcp-gsc/.venv/bin/python refresh_report.py

Outputs (written next to this script):
    autac-gsc-data-YYYY-MM-DD.json   archived raw GSC response
    autac-gsc-data.json              latest copy
    autac-keyword-report-YYYY-MM-DD.html   archived report
    autac-keyword-report.html        latest copy
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

HERE = Path(__file__).resolve().parent
ENV_PATH = Path.home() / ".env"
SITE_URL = "https://autacusa.com/"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# Tracked keywords grouped by category, with their Dec 2024 baseline positions.
# `None` means "no baseline recorded" (renders as "—" in the report).
TRACKED: list[tuple[str, list[tuple[str, float | None]]]] = [
    ("Brand", [
        ("autac", None),
        ("autac inc", None),
        ("autacusa", 1),
    ]),
    ("Curly Cords", [
        ("curly cord", 1),
        ("curly cords for phones", 2),
        ("curly cords", 1),
        ("curly wire", 5),
        ("curly cord cable", 2),
        ("curly cable", 2),
        ("curly electrical cord", 4),
        ("curly electrical wire", 8),
        ("curly phone cord", 6),
        ("curly power cord", 4),
    ]),
    ("Coiled Cords", [
        ("coiled wire", 16),
        ("coiled extension cord", 3),
        ("coiled cords", 2),
        ("coiled electrical cable", 17),
        ("coil power cord", 4),
        ("coil cords", 8),
        ("coil cord", 16),
        ("coiled power cord", 2),
        ("coiled electrical cord", 7),
        ("coiled cord", 8),
        ("coiled power cable", 4),
        ("coiled power cords", 1),
        ("coil cord wire", 4),
        ("coiled electric cord", 14),
        ("extension cord coil", 7),
        ("coiled so cord", 3),
    ]),
    ("Retractile", [
        ("retractile cords", 2),
        ("retractile cable", 5),
        ("retractile cord", 8),
        ("retractile coiled cords", 8),
    ]),
    ("Retractable", [
        ("retractable coil cable", 9),
        ("retractable coil cord", 4),
        ("recoil extension cord", 5),
        ("retractable cable", 15),
        ("retractable cords", 15),
        ("retractable power cords", 17),
        ("retractable electric cords", 9),
    ]),
    ("Spiral", [
        ("spiral extension cord", 1),
        ("spiral cords", 7),
        ("spiral cord", 7),
    ]),
    ("Cord Sets", [
        ("electric cord sets", None),
        ("cord sets", 17),
    ]),
    ("Custom", [
        ("custom electrical cables", 15),
        ("custom cords", 9),
    ]),
    ("Industry", [
        ("cable overmolding", 18),
        ("coil cord manufacturer", 5),
        ("coiled cable manufacturers", 10),
        ("extension cord manufacturers usa", 8),
    ]),
    ("Other", [
        ("wire coiled", 15),
        ("straight wire", 9),
    ]),
]


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def gsc_credentials() -> Credentials:
    env = load_env(ENV_PATH)
    missing = [k for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN") if k not in env]
    if missing:
        raise SystemExit(f"Missing in {ENV_PATH}: {', '.join(missing)}")
    return Credentials(
        token=None,
        refresh_token=env["GOOGLE_REFRESH_TOKEN"],
        client_id=env["GOOGLE_CLIENT_ID"],
        client_secret=env["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


def fetch_gsc(start: date, end: date) -> dict:
    creds = gsc_credentials()
    service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "rowLimit": 1000,
        "dataState": "all",
    }
    return service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()


def render_html(data: dict, start: date, end: date) -> str:
    by_query = {row["keys"][0].lower(): row for row in data.get("rows", [])}

    total_tracked = sum(len(group) for _, group in TRACKED)
    visible = 0
    were_top10 = 0
    top10_now = 0
    for _, group in TRACKED:
        for kw, baseline in group:
            row = by_query.get(kw.lower())
            if row:
                visible += 1
                if row["position"] <= 10:
                    top10_now += 1
            if isinstance(baseline, (int, float)) and baseline <= 10:
                were_top10 += 1

    total_clicks = sum(row.get("clicks", 0) for row in data.get("rows", []))

    def fmt_baseline(b: float | None) -> str:
        if b is None:
            return "—"
        return f"{b:g}"

    def fmt_current(row: dict | None) -> str:
        if not row:
            return '<span class="dim">&mdash;</span>'
        return f"{row['position']:.1f}"

    def fmt_change(baseline: float | None, row: dict | None) -> str:
        if not row:
            return '<span class="gone">no data</span>'
        if baseline is None:
            return '<span class="dim">new</span>'
        delta = baseline - row["position"]  # positive = improved (lower position number)
        if abs(delta) < 0.5:
            return '<span class="flat">±0</span>'
        rounded = round(delta)
        if rounded > 0:
            return f'<span class="up">+{rounded}</span>'
        return f'<span class="down">{rounded}</span>'

    def fmt_int(row: dict | None, key: str) -> str:
        return str(row[key]) if row else "0"

    def fmt_ctr(row: dict | None) -> str:
        if not row:
            return "0.0%"
        return f"{row['ctr'] * 100:.1f}%"

    sections = []
    for category, group in TRACKED:
        rows_html = []
        for kw, baseline in group:
            row = by_query.get(kw.lower())
            rows_html.append(
                f"<tr><td>{kw}</td>"
                f"<td>{fmt_baseline(baseline)}</td>"
                f"<td>{fmt_current(row)}</td>"
                f"<td>{fmt_change(baseline, row)}</td>"
                f"<td>{fmt_int(row, 'clicks')}</td>"
                f"<td>{fmt_int(row, 'impressions')}</td>"
                f"<td>{fmt_ctr(row)}</td></tr>"
            )
        sections.append(
            f'<div class="cat-header">{category}</div>\n'
            '<table><thead><tr><th>Keyword</th><th>Dec 2024</th><th>Current</th>'
            '<th>Change</th><th>Clicks</th><th>Impr</th><th>CTR</th></tr></thead><tbody>\n'
            + "\n".join(rows_html) +
            '\n</tbody></table>'
        )

    today = date.today().strftime("%B %d, %Y")
    range_label = f"{start.strftime('%b %-d')} &ndash; {end.strftime('%-d, %Y')}"
    days = (end - start).days + 1

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>AUTAC Keyword Position Report</title>
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
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; }}
  .header {{ background: var(--primary); color: white; padding: 2.5rem 0; margin-bottom: 2rem; }}
  .header .container {{ display: flex; justify-content: space-between; align-items: center; }}
  .header h1 {{ font-size: 1.6rem; font-weight: 700; }}
  .header h1 span {{ color: var(--accent); }}
  .header .meta {{ text-align: right; font-size: 0.85rem; opacity: 0.8; }}
  .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: var(--card-bg); border-radius: 8px; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .card .label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-light); margin-bottom: 0.25rem; }}
  .card .value {{ font-size: 1.8rem; font-weight: 700; }}
  .card .value.red {{ color: var(--red); }}
  .card .value.green {{ color: var(--green); }}
  .card .value.yellow {{ color: #e17055; }}
  .note {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 1rem 1.25rem; border-radius: 0 6px 6px 0; margin-bottom: 1.5rem; font-size: 0.9rem; }}
  .note.blue {{ background: #e8f4fd; border-left-color: #2196f3; }}
  .cat-header {{ font-size: 1.1rem; font-weight: 700; margin: 1.5rem 0 0.5rem; padding: 0.5rem 0; border-bottom: 2px solid var(--accent); color: var(--primary); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card-bg); border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 0.5rem; font-size: 0.9rem; }}
  th {{ background: var(--primary); color: white; padding: 0.6rem 0.75rem; text-align: left; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; }}
  th:nth-child(n+3) {{ text-align: right; }}
  td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }}
  td:nth-child(n+3) {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr:hover td {{ background: #f1f3f5; }}
  .up {{ color: var(--green); font-weight: 700; }}
  .down {{ color: var(--red); font-weight: 700; }}
  .flat {{ color: var(--text-light); }}
  .gone {{ color: #b2bec3; font-style: italic; }}
  .dim {{ color: var(--text-light); }}
  .footer {{ text-align: center; margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border); font-size: 0.8rem; color: var(--text-light); }}
  .footer a {{ color: var(--accent); text-decoration: none; }}
  @media print {{
    body {{ background: white; }}
    .header, th {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head>
<body>
<div class=\"header\">
  <div class=\"container\">
    <h1>AUTAC <span>Keyword Position Report</span></h1>
    <div class=\"meta\">
      autacusa.com<br>
      {today}<br>
      GSC Data: {range_label}
    </div>
  </div>
</div>
<div class=\"container\">

<div class=\"summary-cards\">
  <div class=\"card\">
    <div class=\"label\">Keywords Tracked</div>
    <div class=\"value\">{total_tracked}</div>
  </div>
  <div class=\"card\">
    <div class=\"label\">Visible in GSC ({days}d)</div>
    <div class=\"value yellow\">{visible} / {total_tracked}</div>
  </div>
  <div class=\"card\">
    <div class=\"label\">Were Top 10 (Dec '24)</div>
    <div class=\"value\">{were_top10}</div>
  </div>
  <div class=\"card\">
    <div class=\"label\">Top 10 Now</div>
    <div class=\"value {'green' if top10_now >= were_top10 else 'red'}\">{top10_now}</div>
  </div>
  <div class=\"card\">
    <div class=\"label\">Total Clicks ({days}d)</div>
    <div class=\"value\">{total_clicks}</div>
  </div>
</div>

<div class=\"note blue\">
  <strong>Note:</strong> GSC data covers the last {days} days ({range_label}). Keywords showing &ldquo;&mdash;&rdquo; had zero impressions this window.
  Low-volume keywords may not appear in a {days}-day window even if they still rank &mdash; a live Google search may show results GSC hasn&rsquo;t logged yet.
</div>
{chr(10).join(sections)}

<div class=\"footer\">
  Prepared by <a href=\"https://webbersaur.us\">Webbersaurus</a> &bull; Data: Google Search Console API
</div>
</div>
</body>
</html>"""


def main() -> None:
    end = date.today()
    start = end - timedelta(days=7)
    print(f"Fetching GSC data for {SITE_URL} ({start} → {end})…")
    data = fetch_gsc(start, end)
    print(f"Got {len(data.get('rows', []))} rows.")

    stamp = end.isoformat()
    archive_json = HERE / f"autac-gsc-data-{stamp}.json"
    archive_html = HERE / f"autac-keyword-report-{stamp}.html"
    latest_json = HERE / "autac-gsc-data.json"
    latest_html = HERE / "autac-keyword-report.html"

    archive_json.write_text(json.dumps(data, indent=2))
    html = render_html(data, start, end)
    archive_html.write_text(html)
    shutil.copyfile(archive_json, latest_json)
    shutil.copyfile(archive_html, latest_html)

    print(f"Wrote {archive_json.name}, {archive_html.name}, and refreshed latest copies.")


if __name__ == "__main__":
    main()
