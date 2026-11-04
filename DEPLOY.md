# Deploying Prime Tech Hosting (one Cloudflare Pages project)

## 1. Build (on your computer)
```
pip install -r requirements.txt
python3 build.py          # writes ./dist
python3 check_site.py     # must end with "PROBLEMS: 0"
```
`dist/` is the whole site: Arabic at `/`, English at `/en/`, one `_redirects`, `_headers`, `robots.txt`, three sitemaps.

## 2. Upload
Dashboard → Workers & Pages → Create → Pages → **Upload assets** → drag the `dist` folder
(or `npx wrangler pages deploy dist --project-name <your-project>`). Attach the custom domain `primetechhosting.com`.
Do not create a second project and do not use `en.primetechhosting.com`.

## 3. Domain details
- Canonical host is `https://primetechhosting.com` (no www). Your old Blogger URLs used `www.`; add ONE host-level redirect
  `www.primetechhosting.com/*` → `https://primetechhosting.com/$1` (Cloudflare → Rules → Redirect Rules, 301).
- Search Console: add the domain property, submit `https://primetechhosting.com/sitemap.xml` (index of the Arabic + English sitemaps).

## 4. MUST-DO tests right after the first deploy (I could not run these - they need the live site)
Legacy Blogger URLs must answer **200 at the same URL with no redirect**. Cloudflare Pages normally redirects `*.html` to the extension-less
URL; `_redirects` contains 35 status-200 rewrites to stop that. Verify:
```
curl -sI https://primetechhosting.com/2026/04/hostinger-review.html | head -3        # expect HTTP/2 200, no Location header
curl -sI https://primetechhosting.com/2026/04/Hostinger-discount-code-2026.html | head -3   # case-sensitive slug
curl -sI https://primetechhosting.com/en/reviews/hostinger/ | head -3
curl -sI https://primetechhosting.com/does-not-exist/ | head -3                      # expect 404 (Arabic 404 page)
```
If a legacy URL answers 308/301 instead of 200, tell me: the fallback is a tiny Pages Function that serves the `/_legacy/...` copy at the original path.

## 5. Adding things later
| Task | How |
|---|---|
| Load more planned Arabic titles | CSV `title,slug,category,company,section,primary_topic` → `python3 tools/registry.py import titles.csv` (rejects duplicate/overlapping titles and bad slugs) |
| Publish a new Arabic article | copy `content-ar/articles/_TEMPLATE.md.example` → `<slug>.md`, set `status: published` and `registry_id: <id of its draft title>` (the draft card + `/planned-NNN/` page disappear by themselves), then `python3 build.py`. URL = `/<slug>/`, sitemap entry added automatically. Under 300 words is refused. |
| Add contact email | `content-ar/site-ar.json` → `contact_email` (until then `/contact/` is noindex and not in the sitemap) |
| Declare a real Arabic<->English equivalent | `content-registry/language-pairs.json` → `active` (adds hreflang + makes the switcher point at that page) |
| Add a hosting company (Arabic) | `content-registry/hosting-companies.json`; its profile page appears once an Arabic article URL matches `article_slug_pattern` |
| Finish an English article | see `en-source/README.md` (content/guides, content/articles ...), then `python3 build.py` |
| Arabic images | All Blogger images were replaced by JPG placeholders in `images-ar/<article>/`. Open `IMAGE-REPLACEMENT-GUIDE.html`, rename your JPG to the placeholder's name, overwrite it, run `build.py`. New article: `python3 tools/imgs.py new <slug> "<title>" 5` |
| Draft titles / sections | `content-registry/arabic-planned-articles.json` (`section`, `category`) and `content-registry/sections.json` (section names + order). Drafts are visible, noindex and never in `sitemap-ar.xml` |
