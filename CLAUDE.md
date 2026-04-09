# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static HTML/CSS/JS website for **Autac USA** (autacusa.com), a 100% woman-owned retractile cord manufacturer in North Branford, CT since 1947. No build system, no bundler, no CMS — all pages are self-contained HTML with inline `<style>` blocks.

**Repo:** github.com/webbersaur/autac.git (branch: `main`)
**GitHub Pages:** https://webbersaur.github.io/autac/

## Local Development

```bash
python3 -m http.server 8080
```

## Site Structure

### Public Pages (indexed in sitemap.xml)
- `index.html` — Homepage
- `about.html` — Company history, leadership, woman-owned messaging
- `products.html` — Product catalog with filtering (loads from JSON, pricing behind Supabase OTP auth)
- `products/retractile-cords.html` — Retractile cord category
- `products/curly-cords.html` — Curly cord category
- `products/coiled-cords.html` — Coiled cord category
- `products/cord-sets.html` — Cord sets (straight, retractile, shielded assemblies)
- `products/color-charts.html` — Conductor color reference
- `solutions.html` — Industry-specific solutions
- `contact.html` — Contact form (wired to Supabase)
- `quote.html` — 5-step guided quote wizard (wired to Supabase)
- `build-your-cord.html` — 8-step custom cord configurator (wired to Supabase)
- `faq.html` — 16-question FAQ with accordion UI and FAQPage structured data
- `shop-online.html` — Links to eBay store
- `media.html` — 8 YouTube videos from WordPress site
- `news.html` — News & press index
- `news/*.html` — 9 individual news/press articles
- `blog/index.html` — Blog index
- `blog/*.html` — 34 blog posts (11 from WordPress + 23 SEO posts)
- `privacy-policy.html` — Privacy policy
- `terms-of-service.html` — Website terms of service
- `terms-of-sale.html` — B2B terms and conditions of sale (18 sections)
- `75th-anniversary.html` — 75th anniversary celebration (1947–2022)
- `2026-price-adjustments.html` — Price adjustment notice
- `holiday-schedule.html` — 2026 holiday closure schedule

### Non-indexed Files (blocked in robots.txt)
- `proposal-v1.html` — Webbersaurus website redesign proposal (different brand colors)
- `invoice-deposit.html` — Webbersaurus deposit invoice
- `admin.html` — Supabase-powered dashboard (password auth, email allowlist)

## Architecture & Patterns

### No Shared CSS/JS
Every page has its own complete inline `<style>` block and `<script>` block. When creating new pages, copy the full header/nav/footer structure and CSS from an existing page. This means **sitewide changes (nav, footer, theme) must be applied to all pages individually**.

### CSS Theme (consistent across all pages)
- `--red: #cc0a2b` / `--red-light: #e01235` — Primary CTA color
- `--accent: #f5c518` / `--accent-dark: #d4a80e` — Secondary CTA (yellow)
- `--black: #1a1a1a` — Headers, dark backgrounds
- `--font: 'Inter'` — Google Fonts (weights 400–800)
- `.container` — max-width: 1200px centered wrapper

### Page Template Structure
Every page follows: Topbar → Sticky Header (logo + nav + CTA) → Page Hero → Content → Footer

### Navigation
- Products has a hover dropdown with invisible bridge (`::before` spacer) to prevent flickering
- Dropdown items: Full Catalog, Retractile Cords, Curly Cords, Coiled Cords, Cord Sets, Color Charts
- Mobile: hamburger toggle with `nav.open` class
- "Get a Quote" yellow CTA button links to `quote.html`
- Blog link points to `blog/`
- Product subpages use `../` prefix for root-level links
- Footer has three legal links: Privacy Policy | Terms of Service | Terms of Sale

### Forms (Supabase Backend)
All three forms (`contact.html`, `quote.html`, `build-your-cord.html`) submit to Supabase tables via the JS client. A Supabase Edge Function (`supabase/functions/notify-submission/`) sends email notifications on new submissions via Resend SMTP. All forms block disposable/temporary email domains.

- **contact.html**: Simple contact form → `contacts` table
- **quote.html**: `nextStep()`/`prevStep()`/`goToStep()` navigation, `validateContact()` on step 4, NDA checkbox on step 2, generates reference number `QR-YYYYMMDD-XXXX` → `quotes` table
- **build-your-cord.html**: `cordConfig` state object, `updateSummary()` updates sticky sidebar, auto-calculates extended length (5x retracted) → `cord_configs` table
- **products.html**: Pricing behind OTP auth (`verifyOtp` type: `email`), access logged to `pricing_access_log` and `page_views` tables

## SEO Status
- Canonical tags on all pages (www.autacusa.com)
- Unique title tags and meta descriptions per page
- JSON-LD structured data on all pages
- Open Graph tags on homepage
- robots.txt and sitemap.xml in place

## When Adding New Pages
1. Copy header/nav/footer HTML and full `<style>` block from an existing page
2. Add `<link rel="canonical">` tag in `<head>`
3. Add the page to `sitemap.xml`
4. For pages in subdirectories, use `../` prefix for root-level asset/page links
5. Ensure nav dropdown includes all 6 product links (Catalog, Retractile, Curly, Coiled, Cord Sets, Color Charts)
6. Ensure footer has all 3 legal links (Privacy Policy, Terms of Service, Terms of Sale)
7. Add JSON-LD structured data appropriate to the page type
