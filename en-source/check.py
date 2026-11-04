#!/usr/bin/env python3
"""Post-build checks: internal links, images, JSON-LD, unique titles/descriptions, single H1, canonical."""
import os, re, json, sys, glob
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
errs, titles, descs = [], {}, {}
files = glob.glob(D + "/**/*.html", recursive=True)
def exists(u):
    u = u.split("#")[0].split("?")[0]
    if not u or u.startswith(("http", "mailto:", "data:")): return True
    p = D + u
    return os.path.isfile(p) or os.path.isfile(p.rstrip("/") + "/index.html") or os.path.isfile(p + "/index.html")
for f in files:
    t = open(f, encoding="utf-8").read(); rel = f[len(D):]
    for u in re.findall(r'(?:href|src)=["\']?(/[^"\' >]*)', t):
        if not exists(u): errs.append(f"{rel}: broken {u}")
    for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S):
        try: json.loads(j)
        except Exception as e: errs.append(f"{rel}: bad JSON-LD {e}")
    if rel == "/404.html": continue
    if t.count("<h1") != 1 and "/search/" not in rel: errs.append(f"{rel}: h1 count {t.count('<h1')}")
    m = re.search(r"<title>(.*?)</title>", t); d = re.search(r'name="description" content="(.*?)"', t)
    if not m or not d: errs.append(f"{rel}: missing title/desc"); continue
    titles.setdefault(m.group(1), []).append(rel); descs.setdefault(d.group(1), []).append(rel)
    if 'rel="canonical"' not in t: errs.append(f"{rel}: no canonical")
    if 'lang="en" dir="ltr"' not in t: errs.append(f"{rel}: lang/dir")
    for a in re.findall(r'<a [^>]*href="(https?://(?!primetechhosting)[^"]+)"[^>]*>', t):
        pass
    for tag in re.findall(r'<a [^>]*rel="sponsored[^>]*>', t):
        if 'nofollow' not in tag or 'noopener' not in tag: errs.append(f"{rel}: bad affiliate rel")
for k, v in titles.items():
    if len(v) > 1: errs.append(f"duplicate title {k}: {v[:3]}")
for k, v in descs.items():
    if len(v) > 1: errs.append(f"duplicate description: {v[:3]}")
for need in ("robots.txt", "sitemap.xml", "search-index.json", "404.html"):
    if not os.path.isfile(f"{D}/{need}"): errs.append(f"missing {need}")
print(f"html files: {len(files)} | problems: {len(errs)}")
for e in errs[:40]: print(" -", e)
sys.exit(1 if errs else 0)
