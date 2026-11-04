# PrimeTech Hosting – Batch 1

Build:   python3 gen.py      (creates dist/ and image-map.csv)
Check:   python3 check.py    (links, images, JSON-LD, titles, affiliate rel)
Upload:  the dist/ folder to Cloudflare Pages.

## Add an article (content/guides/<slug>.md, or content/comparisons, content/best)
---
title: ...
description: ...
published: YYYY-MM-DD      (real date)
updated: YYYY-MM-DD        (real date)
image_text: Text printed on the article image
hosts: hostinger, bluehost   (only for content/best, creates ItemList)
---
# H1
Affiliate link: [Hostinger](host:hostinger)   -> uses url from data/hosts.json, adds rel="sponsored nofollow noopener"
## Frequently Asked Questions
### Question?
Answer.   (creates FAQPage schema automatically)

## Replace an image
Put your jpg with the SAME file name (see image-map.csv) inside images_custom/ and rebuild.

## Publish a host review
Edit data/hosts.json (fill fields, last_verified, status "published", hands_on_tested true only if you tested it).
Optional long review text: content/reviews/<slug>.md
Pages stay noindex until published / until real content exists.

## Fill before launch
data/site.json: contact_email, author_name, author_bio, ga_id, gsc_verification
