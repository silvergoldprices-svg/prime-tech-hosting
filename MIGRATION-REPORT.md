# Prime Tech Hosting – Migration & Validation Report
Build date 2026-11-03. "Local" = tested on this machine (file checks, a throw-away static server on localhost, headless Chromium). Nothing here was tested against Cloudflare or the live domain.

## 0. Read these first (they change what you should expect)
1. **The "150 existing English articles" are 7 real articles + 2 reviews + 140 placeholders.** `content-plan.csv` lists 150 titles: 7 `written`, 3 `merged` into comparison pages, 140 `planned`. The 140 planned pages say "Full article is being written" and were `index,follow` and in the original sitemap. All 166 English HTML files are preserved under `/en/` at the same relative paths, but the placeholders are now `noindex` and **excluded from `sitemap-en.xml`** (your own rule: no thin pages in sitemaps). Two one-line changes in `en-source`: stub pages `force_noindex=True`, `data/site.json` `index_drafts: false`. Flip them back if you disagree.
2. **Your planned Arabic titles list was not in the upload.** The RTF holds the 31 *existing* titles+URLs. `arabic-planned-articles.json` is empty and `tools/registry.py` is ready for the list.
3. **The XML has 4 live posts that are not in the RTF** (all 2026/07: HostGator review, GoDaddy review, Cloudflare linking, Cloudflare WAF rules). The XML is the source of truth, so all 35 live posts were migrated.
4. **Blogger images could not be downloaded** (the sandbox blocks `blogger.googleusercontent.com`). All 44 images remain hot-linked, with width/height set so layout does not jump. Download them yourself before Blogger is turned off (DEPLOY.md §5).
5. **Legacy `.html` URLs depend on a Cloudflare behaviour I could not test.** Pages redirects `*.html` to clean URLs by default. I added 35 status-200 rewrites in `_redirects`. Run the curl tests in DEPLOY.md §4 right after deploying.
6. **English has no affiliate links or tracking parameters** (14 plain brand links, 0 with `?ref/aff/utm`). Nothing was lost; if you expected affiliate links there, they were never in this zip. The 21 Arabic Hostinger referral links (`?REFERRALCODE=…`) are preserved exactly.

## 1. Arabic audit
| Item | Result |
|---|---|
| Entries in Blogger XML | 39 (35 POST/LIVE, 4 PAGE/SOFT_TRASHED); drafts 0; deleted/other 0; duplicates 0; missing permalink 0 |
| Legacy URLs supplied (RTF) | 31 – all 31 match an XML post exactly (no case/path differences) |
| Legacy posts migrated | **35 / 35** |
| Legacy paths preserved exactly (file at original path + canonical = original URL + rewrite rule) | **35 / 35** |
| Original article content missing | 0 |
| Planned titles imported | 0 (list not supplied); duplicate/overlap detection tested and working |
| Published Arabic pages | 55 files = 52 indexable + `/contact/` (noindex until email set) + `/search/` (noindex) + `404.html` |
| In `sitemap-ar.xml` | 52 (home, 35 legacy posts, 7 categories, directory, 4 company profiles, about, privacy, terms, disclosure) |
| Trashed Blogger pages | 4. About, Privacy, Terms re-created at `/about/`, `/privacy-policy/`, `/terms/` from their trashed text (internal `/p/_N.html` links repointed). Contact had only a Blogger form widget → new `/contact/` waits for an email. **Re-read the privacy text** (mentions Google Analytics/cookies) before relying on it. |
| Cleaning | Gemini/AI-chat markup (inline styles, custom elements, icon buttons) removed; 5 H1 → H2; tables kept (2) and made scrollable; code blocks kept as `<pre><code>`; 199 internal links made root-relative; raw 63,874 words vs 63,852 after cleaning (difference = code-block language labels and span spacing) |
| Raw HTML size | e.g. one post 650 KB → 34 KB after cleaning |
| lastmod | publication date (I can't tell real edit dates from the export) |

New Arabic URL rule enforced by the build: `/<slug>/`, latin lowercase slug, no date, no `.html`, reserved names rejected, < 300 words rejected. Tested with a throw-away article (published, in sitemap, canonical correct) and a 2-word one (refused); both removed.

**Hosting directory (Arabic only):** 20 companies in `hosting-companies.json` and `/hosting-companies/`. Profile pages exist only for the 4 with existing Arabic articles (Hostinger, Bluehost, HostGator, GoDaddy); the other 16 show "قريبًا" with no page. No prices, ratings, coupon codes or affiliate claims were added (`affiliate_program: "unknown"`).
**English stays at 3 providers** (your later instruction overrides §7 of the brief). Existing English comparison pages that name other brands were left untouched.

## 2. English audit
| Item | Result |
|---|---|
| HTML files found / present under `/en/` | 166 / 166 (165 pages + 404), missing 0 |
| Images | 156 / 156, identical file set (shared at `/images/`) |
| External links | 14 before / 14 after |
| Broken internal links, missing assets | 0 / 0 (every `href/src/action` checked) |
| In `sitemap-en.xml` | 23 (real pages only). Noindex: 142 (140 placeholders + author, contact, coupons, search …) |
| Changes to pages | internal links/canonicals/OG/JSON-LD → `/en/`; language switcher added; `search.js` now loads `/en/search-index.json`; English `WebSite` gets its own @id; `Organization` @id shared with Arabic (one entity) |
| English 404 | kept at `/en/404.html`; Pages only uses the root `404.html` (Arabic) |

## 3. Technical SEO audit (local)
- **Canonical:** 219 of 219 indexable/real pages self-referencing; legacy pages canonicalise to their `.html` URL.
- **lang/dir:** Arabic `ar`/`rtl`, English `en`/`ltr` on every page.
- **hreflang:** only the home pair (`/` ↔ `/en/`, + x-default → Arabic), reciprocal. No article pairs are claimed. Candidate: `hostinger-review.html` ↔ `/en/reviews/hostinger/` (listed, inactive, because the English review is a short overview). Switcher falls back to the other homepage elsewhere.
- **Sitemaps:** index + ar (52) + en (23); no duplicates, no noindex URLs, no planned URLs; all indexable pages are listed. **robots.txt:** allows all, references `sitemap.xml`, doesn't block `/en/`; it disallows only the internal `/_legacy/` mirror.
- **JSON-LD:** 0 invalid; no Review/AggregateRating anywhere; no conflicting `@id`; FAQPage appears only on the 9 English pages that already had visible FAQs (kept). Arabic: Organization+WebSite (home), Article, BreadcrumbList. Parsing was checked, **not** Google's Rich Results test.
- **Local HTTP:** 76 sitemap URLs → 76×200; unknown path → 404 (python static server, not Cloudflare).
- **Mobile:** 76 sitemap pages rendered in headless Chromium at 390 px: 0 with horizontal overflow; 0 images without dimensions; every table in a scroll container. (Blogger images show broken in the sandbox only because the CDN is blocked.)
- Duplicate titles/descriptions among indexable pages: 0.

## 4. Decisions I made that you may want to reverse
- Added `rel="sponsored nofollow noopener"` to the 21 Hostinger referral links (hrefs untouched); other external links get `noopener`.
- Arabic articles with a hosting-company link show a short disclosure box (wording "may earn a commission").
- `/affiliate-disclosure/` (Arabic) is my translation of your English disclosure.
- "حل المشكلات" category = 4 posts picked by slug/title (`fix-…`, `…slow-website-fix…`, `…ssl-activation…`).
- Asset cache changed from 1-year `immutable` to 1 day (the CSS file names are not versioned).
- If the English site was already live/indexed at root paths, add 301s from old root URLs to `/en/…` – I did not, because they would collide with Arabic `/about/`, `/contact/` etc.
- Content consistency: the English methodology says untested providers are labelled; several Arabic posts speak as hands-on testers. Preserved as written.

## 5. Not verified
Production HTTP status/redirect behaviour, Search Console indexing, Google Rich Results validation, real-device rendering, Blogger image availability over time.
