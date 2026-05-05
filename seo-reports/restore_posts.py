"""Restore top-traffic WordPress posts to the static site at root URLs.

Pipeline:
  1. Load top-N candidates from restoration-candidates.json (already prioritized)
  2. For each: fetch the WP post body from wp-posts.json
  3. Clean the body HTML (rn → newlines, fix internal links, strip cruft)
  4. Wrap in the existing blog template, substituting metadata
  5. Write to /<slug>/index.html at the repo root
  6. Update sitemap.xml

Usage:
    /Users/saurus/Documents/workspace/mcp-gsc/.venv/bin/python restore_posts.py [N]
        N defaults to 25.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path('/Users/saurus/Documents/workspace/autac')
TEMPLATE_PATH = REPO / 'blog' / 'coil-cable-guide' / 'index.html'
SEO = REPO / 'seo-reports'

# Slugs that exist on the new site (so we can fix internal links to them)
EXISTING_PATHS: set[str] = set()
EXISTING_BLOG_SLUGS: set[str] = set()
RESTORED_SLUGS: set[str] = set()  # filled in below


def discover_existing() -> None:
    EXISTING_PATHS.add('/')
    for p in REPO.rglob('index.html'):
        if any(part.startswith('.') for part in p.parts): continue
        if p.parts[len(REPO.parts):][:1] in (('node_modules',), ('seo-reports',), ('supabase',)): continue
        rel = p.relative_to(REPO).parent
        EXISTING_PATHS.add('/' + str(rel) + '/' if str(rel) != '.' else '/')
    for p in (REPO / 'blog').iterdir():
        if p.is_dir(): EXISTING_BLOG_SLUGS.add(p.name)


BLOCK_TAGS = ('h1','h2','h3','h4','h5','h6','ul','ol','table','blockquote',
              'figure','div','section','article','aside','pre','hr','iframe')

def clean_wp_html(html: str) -> str:
    """Convert WP-stored content into clean HTML."""
    html = html.replace('\r\n', '\n').replace('\r', '\n')

    # Strip Divi/visual-builder shortcodes if present
    html = re.sub(r'\[/?et_pb_[^\]]*\]', '', html)
    html = re.sub(r'\[caption[^\]]*\]', '', html)
    html = re.sub(r'\[/caption\]', '', html)

    # Strip <strong> wrappers from headings (cosmetic)
    html = re.sub(
        r'<(h[1-6])>\s*<strong>(.*?)</strong>\s*</\1>',
        r'<\1>\2</\1>',
        html, flags=re.DOTALL,
    )

    # Yoast/Gutenberg cruft: empty span wrappers with style attrs
    html = re.sub(r'<span[^>]*>(.*?)</span>', r'\1', html, flags=re.DOTALL)

    # Strip empty paragraphs
    html = re.sub(r'<p>\s*(?:&nbsp;)?\s*</p>', '', html)

    # Force a paragraph break before/after any block-level opening tag so the
    # splitter treats each block as its own chunk.
    block_open = '|'.join(BLOCK_TAGS + ('p',))
    html = re.sub(rf'(<\s*(?:{block_open})\b)', r'\n\n\1', html, flags=re.IGNORECASE)
    html = re.sub(rf'(</\s*(?:{block_open})\s*>)', r'\1\n\n', html, flags=re.IGNORECASE)

    html = html.strip()

    # Wrap bare text paragraphs in <p> tags. Split on blank lines and wrap any
    # block that doesn't already start with a known block tag.
    paragraphs = re.split(r'\n\s*\n', html)
    wrapped = []
    for para in paragraphs:
        para = para.strip()
        if not para: continue
        first_tag_match = re.match(r'<\s*([a-zA-Z0-9]+)', para)
        first_tag = first_tag_match.group(1).lower() if first_tag_match else None
        if first_tag in BLOCK_TAGS or first_tag == 'p':
            wrapped.append(para)
        else:
            # Bare text — wrap in <p>. Don't insert <br>; collapse internal newlines to spaces.
            inner = re.sub(r'\s*\n\s*', ' ', para)
            wrapped.append(f'<p>{inner}</p>')
    html = '\n\n'.join(wrapped)

    # Fix internal links: rewrite or strip dead WP links
    def fix_link(m):
        href = m.group(1).strip()
        # Normalize: drop protocol+host
        path = href
        for prefix in ('https://www.autacusa.com', 'https://autacusa.com',
                       'http://www.autacusa.com', 'http://autacusa.com'):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
        if not path.startswith('/'):
            return m.group(0)  # external link, leave alone

        # Strip trailing /
        slug = path.strip('/').split('/')[-1] if path.strip('/') else ''

        # Map old paths to known new paths
        target = None
        for candidate in [path, path.rstrip('/') + '/', '/' + slug + '/']:
            if candidate in EXISTING_PATHS:
                target = candidate; break
        if not target and slug in EXISTING_BLOG_SLUGS:
            target = f'/blog/{slug}/'
        if not target and slug in RESTORED_SLUGS:
            target = f'/{slug}/'

        if target:
            return f'href="{target}"'
        # Dead link — strip the anchor, keep the text
        return 'STRIP_LINK'

    # First pass: rewrite hrefs
    def replace_href(m):
        result = fix_link(m)
        if result == 'STRIP_LINK':
            return 'data-stripped="true"'
        return result

    html = re.sub(r'href="([^"]+)"', replace_href, html)

    # Second pass: drop the entire <a ...data-stripped> wrapper, keeping inner text
    html = re.sub(
        r'<a [^>]*data-stripped="true"[^>]*>(.*?)</a>',
        r'\1',
        html, flags=re.DOTALL
    )

    # Remove <strong> wrappers around bare links (cosmetic cleanup)
    html = re.sub(r'<strong>\s*</strong>', '', html)

    # Re-tighten whitespace
    html = re.sub(r'\n{3,}', '\n\n', html)

    return html.strip()


def derive_meta_description(body_text: str, max_len: int = 155) -> str:
    """Pull the first meaningful sentence from cleaned content."""
    text = re.sub(r'<[^>]+>', '', body_text)  # strip tags
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    last_space = cut.rfind(' ')
    return (cut[:last_space] if last_space > 100 else cut).rstrip(',.') + '…'


def estimate_read_time(body_html: str) -> int:
    words = len(re.sub(r'<[^>]+>', '', body_html).split())
    return max(3, round(words / 220))  # 220 wpm


def derive_badge(title: str) -> str:
    """A short label for the hero badge."""
    t = title.lower()
    if any(w in t for w in ['guide', 'how to', "what is", "tips"]):
        if t.startswith('how to'): return 'How-To Guide'
        if 'what is' in t or 'understanding' in t: return 'Reference'
        return 'Guide'
    if 'fix' in t or 'repair' in t: return 'Repair Guide'
    return 'Article'


def render_h1(title: str) -> str:
    """Add a <span> highlight on the most distinctive phrase."""
    # Highlight a noun phrase if title has a colon
    if ':' in title:
        head, tail = title.split(':', 1)
        return f'{head.strip()}: <span>{tail.strip()}</span>'
    # Otherwise highlight the last 2-3 words
    words = title.split()
    if len(words) >= 5:
        return ' '.join(words[:-3]) + ' <span>' + ' '.join(words[-3:]) + '</span>'
    return title


def derive_subtitle(title: str) -> str:
    """A short hero subtitle. Generic enough for any topic."""
    return f'{title} — practical guidance, technical specifications, and sourcing options from a Connecticut retractile cord manufacturer.'


# Standard CTA + related-links overrides (same on every restored post)
CTA_TITLE = 'Need Custom Cords for Your Application?'
CTA_DESC = 'Autac has manufactured retractile, coiled, and curly cords in North Branford, CT since 1947. Send us your specifications and we will recommend a stock part or engineer a custom solution.'

RELATED_LINKS = [
    ('/retractile-cords/', 'Retractile Cords'),
    ('/coiled-cords/', 'Coiled Cords'),
    ('/curly-cords/', 'Curly Cords'),
    ('/build-your-cord/', 'Build Your Cord'),
    ('/quote/', 'Request a Quote'),
]


def build_post_html(template: str, *, slug: str, title: str, description: str,
                    badge: str, hero_h1: str, hero_subtitle: str,
                    pub_date_iso: str, read_min: int,
                    body_html: str) -> str:
    """Substitute template strings for a single post."""
    # Title (appears in <title> + og:title)
    OLD_TITLE = 'Coil Cable vs Coiled Cord: A Terminology Guide for Buyers | Autac USA'
    NEW_TITLE = f'{title} | Autac USA'
    html = template.replace(OLD_TITLE, NEW_TITLE)

    # JSON-LD headline (no " | Autac USA" suffix)
    OLD_JSONLD_HEADLINE = '"headline": "Coil Cable vs Coiled Cord: A Terminology Guide for Buyers"'
    html = html.replace(OLD_JSONLD_HEADLINE, f'"headline": {json.dumps(title)}')

    # Description (meta description + og:description)
    OLD_DESC = 'What is a coil cable? How does it differ from a coiled cord, retractile cord, or curly cord? A terminology guide covering coil cable types, specifications, manufacturing, and sourcing from Autac USA.'
    html = html.replace(OLD_DESC, description)

    # JSON-LD description (different copy from meta)
    OLD_JSONLD_DESC = '"description": "What is a coil cable? How does it differ from a coiled cord, retractile cord, or curly cord? A terminology and engineering guide for buyers sourcing coiled cables."'
    html = html.replace(OLD_JSONLD_DESC, f'"description": {json.dumps(description)}')

    # Canonical/og URL
    html = html.replace(
        'https://www.autacusa.com/blog/coil-cable-guide/',
        f'https://www.autacusa.com/{slug}/'
    )

    # JSON-LD datePublished
    html = html.replace('"datePublished": "2024-11-15"', f'"datePublished": "{pub_date_iso}"')

    # Hero badge
    html = html.replace(
        '<div class="page-hero-badge">Terminology Guide</div>',
        f'<div class="page-hero-badge">{badge}</div>'
    )

    # H1
    OLD_H1 = '<h1>Coil Cable vs Coiled Cord: A <span>Terminology Guide</span> for Buyers</h1>'
    html = html.replace(OLD_H1, f'<h1>{hero_h1}</h1>')

    # Hero subtitle
    OLD_SUB = "<p>Why the same product goes by different names, what the engineering distinctions actually mean, and how to specify coil cables correctly when sourcing.</p>"
    html = html.replace(OLD_SUB, f'<p>{hero_subtitle}</p>')

    # Date + read time
    OLD_META = '''<div class="article-meta">
        <span>Published November 15, 2024</span>
        <span>10 min read</span>
      </div>'''
    pub_pretty = datetime.fromisoformat(pub_date_iso).strftime('%B %-d, %Y')
    NEW_META = f'''<div class="article-meta">
        <span>Published {pub_pretty}</span>
        <span>{read_min} min read</span>
      </div>'''
    html = html.replace(OLD_META, NEW_META)

    # Article body — replace EVERYTHING between <article class="article-body"> and </article>
    article_re = re.compile(r'(<article class="article-body">)(.*?)(</article>)', re.DOTALL)
    new_article_body = '\n\n    ' + body_html.replace('\n', '\n    ') + '\n\n  '
    html = article_re.sub(lambda m: m.group(1) + new_article_body + m.group(3), html)

    # CTA section
    OLD_CTA_TITLE = '<div class="section-title">Ready to Source Your Coil Cables?</div>'
    html = html.replace(OLD_CTA_TITLE, f'<div class="section-title">{CTA_TITLE}</div>')
    OLD_CTA_DESC = '<p class="section-desc">Tell us your specifications and we will recommend the right coil cable from our catalog of 400+ standard configurations &mdash; or engineer a custom solution to your exact requirements.</p>'
    html = html.replace(OLD_CTA_DESC, f'<p class="section-desc">{CTA_DESC}</p>')

    # Related links
    OLD_RELATED = '''<div class="related-links">
        <a href="/blog/coil-cords-guide/">Coil Cords Guide &rarr;</a>
        <a href="/blog/coiled-extension-cords/">Coiled Extension Cords Guide &rarr;</a>
        <a href="/coiled-cords/">Browse Coiled Cords &rarr;</a>
        <a href="/products/">Full Product Catalog &rarr;</a>
        <a href="/build-your-cord/">Custom Cord Builder &rarr;</a>
      </div>'''
    new_related = '<div class="related-links">\n        '
    new_related += '\n        '.join(
        f'<a href="{href}">{label} &rarr;</a>' for href, label in RELATED_LINKS
    )
    new_related += '\n      </div>'
    html = html.replace(OLD_RELATED, new_related)

    return html


def update_sitemap(slugs: list[str]) -> None:
    sm_path = REPO / 'sitemap.xml'
    sm = sm_path.read_text()
    today = date.today().isoformat()

    new_entries = []
    for slug in slugs:
        url = f'https://www.autacusa.com/{slug}/'
        if url in sm:
            continue
        new_entries.append(
            f'  <url>\n'
            f'    <loc>{url}</loc>\n'
            f'    <lastmod>{today}</lastmod>\n'
            f'    <changefreq>monthly</changefreq>\n'
            f'    <priority>0.6</priority>\n'
            f'  </url>\n'
        )

    if new_entries:
        sm = sm.replace('</urlset>', ''.join(new_entries) + '</urlset>')
        sm_path.write_text(sm)
        print(f'Added {len(new_entries)} URLs to sitemap.xml')
    else:
        print('All target URLs already in sitemap.xml')


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25

    candidates = json.loads((SEO / 'restoration-candidates.json').read_text())[:n]
    posts_by_slug = {p['post_name']: p for p in json.loads((SEO / 'wp-posts.json').read_text())}
    template = TEMPLATE_PATH.read_text()

    discover_existing()

    # Two-pass: first claim all slugs we're restoring, so internal links can resolve to them
    for c in candidates:
        RESTORED_SLUGS.add(c['slug'])

    written = []
    for c in candidates:
        slug = c['slug']
        wp = posts_by_slug.get(slug)
        if not wp:
            print(f'  SKIP {slug} — not in wp-posts.json')
            continue

        title = wp['post_title']
        body = clean_wp_html(wp.get('post_content') or '')
        if not body:
            print(f'  SKIP {slug} — empty body')
            continue

        description = derive_meta_description(body)
        badge = derive_badge(title)
        hero_h1 = render_h1(title)
        hero_subtitle = derive_subtitle(title)
        pub_date_iso = wp['post_date'][:10]
        read_min = estimate_read_time(body)

        html = build_post_html(
            template,
            slug=slug, title=title, description=description,
            badge=badge, hero_h1=hero_h1, hero_subtitle=hero_subtitle,
            pub_date_iso=pub_date_iso, read_min=read_min,
            body_html=body,
        )

        out_dir = REPO / slug
        out_dir.mkdir(exist_ok=True)
        (out_dir / 'index.html').write_text(html)
        written.append(slug)
        print(f'  ✓ /{slug}/  ({c["lost_impr"]:,} impr lost, {read_min}min read)')

    print(f'\nWrote {len(written)} posts.')
    update_sitemap(written)


if __name__ == '__main__':
    main()
