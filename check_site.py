#!/usr/bin/env python3
"""Validate ./dist.  Writes validation-report.json.  Everything here is a LOCAL check:
file-system checks plus real HTTP GETs against a throw-away python static server (NOT Cloudflare)."""
import re, os, sys, json, threading, http.server, socketserver, functools, urllib.request, urllib.error, csv
from pathlib import Path
from collections import Counter, defaultdict
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
D = ROOT / "dist"
BASE = "https://primetechhosting.com"
NS = {"a": "http://www.w3.org/2005/Atom", "b": "http://schemas.google.com/blogger/2018"}
R = {"problems": []}
def prob(m): R["problems"].append(m)

files = sorted(D.rglob("*.html"))
def url_of(f):
    rel = "/" + f.relative_to(D).as_posix()
    return rel[:-len("index.html")] if rel.endswith("/index.html") else rel
pages = {}
for f in files:
    u = url_of(f)
    t = f.read_text(encoding="utf-8")
    pages[u] = dict(file=f, t=t,
                    canon=(re.search(r'<link rel="canonical" href="([^"]+)"', t) or [None, None])[1],
                    robots=(re.search(r'<meta name="robots" content="([^"]+)"', t) or [None, ""])[1],
                    lang=((re.search(r'<html lang="([^"]+)" dir="([^"]+)"', t) or re.match(r"()()", "")).groups()))
legacy_mirror = {u for u in pages if u.startswith("/_legacy/")}
public = {u: p for u, p in pages.items() if u not in legacy_mirror}
R["html_files_total"] = len(pages); R["html_files_public"] = len(public); R["legacy_mirror_copies"] = len(legacy_mirror)
R["ar_pages"] = sum(1 for u in public if not u.startswith("/en/")); R["en_pages"] = sum(1 for u in public if u.startswith("/en/"))

# ---- legacy URL preservation -----------------------------------------------------------
feed = ET.parse(ROOT / "ar-source" / "feed.atom").getroot().findall("a:entry", NS)
live = [e.find("b:filename", NS).text for e in feed if e.find("b:status", NS).text == "LIVE" and e.find("b:type", NS).text == "POST"]
redir = (D / "_redirects").read_text(encoding="utf-8")
exact = [p for p in live if (D / p.lstrip("/")).is_file() and public.get(p, {}).get("canon") == BASE + p]
R["legacy"] = dict(live_posts_in_xml=len(live), exact_path_file_exists_with_matching_canonical=len(exact),
                   rewrite_rules_in__redirects=sum(1 for p in live if re.search(r"^" + re.escape(p) + r"\s+/_legacy" + re.escape(p[:-5]) + r"/\s+200$", redir, re.M)),
                   case_collisions=len(live) - len({p.lower() for p in live}))
for p in live:
    if p not in exact: prob(f"legacy path not preserved: {p}")

# ---- language / dir / canonical / h1 ----------------------------------------------------
for u, p in public.items():
    en = u.startswith("/en/")
    want = ("en", "ltr") if en else ("ar", "rtl")
    if tuple(p["lang"]) != want: prob(f"{u}: lang/dir {p['lang']} expected {want}")
    if u == "/404.html" or u == "/en/404.html": continue
    if p["canon"] != BASE + u: prob(f"{u}: canonical {p['canon']} != self")
    if p["t"].count("<h1") != 1 and "/search/" not in u: prob(f"{u}: h1 count {p['t'].count('<h1')}")
R["canonical_self_referencing"] = sum(1 for u, p in public.items() if p["canon"] == BASE + u)

# ---- hreflang reciprocity ---------------------------------------------------------------
hl_ok = hl_pages = 0
for u, p in public.items():
    alts = dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', p["t"]))
    if not alts: continue
    hl_pages += 1
    ok = alts.get("ar") and alts.get("en") and alts.get("x-default") and (BASE + u) in (alts.get("ar"), alts.get("en"))
    for lang in ("ar", "en"):
        tu = alts[lang].replace(BASE, "")
        back = dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', public.get(tu, {}).get("t", "")))
        if back.get(lang) != alts[lang] or back.get("en" if lang == "ar" else "ar") is None: ok = False
    hl_ok += bool(ok)
    if not ok: prob(f"{u}: hreflang not reciprocal")
R["hreflang"] = dict(pages_with_hreflang=hl_pages, reciprocal_ok=hl_ok)

# ---- sitemaps -----------------------------------------------------------------------------
def locs(name):
    root = ET.parse(D / name).getroot()
    return [e.text for e in root.iter() if e.tag.endswith("}loc")]
idx = locs("sitemap.xml"); sm_ar = locs("sitemap-ar.xml"); sm_en = locs("sitemap-en.xml")
R["sitemaps"] = dict(index_entries=idx, ar_urls=len(sm_ar), en_urls=len(sm_en), duplicates=len(sm_ar + sm_en) - len(set(sm_ar + sm_en)))
for lang, lst in (("ar", sm_ar), ("en", sm_en)):
    for l in lst:
        u = l.replace(BASE, "")
        p = public.get(u) or (pages.get(u))
        if p is None and (D / u.lstrip("/")).is_file(): p = pages.get(u)
        if p is None: prob(f"sitemap-{lang}: {l} has no file"); continue
        if "noindex" in p["robots"]: prob(f"sitemap-{lang}: {l} is noindex")
        if p["canon"] != l: prob(f"sitemap-{lang}: {l} canonical mismatch")
        if (lang == "en") != u.startswith("/en/"): prob(f"sitemap-{lang}: {l} in wrong sitemap")
indexable = {u for u, p in public.items() if "noindex" not in p["robots"] and u not in ("/404.html", "/en/404.html")}
R["sitemaps"]["indexable_pages_missing_from_sitemaps"] = sorted(u for u in indexable if BASE + u not in set(sm_ar + sm_en))
R["sitemaps"]["noindex_pages"] = sum(1 for u, p in public.items() if "noindex" in p["robots"])
if R["sitemaps"]["indexable_pages_missing_from_sitemaps"]: prob("indexable pages missing from sitemap")
robots = (D / "robots.txt").read_text(encoding="utf-8")
R["robots"] = dict(text=robots, references_index=f"{BASE}/sitemap.xml" in robots, blocks_en=bool(re.search(r"Disallow:\s*/en", robots)))
# planned registry must never reach the sitemap
planned = json.loads((ROOT / "content-registry" / "arabic-planned-articles.json").read_text(encoding="utf-8"))["articles"]
R["planned_registry"] = dict(entries=len(planned), in_sitemap=sum(1 for a in planned if f"{BASE}/{a.get('slug','')}/" in sm_ar and a.get("status") != "published"))

# ---- internal links / assets / images ---------------------------------------------------------
def resolves(u):
    u = u.split("#")[0].split("?")[0]
    if not u: return True
    p = D / u.lstrip("/")
    if u.endswith("/"): return (p / "index.html").is_file()
    return p.is_file() or (p / "index.html").is_file()
broken = defaultdict(list); missing_assets = []
for u, p in public.items():
    for m in re.finditer(r'(?:href|src|action)="(/[^"/][^"]*|/)"', p["t"]):
        link = m.group(1)
        if "'" in link or "+" in link: continue          # URL fragments built by inline JS, not real hrefs
        if not resolves(link):
            (missing_assets if link.startswith(("/assets/", "/images/")) else broken[u]).append(link)
R["internal_links"] = dict(broken_total=sum(len(v) for v in broken.values()), missing_assets=len(missing_assets), examples=[(k, v[:3]) for k, v in list(broken.items())[:8]])
for k, v in broken.items(): prob(f"{k}: broken links {v[:3]}")
imgs = no_dim = 0
for u, p in public.items():
    for tag in re.findall(r"<img [^>]*>", p["t"]):
        imgs += 1
        if "width=" not in tag or "height=" not in tag: no_dim += 1
R["images"] = dict(img_tags=imgs, without_width_or_height=no_dim)

# ---- JSON-LD ------------------------------------------------------------------------------------
bad = 0; ids = defaultdict(set); types = Counter()
for u, p in public.items():
    for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', p["t"], re.S):
        try: d = json.loads(j)
        except Exception as e: bad += 1; prob(f"{u}: invalid JSON-LD {e}"); continue
        types[d.get("@type")] += 1
        if "@id" in d: ids[d["@id"]].add(json.dumps({k: v for k, v in d.items() if k in ("@type", "url")}, sort_keys=True))
        if d.get("@type") in ("Review", "AggregateRating") or "aggregateRating" in d: prob(f"{u}: rating/review schema present - verify it is genuine")
R["jsonld"] = dict(invalid=bad, types=dict(types), ids_with_conflicting_definitions=[i for i, v in ids.items() if len(v) > 1])
for i in R["jsonld"]["ids_with_conflicting_definitions"]: prob(f"JSON-LD @id {i} defined inconsistently")

# ---- Arabic content integrity -------------------------------------------------------------------
ref = [m for e in feed if e.find("b:status", NS).text == "LIVE" for m in re.findall(r'href=&quot;|href="([^"]*REFERRALCODE[^"]*)"', (e.find("a:content", NS).text or ""))]
import html as _h
src_ref = sum(len(re.findall(r'href="(https://www\.hostinger\.com/eg\?REFERRALCODE=[A-Z0-9]+)"', _h.unescape(e.find("a:content", NS).text or ""))) for e in feed if e.find("b:status", NS).text == "LIVE")
dist_ref = sum(len(re.findall(r'href="(https://www\.hostinger\.com/eg\?REFERRALCODE=[A-Z0-9]+)"', pages[p]["t"])) for p in live if p in pages)
R["arabic_affiliate_links"] = dict(referral_links_in_xml=src_ref, referral_links_in_dist=dist_ref)
if src_ref != dist_ref: prob("referral link count differs between XML and dist")
R["arabic_images"] = dict(remote_blogger_images=sum(len(re.findall(r'<img [^>]*src="https://blogger\.googleusercontent\.com', pages[p]["t"])) for p in live),
                          local_images=sum(len(re.findall(r'<img [^>]*src="/images/ar/[^"]+\.jpg"', pages[p]["t"])) for p in live),
                          note="Blogger images were replaced by local JPG placeholders in images-ar/ (see IMAGE-REPLACEMENT-GUIDE.html)")

# ---- English integrity ----------------------------------------------------------------------------
orig = ROOT.parent / "work" / "dist_original"
if orig.exists():
    oh = sorted(orig.rglob("*.html"))
    ext = lambda t: sorted(re.findall(r'href="(https?://(?!primetechhosting\.com)[^"]+)"', t))
    o_ext = sum(len(ext(f.read_text(encoding="utf-8"))) for f in oh)
    n_ext = sum(len(ext(pages["/en" + (("/" + f.relative_to(orig).as_posix())[:-10] if f.name == "index.html" else "/" + f.relative_to(orig).as_posix())]["t"])) for f in oh)
    miss = [f.relative_to(orig).as_posix() for f in oh if "/en" + (("/" + f.relative_to(orig).as_posix())[:-10] if f.name == "index.html" else "/" + f.relative_to(orig).as_posix()) not in pages]
    o_img = sorted(p.name for p in (orig / "images").glob("*")); n_img = sorted(p.name for p in (D / "images").glob("*"))
    R["english"] = dict(original_html_files=len(oh), present_under_en=len(oh) - len(miss), missing=miss, external_links_original=o_ext, external_links_now=n_ext,
                        images_original=len(o_img), images_now=len(n_img), images_identical=o_img == n_img,
                        affiliate_tracking_params_found_in_original=sum(1 for f in oh if re.search(r'href="https?://[^"]+\?(?:ref|aff|utm|REFERRAL)', f.read_text(encoding="utf-8"), re.I)))
    if miss: prob(f"English pages missing: {miss[:5]}")
    if o_ext != n_ext: prob("English external link count changed")

# ---- local HTTP test (python static server, NOT Cloudflare) -----------------------------------------
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(H, directory=str(D)))
srv.daemon_threads = True
port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
def status(path):
    try:
        class NoRedir(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k): return None
        op = urllib.request.build_opener(NoRedir)
        return op.open(f"http://127.0.0.1:{port}{urllib.parse.quote(path)}", timeout=10).status
    except urllib.error.HTTPError as e: return e.code
import urllib.parse
codes = Counter(); fails = []
for l in sm_ar + sm_en:
    c = status(l.replace(BASE, "")); codes[c] += 1
    if c != 200: fails.append((l, c))
codes404 = status("/this-page-does-not-exist/")
R["local_http_test"] = dict(server="python http.server on localhost (static file semantics only - not Cloudflare Pages)", sitemap_urls_tested=len(sm_ar + sm_en),
                            status_counts=dict(codes), non_200=fails[:10], unknown_path_status=codes404)
srv.shutdown()
if fails: prob(f"{len(fails)} sitemap URLs not 200 locally")

# ---- static mobile checks (no browser available) ----------------------------------------------------------
R["mobile_static_checks"] = dict(pages_without_viewport_meta=[u for u, p in public.items() if 'name="viewport"' not in p["t"]],
                                 note="static markup checks only (viewport meta, tables in scroll containers); no device rendering was performed")
tw_missing = [u for u, p in public.items() if re.search(r"<table", p["t"]) and 'class="tw"' not in p["t"]]
R["mobile_static_checks"]["pages_with_unwrapped_tables"] = tw_missing
if tw_missing: prob(f"unwrapped tables: {tw_missing[:3]}")

# ---- duplicates ------------------------------------------------------------------------------------------------
tt = defaultdict(list)
for u, p in public.items():
    if "noindex" in p["robots"]: continue
    m = re.search(r"<title>(.*?)</title>", p["t"]); d = re.search(r'name="description" content="(.*?)"', p["t"])
    tt[("t", m.group(1) if m else "")].append(u); tt[("d", d.group(1) if d else "")].append(u)
dups = {f"{k[0]}:{k[1][:50]}": v for k, v in tt.items() if len(v) > 1 and k[1]}
R["duplicate_titles_or_descriptions_among_indexable_pages"] = dups
for k, v in dups.items(): prob(f"duplicate {k}: {v[:3]}")

(ROOT / "validation-report.json").write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in R.items() if k != "robots"}, ensure_ascii=False, indent=1)[:6000])
print("\nPROBLEMS:", len(R["problems"]))
for p in R["problems"][:40]: print(" -", p)
sys.exit(1 if R["problems"] else 0)
