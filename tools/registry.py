#!/usr/bin/env python3
"""Editorial backlog for NEW Arabic articles.  Planned entries are never built and never reach the sitemap.

  python3 tools/registry.py import titles.csv     # columns: title,slug,category[,company,primary_topic]  (UTF-8)
  python3 tools/registry.py check                 # duplicate titles / slug conflicts against registry, legacy posts and reserved names
  python3 tools/registry.py list [status]

To publish: write content-ar/articles/<slug>.md (front matter status: published) and run build.py.
"""
import sys, re, json, csv, difflib
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "content-registry" / "arabic-planned-articles.json"
NS = {"a": "http://www.w3.org/2005/Atom", "b": "http://schemas.google.com/blogger/2018"}
CATS = {"best-hosting", "company-reviews", "comparisons", "coupons", "tutorials", "wordpress-themes", "wordpress-plugins", "troubleshooting"}
RESERVED = {"about", "contact", "affiliate-disclosure", "privacy-policy", "terms", "search", "category", "hosting-companies", "en", "assets", "images",
            "content-registry", "_legacy", "2026", "sitemap", "sitemap-ar", "sitemap-en", "robots", "404"}
norm = lambda s: re.sub(r"[\W_]+", " ", s.lower()).strip()

def legacy():
    out = []
    for e in ET.parse(ROOT / "ar-source" / "feed.atom").getroot().findall("a:entry", NS):
        if e.find("b:status", NS).text == "LIVE" and e.find("b:type", NS).text == "POST":
            out.append((e.find("a:title", NS).text, Path(e.find("b:filename", NS).text).stem.lower()))
    return out

def problems(arts):
    P, L = [], legacy()
    seen_slug, seen_title = {}, []
    for a in arts:
        s = a["slug"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", s): P.append(f"{s}: slug must be lowercase latin letters/digits/hyphens (no year, month or .html)")
        if s in RESERVED: P.append(f"{s}: reserved name")
        if s in seen_slug: P.append(f"{s}: duplicate slug (also '{seen_slug[s]}')")
        if any(s == ls for _, ls in L): P.append(f"{s}: same as the slug of an existing legacy post (different URL, but confusing - rename)")
        if a["category"] not in CATS: P.append(f"{s}: unknown category {a['category']}")
        seen_slug[s] = a["title"]
        for t in [x for x, _ in L] + seen_title:
            r = difflib.SequenceMatcher(None, norm(a["title"]), norm(t)).ratio()
            if r >= 0.8 and a["title"] != t: P.append(f"{s}: title overlaps ({r:.2f}) with '{t[:60]}'")
        seen_title.append(a["title"])
    return P

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    reg = json.loads(REG.read_text(encoding="utf-8"))
    if cmd == "import":
        rows = list(csv.DictReader(open(sys.argv[2], encoding="utf-8-sig")))
        n0 = len(reg["articles"])
        for r in rows:
            reg["articles"].append(dict(id=len(reg["articles"]) + 1, title=r["title"].strip(), slug=r["slug"].strip().strip("/"), category=r["category"].strip(),
                                        company=(r.get("company") or "").strip(), section=(r.get("section") or "").strip(), primary_topic=(r.get("primary_topic") or "").strip(), status="planned", notes=""))
        P = problems(reg["articles"])
        if P: print("NOT SAVED - fix these first:"); [print(" -", p) for p in P]; sys.exit(1)
        REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8"); print(f"imported {len(reg['articles']) - n0} titles")
    elif cmd == "check":
        P = problems(reg["articles"]); print(f"{len(reg['articles'])} planned entries, {len(P)} problems"); [print(" -", p) for p in P]; sys.exit(1 if P else 0)
    elif cmd == "list":
        for a in reg["articles"]:
            if len(sys.argv) < 3 or a["status"] == sys.argv[2]: print(a["id"], a["status"], a["slug"], "|", a["title"])
main()
