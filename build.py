#!/usr/bin/env python3
"""
Prime Tech Hosting – unified bilingual build (Arabic at /, English at /en/).

    python3 build.py            -> writes ./dist  (deploy this folder to Cloudflare Pages)
    python3 check_site.py       -> validates ./dist (links, canonicals, hreflang, sitemaps, JSON-LD ...)

Inputs
  en-source/                the original English project (gen.py + content + data).  Built, then moved under /en/
  ar-source/feed.atom       Blogger XML backup  (source of truth for legacy Arabic posts)
  content-ar/articles/*.md  NEW Arabic articles (front matter status: published -> built; anything else is ignored)
  content-registry/*.json   editorial backlog, hosting-company directory, language pairs
"""
import re, os, sys, json, html, shutil, subprocess, datetime, csv
import xml.etree.ElementTree as ET
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
try:
    import markdown as mdlib
except ImportError:
    mdlib = None
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from imgs import make_placeholder          # placeholder JPG generator (Arabic text)
OUT = ROOT / "dist"
EN_SRC = ROOT / "en-source"
BASE = "https://primetechhosting.com"
NAME_AR = "نبض الاستضافة"
NAME_EN = "PrimeTech Hosting"
MIN_WORDS_NEW_ARTICLE = 300          # guard: a new Arabic article below this is refused (no thin pages)
TODAY = datetime.date.today().isoformat()
NS = {"a": "http://www.w3.org/2005/Atom", "b": "http://schemas.google.com/blogger/2018"}
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

E = html.escape
REPORT = {"warnings": [], "errors": []}
def warn(m): REPORT["warnings"].append(m); print("WARN:", m)
def die(m): REPORT["errors"].append(m); print("ERROR:", m); raise SystemExit(1)

def load_json(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))

# ------------------------------------------------------------------ output helpers
WRITTEN = {}          # url -> dict(file, index, lastmod, lang, kind)
def write_file(rel, content, binary=False):
    p = OUT / rel.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    if binary: p.write_bytes(content)
    else: p.write_text(content, encoding="utf-8")

def fmt_date_ar(iso):
    y, m, d = iso[:10].split("-")
    return f"{int(d)} {AR_MONTHS[int(m)-1]} {y}"

# ====================================================================== ENGLISH  (/en/)
def build_english():
    print("== English: building original project and moving it under /en/")
    subprocess.run([sys.executable, "gen.py"], cwd=EN_SRC, check=True, stdout=subprocess.DEVNULL)
    src = EN_SRC / "dist"
    pairs = load_json("content-registry/language-pairs.json")["active"]
    en_to_ar = {p["en"]: p["ar"] for p in pairs}
    ar_to_en = {p["ar"]: p["en"] for p in pairs}

    # original lastmod values (so the English sitemap keeps real dates)
    lastmod = {}
    sm = (src / "sitemap.xml").read_text(encoding="utf-8")
    for loc, lm in re.findall(r"<loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?", sm):
        lastmod[loc.replace(BASE, "")] = lm or None

    # shared assets / images stay at the root (no duplication; absolute paths keep working from /en/...)
    shutil.copytree(src / "assets", OUT / "assets", dirs_exist_ok=True)
    shutil.copytree(src / "images", OUT / "images", dirs_exist_ok=True)
    js = (OUT / "assets" / "search.js").read_text(encoding="utf-8")
    assert "fetch('/search-index.json')" in js
    (OUT / "assets" / "search.js").write_text(js.replace("fetch('/search-index.json')", "fetch('/en/search-index.json')"), encoding="utf-8")

    idx = json.loads((src / "search-index.json").read_text(encoding="utf-8"))
    for r in idx: r["u"] = "/en" + r["u"]
    write_file("/en/search-index.json", json.dumps(idx, ensure_ascii=False))

    n = 0
    for f in sorted(src.rglob("*.html")):
        rel = "/" + f.relative_to(src).as_posix()                    # /hostinger/x/index.html
        url = rel[:-len("index.html")] if rel.endswith("/index.html") else rel
        t = f.read_text(encoding="utf-8")
        # 1) internal links / form actions -> /en/ (assets+images stay at root)
        t = re.sub(r'(href|action)="(/(?!assets/|images/|en/)[^"]*)"', lambda m: f'{m.group(1)}="/en{m.group(2)}"', t)
        # 2) absolute URLs (canonical, og:url, JSON-LD) -> /en/ ; images/assets and #fragments (shared @id) untouched
        t = re.sub(r"https://primetechhosting\.com/(?!images/|assets/|en/|#)", BASE + "/en/", t)
        t = t.replace(BASE + "/#website", BASE + "/en/#website")
        t = t.replace(f'"@id": "{BASE}/#org", "name": "PrimeTech Hosting", "url": "{BASE}/en/"', f'"@id": "{BASE}/#org", "name": "PrimeTech Hosting", "url": "{BASE}/"')      # English WebSite entity gets its own @id; Organization @id is shared
        if url == "/search/": t = t.replace('content="index,follow,max-image-preview:large"', 'content="noindex,follow"')   # internal search results: keep out of the index
        # 3) language switcher + hreflang (only for genuine pairs)
        en_url = "/en" + url
        ar_target = en_to_ar.get(en_url, "/")
        switch = f'<span class="sp"></span><a class="l" href="{ar_target}" hreflang="ar" lang="ar" title="النسخة العربية">العربية</a>'
        switch = switch.replace('<span class="sp"></span>', '').replace('class="l"', 'class="l langsw"')
        t, nsub = re.subn(r'(<a class="logo" href="[^"]*">.*?</a>)', lambda m: m.group(1) + switch, t, count=1)
        assert nsub == 1, rel
        if en_url in en_to_ar and 'noindex' not in t:
            alt = (f'<link rel="alternate" hreflang="en" href="{BASE}{en_url}">'
                   f'<link rel="alternate" hreflang="ar" href="{BASE}{en_to_ar[en_url]}">'
                   f'<link rel="alternate" hreflang="x-default" href="{BASE}{en_to_ar[en_url]}">')
            t = t.replace("</head>", alt + "</head>", 1)
        out_rel = "/en" + rel
        write_file(out_rel, t)
        n += 1
        indexable = 'content="index,follow' in t
        WRITTEN[en_url] = dict(file=out_rel, index=indexable, lastmod=lastmod.get(url), lang="en",
                               kind="404" if url == "/404.html" else "page")
    print(f"   English html files moved: {n}")
    return n, ar_to_en, en_to_ar

# ====================================================================== ARABIC chrome
MERCHANT_HOSTS = re.compile(r"(hostinger|bluehost|hostgator|namecheap|siteground|dreamhost|hosting\.com|a2hosting|ionos|inmotionhosting|godaddy|greengeeks|cloudways|wpengine|kinsta|liquidweb|scalahosting|fastcomet|hostarmada|interserver|knownhost|ipage|rocket\.net)\.", re.I)

NAV_AR = [("/category/best-hosting/", "أفضل استضافة"), ("/category/company-reviews/", "مراجعات"), ("/category/comparisons/", "مقارنات"),
          ("/category/coupons/", "كوبونات"), ("/category/tutorials/", "شروحات"), ("/hosting-companies/", "شركات الاستضافة")]

def nav_ar(alt_en):
    links = "".join(f'<a class="l" href="{u}">{t}</a>' for u, t in NAV_AR)
    return (f'<header class="top"><div class="wrap nav"><a class="logo" href="/">نبض <span>الاستضافة</span></a>'
            f'<a class="l langsw" href="{alt_en}" hreflang="en" lang="en" title="English version">English</a>{links}'
            f'<span class="sp"></span><a class="l" href="/search/">بحث</a></div></header>')

FOOTER_AR = ('<footer><div class="wrap"><p><strong>نبض الاستضافة</strong>: مراجعات ومقارنات وشروحات لاستضافة المواقع باللغة العربية. '
             'قد نحصل على عمولة من بعض الروابط في هذا الموقع، راجع <a href="/affiliate-disclosure/" style="margin:0">إفصاح الشراكة</a>.</p>'
             '<p><a href="/about/">من نحن</a><a href="/contact/">اتصل بنا</a><a href="/affiliate-disclosure/">إفصاح الشراكة</a>'
             '<a href="/sitemap/">خريطة الموقع</a><a href="/privacy-policy/">سياسة الخصوصية</a><a href="/terms/">الشروط والأحكام</a></p></div></footer>')

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%230b2545'/%3E"
           "%3Ctext x='32' y='43' font-size='32' font-weight='700' text-anchor='middle' fill='%2313a89e' font-family='Arial'%3EP%3C/text%3E%3C/svg%3E")

ORG_ID = BASE + "/#org"
def org_schema():
    return {"@context": "https://schema.org", "@type": "Organization", "@id": ORG_ID, "name": NAME_EN,
            "url": BASE + "/", "logo": {"@type": "ImageObject", "url": BASE + "/images/logo.jpg"}}

def crumb_schema(crumbs):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": BASE + u} for i, (n, u) in enumerate(crumbs)]}

def ar_page(url, title, desc, body, *, schemas=None, index=True, crumbs=None, alt_en=None, hreflang_pair=False,
            og_image=None, og_type="website", kind="page", lastmod=None, search=False):
    """Render a full Arabic page, write it, and register it."""
    schemas = list(schemas or [])
    if crumbs and len(crumbs) > 1: schemas.append(crumb_schema(crumbs))
    full_title = title if NAME_AR in title else f"{title} | {NAME_AR}"
    canon = BASE + url
    robots = "index,follow,max-image-preview:large" if index else "noindex,follow"
    hl = ""
    if hreflang_pair and alt_en and index:
        hl = (f'<link rel="alternate" hreflang="ar" href="{canon}"><link rel="alternate" hreflang="en" href="{BASE}{alt_en}">'
              f'<link rel="alternate" hreflang="x-default" href="{canon}">')
    og_img = f'<meta property="og:image" content="{E(og_image)}">' if og_image else ""
    sj = "".join(f'<script type="application/ld+json">{json.dumps(s, ensure_ascii=False)}</script>' for s in schemas)
    cb = ""
    if crumbs and len(crumbs) > 1:
        cb = '<nav class="crumbs wrap" aria-label="مسار التنقل">' + " &lsaquo; ".join(
            f'<a href="{u}">{E(n)}</a>' for n, u in crumbs[:-1]) + f" &lsaquo; {E(crumbs[-1][0])}</nav>"
    page = (f'<!DOCTYPE html>\n<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{E(full_title)}</title><meta name="description" content="{E(desc)}"><meta name="robots" content="{robots}">'
            f'<link rel="canonical" href="{canon}">{hl}<link rel="stylesheet" href="/assets/style.css"><link rel="stylesheet" href="/assets/style-ar.css">'
            f'<link rel="icon" href="{FAVICON}">'
            f'<meta property="og:type" content="{og_type}"><meta property="og:site_name" content="{NAME_AR}"><meta property="og:title" content="{E(full_title)}">'
            f'<meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{canon}"><meta property="og:locale" content="ar_AR">{og_img}'
            f'<meta name="twitter:card" content="summary_large_image">{sj}</head>'
            f'<body>{nav_ar(alt_en or "/en/")}{cb}{body}{FOOTER_AR}'
            f'{"<script src=/assets/search-ar.js defer></script>" if search else ""}<script src="/assets/coupon-reveal.js" defer></script></body></html>')
    rel = url + "index.html" if url.endswith("/") else url
    write_file(rel, page)
    WRITTEN[url] = dict(file=rel, index=index, lastmod=lastmod, lang="ar", kind=kind, title=title, desc=desc)

# ====================================================================== sanitiser for Blogger HTML
BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "div", "blockquote", "pre", "hr", "figure", "details"}
KEEP = {"p", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "a", "img",
        "strong", "b", "em", "i", "br", "blockquote", "code", "pre", "hr", "figure", "figcaption", "sup", "sub", "details", "summary",
        "div", "button", "span"}
ATTRS = {"a": {"href", "title", "rel"}, "img": {"src", "alt", "width", "height", "title"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}, "ol": {"start"},
         "div": {"class", "data-code", "data-aff", "id", "hidden"}, "button": {"class", "type", "aria-label", "data-copy", "disabled"}, "span": {"class"}}
DROP = {"script", "style", "iframe", "noscript", "svg", "form", "input", "select", "textarea", "link", "meta", "object", "embed", "canvas"}

def internalise(u):
    m = re.match(r"https?://(?:www\.)?primetechhosting\.com(/[^#?]*)?(.*)$", u)
    if m: return (m.group(1) or "/") + m.group(2)
    return u

def sanitize(raw_html, stats):
    soup = BeautifulSoup(raw_html, "lxml")
    root = soup.body or soup
    # 1) UI chrome pasted from AI chat tools (icon buttons, tooltips) is removed; real content wrappers are kept.
    for t in root.find_all(True):
        if t.parent is None: continue
        if t.name in DROP or re.search(r"icon|tooltip|ripple|badge-|sources-carousel|feedback", t.name): t.decompose()
    # 2) <code-block> -> <pre><code> (language label and download button dropped, code text kept exactly)
    for cb in root.find_all("code-block"):
        code = cb.find("code") or cb.find("pre")
        txt = code.get_text() if code else cb.get_text()
        pre = soup.new_tag("pre"); c = soup.new_tag("code"); c.string = txt.rstrip("\n"); pre.append(c)
        cb.replace_with(pre)
    # 3) every other custom element (link-block, structured-text, response-element ...) is unwrapped, its children stay
    for t in root.find_all(True):
        if "-" in t.name and t.parent is not None: t.unwrap()
    for t in reversed(root.find_all(True)):
        if t.parent is None: continue
        name = t.name
        if name == "h1": t.name = name = "h2"; stats["h1_demoted"] += 1
        if name == "div":
            cls = " ".join(t.get("class", []) if isinstance(t.get("class"), list) else [t.get("class") or ""])
            if "coupon-box" in cls or "coupon-code" in cls or "coupon-info" in cls:
                allowed = ATTRS.get("div", set())
                t.attrs = {k: v for k, v in t.attrs.items() if k in allowed or k.startswith("data-")}
                continue
            if any(c.name in BLOCK for c in t.find_all(True)): t.unwrap()
            else: t.name = "p"; t.attrs = {}
            continue
        if name not in KEEP:
            t.unwrap(); continue
        allowed = ATTRS.get(name, set())
        if name == "img":
            orig_w, orig_h = t.get("data-original-width"), t.get("data-original-height")
        t.attrs = {k: v for k, v in t.attrs.items() if k in allowed}
        if name == "img" and orig_w and orig_h: t["data-ow"], t["data-oh"] = orig_w, orig_h
        if name == "a":
            href = t.get("href", "")
            if not href or href.startswith("javascript:"): t.unwrap(); continue
            href2 = internalise(href)
            if href2 != href: stats["internal_links_rooted"] += 1
            t["href"] = href2
            if href2.startswith("http"):
                host = re.sub(r"https?://([^/]+).*", r"\1", href2)
                rel = set(filter(None, (t.get("rel") if isinstance(t.get("rel"), str) else " ".join(t.get("rel") or [])).split()))
                if "blogger.googleusercontent.com" not in host:
                    rel.add("noopener")
                    if MERCHANT_HOSTS.search(host) and "?" in href2:
                        rel |= {"sponsored", "nofollow"}; stats["affiliate_links_marked"] += 1
                    stats["external_links"] += 1
                if rel: t["rel"] = " ".join(sorted(rel))
                elif "rel" in t.attrs: del t.attrs["rel"]
        if name == "img":
            if not t.get("src"): t.decompose(); continue
            if not (t.get("width") and t.get("height")):          # avoid layout shift: take size from the Blogger URL / original size
                m = re.search(r"=w(\d+)-h(\d+)", t["src"])
                if m: t["width"], t["height"] = m.group(1), m.group(2)
                elif t.get("data-ow") and t.get("data-oh"):
                    t["width"], t["height"] = t["data-ow"], t["data-oh"]
            stats["images"] += 1
            if not t.get("alt"): t["alt"] = ""
            for k in ("data-ow", "data-oh"): t.attrs.pop(k, None)
            t["decoding"] = "async"
            t["loading"] = "eager" if stats["images"] == 1 else "lazy"
    # headings that only wrap an image/figure (Blogger pattern) are not headings: unwrap them (and nested p)
    for h in root.find_all(["h2", "h3", "h4", "h5", "h6"]):
        if h.find("img") and not re.sub(r"\s+", "", h.get_text()): h.unwrap()
    for p in root.find_all("p"):
        if p.find_parent("p") is not None: p.unwrap()
    # tables scroll in their own container
    for tb in root.find_all("table"):
        w = soup.new_tag("div"); w["class"] = "tw"; tb.wrap(w); stats["tables"] += 1
    # drop empty blocks (repeat: removal can create new empties)
    for _ in range(3):
        for t in root.find_all(["p", "li", "h2", "h3", "h4", "h5", "h6", "blockquote", "a", "strong", "b", "em", "i"]):
            if not t.get_text(strip=True) and not t.find(["img", "br"]): t.decompose()
    out = "".join(str(c) for c in root.children if not (isinstance(c, NavigableString) and not str(c).strip()))
    out = re.sub(r"(<br\s*/?>\s*){2,}", "<br/>", out)
    return out.strip()

def text_of(frag):
    return re.sub(r"\s+", " ", BeautifulSoup(frag, "lxml").get_text(" ")).strip()

# ====================================================================== ARABIC content
CATS = {   # slug -> (Arabic label (== Blogger label where one exists), description)
    "best-hosting":   ("أفضل استضافة", "ترشيحات ومقارنات لأفضل شركات استضافة المواقع حسب الاستخدام والميزانية."),
    "company-reviews": ("مراجعات شركات", "مراجعات لشركات الاستضافة: المميزات والعيوب والتجربة."),
    "comparisons":    ("مقارنات", "مقارنات مباشرة بين شركات الاستضافة وخططها."),
    "coupons":        ("كوبونات خصم", "أكواد الخصم والعروض المتاحة على خدمات الاستضافة."),
    "tutorials":      ("مقالات تعليمية", "شروحات عملية لإنشاء المواقع وإدارتها وفهم أساسيات الاستضافة."),
    "wordpress-themes": ("قوالب ووردبريس", "مراجعات وإرشادات لاختيار قوالب ووردبريس وتركيبها."),
    "wordpress-plugins": ("إضافات ووردبريس", "مراجعات ومقارنات وشروحات لأهم إضافات ووردبريس: السرعة والسيو والحماية والمتاجر."),
    "troubleshooting": ("حل المشكلات", "أدلة لحل أخطاء الاستضافة والووردبريس الشائعة."),
}
LABEL_TO_CAT = {v[0]: k for k, v in CATS.items()}
TROUBLE = re.compile(r"/(fix-|.*-slow-website-fix|.*ssl-activation)", re.I)

def short(s, n=155):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"

def parse_blogger():
    root = ET.parse(ROOT / "ar-source" / "feed.atom").getroot()
    posts, pages, other = [], [], []
    for e in root.findall("a:entry", NS):
        g = lambda tag: (e.find(tag, NS).text if e.find(tag, NS) is not None else None)
        d = dict(id=g("a:id").split("post-")[-1].split("page-")[-1], type=g("b:type"), status=g("b:status"), title=(g("a:title") or "").strip(),
                 published=(g("a:published") or "")[:10], updated=(g("a:updated") or "")[:10], path=g("b:filename"),
                 meta=(g("b:metaDescription") or "").strip(), labels=[c.get("term") for c in e.findall("a:category", NS) if c.get("term")],
                 author=(e.find("a:author/a:name", NS).text if e.find("a:author/a:name", NS) is not None else None),
                 content=html.unescape(g("a:content") or ""), trashed=g("b:trashed"))
        (posts if d["type"] == "POST" else pages if d["type"] == "PAGE" else other).append(d)
    return posts, pages, other

def post_cards(items, limit=None):
    items = items[:limit] if limit else items
    return "".join(f'<a class="card" href="{p["url"]}"><h3>{E(p["title"])}</h3><p>{E(short(p["desc"], 120))}</p></a>' for p in items)

# ====================================================================== images: Blogger hot-links -> local placeholders
IMG_DIR = ROOT / "images-ar"            # <- the Arabic image folder: images-ar/<article>/<article>-NN.jpg  (replace a file, keep its name)
IMG_MANIFEST = []
_IMG_SLUGS = {}
BLOGGER_HOST = re.compile(r"googleusercontent|blogger\.com|bp\.blogspot|ggpht", re.I)
IMG_W, IMG_H = 1200, 675

def img_slug(path):
    stem = re.sub(r"[^a-z0-9]+", "-", Path(path).stem.lower()).strip("-")
    if len(stem) > 44: stem = stem[:44].rsplit("-", 1)[0] or stem[:44]
    base, n = stem, 2
    while stem in _IMG_SLUGS and _IMG_SLUGS[stem] != path: stem = f"{base}-{n}"; n += 1
    _IMG_SLUGS[stem] = path
    return stem

def localize_images(p, body, slug=None):
    """Every <img> of a migrated post (Blogger CDN) becomes a local JPG placeholder; extra placeholders are put between paragraphs
    (after the first paragraph of every 2nd, 4th, 6th ... heading, max 5, only where that section has no picture yet)."""
    soup = BeautifulSoup(body, "lxml"); root = soup.body
    slug = slug or img_slug(p["path"])
    for a in list(root.find_all("a")):
        if BLOGGER_HOST.search(a.get("href", "")): a.unwrap()          # link-to-full-size anchors that pointed at Blogger
    extra = []
    for idx, h in enumerate(root.find_all("h2")):
        if idx % 2 == 0: continue
        ht = h.get_text(" ", strip=True)
        if not ht or re.search(r"الخاتمة|الأسئلة|خلاصة", ht): continue
        has, sib = False, h.next_sibling
        while sib is not None and getattr(sib, "name", None) != "h2":
            if getattr(sib, "name", None) and (sib.name == "img" or sib.find("img")): has = True; break
            sib = sib.next_sibling
        if not has: extra.append((h, ht))
    for h, ht in extra[:5]:
        wrap = soup.new_tag("p"); im = soup.new_tag("img"); im["alt"] = ht; im["data-new"] = "1"; wrap.append(im)
        nxt = h.find_next_sibling()
        (nxt if (nxt is not None and nxt.name == "p" and nxt.get_text(strip=True)) else h).insert_after(wrap)
    first = root.find(["h2", "img"])
    if first is None or first.name != "img":                              # no cover picture at the top
        wrap = soup.new_tag("p"); im = soup.new_tag("img"); im["alt"] = p["title"]; im["data-new"] = "1"; wrap.append(im)
        root.insert(0, wrap)
    for n, im in enumerate(root.find_all("img"), 1):
        fn = f"{slug}-{n:02d}.jpg"
        prev_h = im.find_previous("h2")
        prev_t = prev_h.get_text(" ", strip=True) if prev_h else ""
        text = p["title"] if n == 1 else (im.get("alt") or prev_t or p["title"])
        where = "الغلاف: أعلى المقال" if n == 1 else (f"تحت العنوان: {prev_t}" if prev_t else "أعلى المقال")
        im.attrs = {"src": f"/images/ar/{slug}/{fn}", "alt": im.get("alt") or text, "width": str(IMG_W), "height": str(IMG_H),
                    "loading": "eager" if n == 1 else "lazy", "decoding": "async"}
        make_placeholder(IMG_DIR / slug / fn, short(text, 105), fn)       # never overwrites a real picture
        IMG_MANIFEST.append(dict(article=p["title"], article_path=p.get("path") or f"/{slug}/", file=f"images-ar/{slug}/{fn}", name=fn, folder=slug, where=where, text=short(text, 105)))
    return "".join(str(c) for c in root.children if not (isinstance(c, NavigableString) and not str(c).strip()))

def prepare_new_images(a):
    """New (markdown) articles: no <img> written -> cover + a picture after every 2nd heading are added automatically (JPG placeholders named
    <slug>-NN.jpg, the name is printed on the picture).  If YOU wrote ![..](/images/ar/<slug>/<name>.jpg) lines, nothing is moved - a placeholder is
    only created for a name that does not exist yet.  A real file images-ar/<slug>/<name>.jpg always wins over the placeholder."""
    soup = BeautifulSoup(a["body"], "lxml"); imgs = soup.body.find_all("img")
    if not imgs: return localize_images(a, a["body"], slug=a["slug"])
    for im in imgs:
        m = re.match(r"^/images/ar/([^/]+)/([^/]+\.jpg)$", im.get("src", ""))
        if m:
            make_placeholder(IMG_DIR / m.group(1) / m.group(2), short(im.get("alt") or a["title"], 105), m.group(2))
            IMG_MANIFEST.append(dict(article=a["title"], article_path=f"/{a['slug']}/", file=f"images-ar/{m.group(1)}/{m.group(2)}", name=m.group(2), folder=m.group(1), where="مكانها اللي كتبته في المقال", text=im.get("alt") or a["title"]))
    return a["body"]

def copy_arabic_images():
    """images-ar/ -> dist/images/ar/ (JPG only; anything wider than 1600 px is shrunk so a phone photo does not weigh 5 MB)."""
    from PIL import Image, ImageOps
    n = 0
    if not IMG_DIR.exists(): return 0
    for f in sorted(IMG_DIR.rglob("*")):
        if not f.is_file(): continue
        rel = f.relative_to(IMG_DIR).as_posix()
        if f.suffix != ".jpg":
            warn(f"images-ar/{rel}: not a .jpg (lower-case) file - NOT copied. Save/convert it as JPG and name it exactly like the placeholder"); continue
        dst = OUT / "images" / "ar" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            im = Image.open(f)
            if im.width > 1600:
                im = ImageOps.exif_transpose(im).convert("RGB"); im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
                im.save(dst, "JPEG", quality=82, optimize=True, progressive=True)
            else:
                shutil.copy(f, dst)
        except Exception as e:
            warn(f"images-ar/{rel}: unreadable image ({e})"); continue
        n += 1
    return n

# ====================================================================== draft (planned) titles: visible, noindex, grouped in sections
def load_drafts(pub_ids, sections_cfg):
    reg = load_json("content-registry/arabic-planned-articles.json")
    out = []
    for a in reg.get("articles", []):
        if a.get("status") not in ("planned", "draft") or a.get("id") in pub_ids: continue
        slug = a.get("slug") or f"planned-{a.get('id')}"
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug): warn(f"registry id {a.get('id')}: bad slug '{slug}' - skipped"); continue
        out.append(dict(id=a["id"], title=a["title"], slug=slug, url=f"/{slug}/", cat=a.get("category") if a.get("category") in CATS else "tutorials",
                        section=a.get("section") if a.get("section") in sections_cfg else "", company=a.get("company") or ""))
    return out

def draft_cards(items, cos):
    return "".join(f'<a class="card draft" href="{d["url"]}"><span class="soon">قريبًا</span><h3>{E(d["title"])}</h3>'
                   + (f'<p>{E(cos[d["company"]])}</p>' if d["company"] in cos else "") + "</a>" for d in items)

def draft_blocks(items, cos, sections_cfg):
    out = []
    for sk in list(sections_cfg) + [""]:
        its = [d for d in items if d["section"] == sk]
        if not its: continue
        label = sections_cfg[sk]["label"] if sk else "عناوين أخرى"
        desc = sections_cfg[sk]["description"] if sk else ""
        out.append(f'<section class="sec draftsec"><h2 id="s-{sk or "other"}">{E(label)} <span class="cnt">({len(its)})</span></h2>'
                   + (f'<p class="meta">{E(desc)}</p>' if desc else "") + f'<div class="grid">{draft_cards(its, cos)}</div></section>')
    return "".join(out)

def build_arabic():
    print("== Arabic: migrating Blogger export")
    posts, pages, other = parse_blogger()
    inv = {"xml_entries": len(posts) + len(pages) + len(other), "posts_live": 0, "posts_draft": 0, "pages_trashed": 0, "deleted_or_other": len(other),
           "legacy_published": 0, "path_exact": 0, "no_path": 0, "duplicate_paths": 0, "empty_content": 0}
    stats = dict(h1_demoted=0, internal_links_rooted=0, affiliate_links_marked=0, external_links=0, images=0, tables=0)
    live, seen_paths, rows = [], {}, []
    for p in posts:
        if p["status"] != "LIVE":
            inv["posts_draft"] += 1
            rows.append(dict(kind="POST", status=p["status"], path=p["path"], title=p["title"], result="NOT migrated (not live)")); continue
        inv["posts_live"] += 1
        if not p["path"]:
            inv["no_path"] += 1; rows.append(dict(kind="POST", status="LIVE", path="", title=p["title"], result="MISSING permalink")); continue
        if p["path"] in seen_paths:
            inv["duplicate_paths"] += 1; warn(f"duplicate legacy path {p['path']}"); continue
        seen_paths[p["path"]] = 1
        s0 = dict(stats); s_local = dict(h1_demoted=0, internal_links_rooted=0, affiliate_links_marked=0, external_links=0, images=0, tables=0)
        body = sanitize(p["content"], s_local)
        body = localize_images(p, body)
        for k, v in s_local.items(): stats[k] += v
        words = len(text_of(body).split())
        if words < 50: inv["empty_content"] += 1; warn(f"{p['path']}: almost no text after cleaning ({words} words)")
        p.update(body=body, words=words, local=s_local, raw_len=len(p["content"]))
        p["slug"] = Path(p["path"]).stem
        p["url"] = p["path"]
        p["desc"] = p["meta"] or short(text_of(body), 155)
        cat = next((LABEL_TO_CAT[l] for l in p["labels"] if l in LABEL_TO_CAT), "tutorials")
        p["cat"] = cat
        p["trouble"] = bool(TROUBLE.search(p["path"]))
        live.append(p)
        inv["legacy_published"] += 1
        rows.append(dict(kind="POST", status="LIVE", path=p["path"], title=p["title"], published=p["published"], labels="|".join(p["labels"]),
                         words=words, images=s_local["images"], tables=s_local["tables"], raw_chars=p["raw_len"], clean_chars=len(body), result="migrated"))
    for p in pages:
        inv["pages_trashed"] += (p["status"] == "SOFT_TRASHED")
        rows.append(dict(kind="PAGE", status=p["status"], path=p["path"], title=p["title"], result="trashed in Blogger - re-created at a clean URL (see report)"))
    live.sort(key=lambda p: p["published"], reverse=True)

    # new articles (markdown) ---------------------------------------------------------------
    new_articles = load_new_articles({p["path"] for p in live})
    for a in new_articles: a["url"] = f"/{a['slug']}/"; a["body"] = prepare_new_images(a)
    allp = live + new_articles

    registry = load_json("content-registry/hosting-companies.json")
    companies = registry["companies"]
    cos = {c["slug"]: c["name_ar"] for c in companies}
    sections_cfg = load_json("content-registry/sections.json")["sections"]
    pub_ids = {int(a["registry_id"]) for a in new_articles if str(a.get("registry_id") or "").isdigit()}
    drafts = load_drafts(pub_ids, sections_cfg)
    print(f"   Draft titles shown on the site (noindex): {len(drafts)}")

    # --------------------------------------------------------------- article pages
    def related(p):
        same = [q for q in allp if q["cat"] == p["cat"] and q["url"] != p["url"]][:3]
        return same
    en_pairs = load_json("content-registry/language-pairs.json")["active"]
    ar_to_en = {x["ar"]: x["en"] for x in en_pairs}

    def article_page(p, legacy):
        cat_label = CATS[p["cat"]][0]
        has_aff = bool(re.search(r'rel="[^"]*sponsored', p["body"])) or any(
            MERCHANT_HOSTS.search(h) for h in re.findall(r'href="https?://([^"/]+)', p["body"]))
        disc = ('<p class="disc">قد نحصل على عمولة عند الشراء عبر بعض الروابط في هذه الصفحة دون أي تكلفة إضافية عليك. '
                'اقرأ <a href="/affiliate-disclosure/">إفصاح الشراكة</a>.</p>') if has_aff else ""
        rel = related(p)
        rel_html = f'<section class="sec"><h2>مقالات ذات صلة</h2><div class="grid">{post_cards(rel)}</div></section>' if rel else ""
        first_img = re.search(r'<img[^>]+src="([^"]+)"', p["body"])
        og_src = (BASE + first_img.group(1) if first_img.group(1).startswith("/") else first_img.group(1)) if first_img else None
        sch = [{"@context": "https://schema.org", "@type": "Article", "headline": p["title"], "description": p["desc"], "inLanguage": "ar",
                "datePublished": p["published"], "author": {"@type": "Person", "name": p.get("author") or NAME_AR},
                "publisher": {"@id": ORG_ID}, "mainEntityOfPage": BASE + p["url"],
                **({"image": og_src} if og_src else {})}]
        crumbs = [("الرئيسية", "/"), (cat_label, f"/category/{p['cat']}/"), (p["title"], p["url"])]
        meta = (f'<p class="meta"><a href="/category/{p["cat"]}/">{cat_label}</a> · نُشر في '
                f'<time datetime="{p["published"]}">{fmt_date_ar(p["published"])}</time></p>')
        body = f'<div class="wrap narrow"><article><h1>{E(p["title"])}</h1>{meta}{disc}<div class="post">{p["body"]}</div></article>{rel_html}</div>'
        ar_page(p["url"], p["title"], p["desc"], body, schemas=sch, crumbs=crumbs, og_image=og_src,
                og_type="article", kind="article", lastmod=p["published"], alt_en=ar_to_en.get(p["url"], "/en/"),
                hreflang_pair=p["url"] in ar_to_en)
        if legacy:                                            # same document under /_legacy/ for the Cloudflare rewrite (see _redirects)
            doc = (OUT / p["path"].lstrip("/")).read_text(encoding="utf-8")
            write_file("/_legacy" + p["path"][:-5] + "/index.html", doc)

    for p in live: article_page(p, legacy=True)
    for p in new_articles: article_page(p, legacy=False)

    # rewrites so the browser keeps the exact /YYYY/MM/slug.html URL (Pages otherwise 308-redirects *.html to the clean URL)
    rl = ["# Legacy Blogger URLs: serve the document at the ORIGINAL .html URL (status 200 = rewrite, not redirect)"]
    rl += [f"{p['path']}  /_legacy{p['path'][:-5]}/  200" for p in live]
    write_file("/_redirects", "\n".join(rl) + "\n")

    # --------------------------------------------------------------- categories
    cat_items = {k: [p for p in allp if p["cat"] == k or (k == "troubleshooting" and p.get("trouble"))] for k in CATS}
    dr_by_cat = {k: [d for d in drafts if d["cat"] == k] for k in CATS}
    for k, (label, desc) in CATS.items():
        its, drs = cat_items[k], dr_by_cat[k]
        if not its and not drs: warn(f"category {k} has no articles and no draft titles -> page not generated"); continue
        pub_html = f'<div class="grid">{post_cards(its)}</div>' if its else ""
        dr_html = (f'<div class="drafts"><h2 class="dh">عناوين قيد الكتابة ({len(drs)})</h2>'
                   f'<p class="meta">هذه العناوين قيد التجهيز وتُنشر تباعًا؛ صفحاتها غير مفهرسة إلى أن يكتمل المقال.</p>{draft_blocks(drs, cos, sections_cfg)}</div>') if drs else ""
        body = (f'<div class="wrap"><article><h1>{label}</h1><p class="meta">{E(desc)}</p>{pub_html}{dr_html}</article></div>')
        ar_page(f"/category/{k}/", label, desc, body, crumbs=[("الرئيسية", "/"), (label, f"/category/{k}/")], kind="category",
                index=bool(its), lastmod=max(p["published"] for p in its) if its else TODAY)

    # --------------------------------------------------------------- hosting directory + company profiles
    def co_articles(c):
        pat = re.compile(c["article_slug_pattern"], re.I) if c.get("article_slug_pattern") else None
        return [p for p in allp if pat and pat.search(p["url"])] if pat else []
    profiles = []
    for c in companies:
        c["_articles"] = co_articles(c)
        c["_drafts"] = [d for d in drafts if d["company"] == c["slug"]]
        c["profile"] = bool(c["_articles"] or c["_drafts"])
        if c["profile"]: profiles.append(c)
    for c in profiles:
        url = f"/hosting-companies/{c['slug']}/"
        c["_url"] = url
        body = (f'<div class="wrap narrow"><article><h1>{E(c["name_ar"])} ({E(c["name_en"])})</h1>'
                f'<p class="meta">كل ما نشرناه في {NAME_AR} عن {E(c["name_ar"])}.</p>'
                f'<p>الموقع الرسمي: <a href="{E(c["official_site"])}" rel="noopener" target="_blank">{E(c["official_domain"])}</a></p></article>'
                + (f'<section class="sec"><h2>المقالات</h2><div class="grid">{post_cards(c["_articles"])}</div></section>' if c["_articles"] else "")
                + (f'<div class="drafts"><h2 class="dh">عناوين قيد الكتابة ({len(c["_drafts"])})</h2>{draft_blocks(c["_drafts"], cos, sections_cfg)}</div>' if c["_drafts"] else "") + '</div>')
        ar_page(url, f"{c['name_ar']} ({c['name_en']})", f"مقالات {NAME_AR} عن {c['name_ar']} ({c['name_en']}).", body,
                crumbs=[("الرئيسية", "/"), ("شركات الاستضافة", "/hosting-companies/"), (c["name_ar"], url)], kind="company",
                index=bool(c["_articles"]), lastmod=max(p["published"] for p in c["_articles"]) if c["_articles"] else TODAY)
    rows_html = ""
    for c in companies:
        if c["profile"]:
            n, m = len(c["_articles"]), len(c["_drafts"])
            st = f'<a href="{c["_url"]}">' + (f"{n} مقال" if n else "") + (" · " if n and m else "") + (f"{m} قريبًا" if m else "") + "</a>"
        else:
            st = "قريبًا"
        rows_html += (f'<tr><td><strong>{E(c["name_ar"])}</strong><br><span class="meta">{E(c["name_en"])}</span></td>'
                      f'<td><a href="{E(c["official_site"])}" rel="noopener" target="_blank">{E(c["official_domain"])}</a></td><td>{st}</td></tr>')
    body = (f'<div class="wrap"><article><h1>شركات الاستضافة</h1>'
            f'<p class="meta">دليل لأشهر شركات استضافة المواقع. نضيف مراجعة الشركة هنا بعد نشرها كاملة فقط؛ الشركات التي لم تُنشر عنها مقالات بعد تظهر بعلامة «قريبًا».</p>'
            f'<div class="tw"><table><thead><tr><th>الشركة</th><th>الموقع الرسمي</th><th>محتوى الموقع</th></tr></thead><tbody>{rows_html}</tbody></table></div>'
            f'</article></div>')
    ar_page("/hosting-companies/", "شركات الاستضافة", "دليل لأشهر شركات استضافة المواقع مع روابط المقالات المتاحة عن كل شركة.", body,
            crumbs=[("الرئيسية", "/"), ("شركات الاستضافة", "/hosting-companies/")], kind="directory", lastmod=TODAY)

    # --------------------------------------------------------------- static pages (migrated from trashed Blogger pages)
    site_ar = load_json("content-ar/site-ar.json")
    tr = {p["path"]: p for p in pages}
    def static_from_blogger(path, url, title, desc):
        src = tr.get(path)
        if not src: warn(f"trashed page {path} not found in export"); return
        s = dict(h1_demoted=0, internal_links_rooted=0, affiliate_links_marked=0, external_links=0, images=0, tables=0)
        b = sanitize(src["content"], s)
        for old, new in (("/p/_5.html", "/contact/"), ("/p/_9.html", "/about/"), ("/p/_82.html", "/privacy-policy/"), ("/p/_21.html", "/terms/")):
            b = b.replace(f'href="{old}"', f'href="{new}"')
        b = re.sub(r"^\s*<h2>\s*" + re.escape(title) + r"\s*</h2>", "", b)          # avoid duplicate H1
        body = f'<div class="wrap narrow"><article><h1>{E(title)}</h1>{b}</article></div>'
        ar_page(url, title, desc, body, crumbs=[("الرئيسية", "/"), (title, url)], kind="static", lastmod=src["published"])
    static_from_blogger("/p/_9.html", "/about/", "من نحن", f"تعرف على {NAME_AR}: موقع عربي لمراجعات ومقارنات استضافة المواقع.")
    static_from_blogger("/p/_82.html", "/privacy-policy/", "سياسة الخصوصية", f"سياسة الخصوصية في {NAME_AR}: ما المعلومات التي نجمعها وكيف نستخدمها.")
    static_from_blogger("/p/_21.html", "/terms/", "الشروط والأحكام", f"الشروط والأحكام لاستخدام موقع {NAME_AR}.")

    disc_body = ('<div class="wrap narrow"><article><h1>إفصاح الشراكة</h1>'
                 f'<p>بعض الروابط في {NAME_AR} هي روابط شراكة (أفلييت). إذا نقرت على أحدها واشتريت منتجًا أو خدمة، فقد نحصل على عمولة دون أي تكلفة إضافية عليك.</p>'
                 '<h2>كيف يؤثر ذلك على المحتوى؟</h2><ul><li>العمولات تساعد في تغطية تكاليف تشغيل الموقع.</li>'
                 '<li>نسعى لوصف الشركات بدقة، بما في ذلك عيوبها.</li>'
                 '<li>الصفحات التي تحتوي على روابط شراكة تعرض تنبيهًا قصيرًا في أعلاها.</li>'
                 '<li>روابط الشراكة موسومة بالخاصية <code>rel="sponsored nofollow noopener"</code>.</li></ul>'
                 '<h2>أسئلة؟</h2><p>إن كان لديك سؤال عن هذه السياسة، تواصل معنا عبر <a href="/contact/">صفحة اتصل بنا</a>.</p></article></div>')
    ar_page("/affiliate-disclosure/", "إفصاح الشراكة", f"إفصاح الشراكة في {NAME_AR}: كيف تعمل روابط الشراكة وكيف تؤثر على المحتوى.", disc_body,
            crumbs=[("الرئيسية", "/"), ("إفصاح الشراكة", "/affiliate-disclosure/")], kind="static", lastmod=TODAY)

    email = (site_ar.get("contact_email") or "").strip()
    contact_core = (f'<p>للإبلاغ عن خطأ أو السؤال عن مراجعة أو التواصل بشأن الموقع، راسلنا على: <a href="mailto:{E(email)}">{E(email)}</a></p>'
                    if email else "<p>بيانات التواصل ستضاف قريبًا.</p>")
    ar_page("/contact/", "اتصل بنا", f"تواصل مع {NAME_AR} للإبلاغ عن خطأ أو للاستفسار.",
            f'<div class="wrap narrow"><article><h1>اتصل بنا</h1>{contact_core}</article></div>',
            index=bool(email), crumbs=[("الرئيسية", "/"), ("اتصل بنا", "/contact/")], kind="static", lastmod=TODAY)
    if not email: warn("content-ar/site-ar.json: contact_email is empty -> /contact/ is noindex and excluded from the sitemap until you add it")

    # --------------------------------------------------------------- search + 404 + home
    sbox = ('<form class="sbox" action="/search/" method="get"><input name="q" placeholder="ابحث في المراجعات والكوبونات والشروحات" aria-label="بحث">'
            '<button class="btn" type="submit">بحث</button></form>')
    ar_page("/search/", "بحث", f"ابحث في محتوى {NAME_AR}.",
            f'<div class="wrap narrow"><article><h1>بحث</h1><input id="q" class="qin" placeholder="اكتب كلمة البحث" aria-label="بحث" autofocus><div id="res" class="grid" style="margin-top:16px"></div></article></div>',
            index=False, kind="search", search=True)
    idx = [{"u": p["url"], "t": p["title"], "d": p["desc"]} for p in allp]
    idx += [{"u": f"/category/{k}/", "t": CATS[k][0], "d": CATS[k][1]} for k in CATS if cat_items[k] or dr_by_cat[k]]
    idx += [{"u": d["url"], "t": d["title"], "d": "قريبًا · " + (sections_cfg[d["section"]]["label"] if d["section"] else CATS[d["cat"]][0])} for d in drafts]
    idx += [{"u": c["_url"], "t": f'{c["name_ar"]} ({c["name_en"]})', "d": ""} for c in profiles]
    write_file("/search-index-ar.json", json.dumps(idx, ensure_ascii=False))
    write_file("/assets/search-ar.js",
               "(function(){var q=document.getElementById('q'),out=document.getElementById('res'),idx=[];"
               "function run(){var t=q.value.trim().toLowerCase();if(!t){out.innerHTML='';return}var w=t.split(/\\s+/);"
               "var r=idx.map(function(p){var s=0,h=(p.t+' '+p.d).toLowerCase();w.forEach(function(x){if(p.t.toLowerCase().indexOf(x)>-1)s+=3;if(h.indexOf(x)>-1)s+=1});return[s,p]})"
               ".filter(function(a){return a[0]>0}).sort(function(a,b){return b[0]-a[0]}).slice(0,20);"
               "out.innerHTML=r.length?r.map(function(a){return'<a class=\"card\" href=\"'+a[1].u+'\"><h3>'+a[1].t.replace(/</g,'&lt;')+'</h3><p>'+a[1].d.replace(/</g,'&lt;')+'</p></a>'}).join(''):'<p>لا توجد نتائج.</p>'}"
               "fetch('/search-index-ar.json').then(function(r){return r.json()}).then(function(j){idx=j;var p=new URLSearchParams(location.search).get('q');if(p){q.value=p;run()}});"
               "q.addEventListener('input',run)})();")
    write_file("/404.html",
               f'<!DOCTYPE html>\n<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>الصفحة غير موجودة | {NAME_AR}</title><meta name="robots" content="noindex"><link rel="stylesheet" href="/assets/style.css"><link rel="stylesheet" href="/assets/style-ar.css"></head>'
               f'<body>{nav_ar("/en/")}<div class="wrap narrow"><article><h1>الصفحة غير موجودة</h1><p>هذه الصفحة غير موجودة. جرّب <a href="/">الرئيسية</a> أو <a href="/search/">البحث</a>.</p></article></div>{FOOTER_AR}</body></html>')

    cat_cards = "".join(f'<a class="card" href="/category/{k}/"><h3>{CATS[k][0]}</h3><p>{E(CATS[k][1])}</p>'
                        f'<p class="meta">' + (f'{len(cat_items[k])} مقال' if cat_items[k] else '') + (' · ' if cat_items[k] and dr_by_cat[k] else '') + (f'{len(dr_by_cat[k])} قريبًا' if dr_by_cat[k] else '') + '</p></a>'
                        for k in CATS if cat_items[k] or dr_by_cat[k])
    co_cards = "".join(f'<a class="card" href="{c["_url"]}"><h3>{E(c["name_ar"])}</h3><p>' + (f'{len(c["_articles"])} مقال' if c["_articles"] else '') + (' · ' if c["_articles"] and c["_drafts"] else '') + (f'{len(c["_drafts"])} قريبًا' if c["_drafts"] else '') + '</p></a>' for c in profiles)
    home_body = (f'<section class="hero"><div class="wrap"><h1>نبض الاستضافة: مراجعات ومقارنات استضافة المواقع بالعربي</h1>'
                 f'<p>مراجعات شاملة ومقارنات واضحة بين شركات الاستضافة، مع شروحات وحلول عملية تساعد المستخدم العربي على اختيار الاستضافة المناسبة بسهولة.</p>{sbox}</div></section>'
                 f'<section class="sec"><div class="wrap"><h2>تصفح حسب القسم</h2><div class="grid">{cat_cards}</div></div></section>'
                 f'<section class="sec"><div class="wrap"><h2>أحدث المقالات</h2><div class="grid">{post_cards(allp[:6])}</div></div></section>'
                 f'<section class="sec"><div class="wrap"><h2>شركات الاستضافة</h2><div class="grid">{co_cards}</div>'
                 f'<p><a class="btn" href="/hosting-companies/">كل شركات الاستضافة</a></p></div></section>'
                 f'<section class="sec"><div class="wrap narrow"><h2>عن الموقع</h2><p>{NAME_AR} موقع عربي متخصص في مراجعات استضافة المواقع والمقارنة بينها. تعرّف على <a href="/about/">من نحن</a> و<a href="/affiliate-disclosure/">كيف يموّل الموقع نفسه</a>.</p></div></section>')
    sch = [org_schema(), {"@context": "https://schema.org", "@type": "WebSite", "@id": BASE + "/#website", "url": BASE + "/", "name": NAME_AR,
                          "inLanguage": "ar", "publisher": {"@id": ORG_ID},
                          "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint", "urlTemplate": BASE + "/search/?q={search_term_string}"},
                                              "query-input": "required name=search_term_string"}}]
    ar_page("/", "نبض الاستضافة | مراجعات ومقارنات استضافة المواقع بالعربي", "مراجعات شاملة ومقارنات بين شركات استضافة المواقع، مع كوبونات وشروحات وحلول عملية بالعربية.",
            home_body, schemas=sch, alt_en="/en/", hreflang_pair=True, kind="home", lastmod=allp[0]["published"] if allp else TODAY)

    # --------------------------------------------------------------- HTML sitemap (for visitors): every published article + every draft title
    def li(u, t, soon=False): return f'<li><a href="{u}">{E(t)}</a>' + (' <span class="soon">قريبًا</span>' if soon else "") + "</li>"
    parts = ['<h2>الصفحات الرئيسية</h2><ul>' + li("/", "الرئيسية") + li("/hosting-companies/", "شركات الاستضافة") + li("/search/", "البحث")
             + li("/about/", "من نحن") + li("/contact/", "اتصل بنا") + li("/affiliate-disclosure/", "إفصاح الشراكة")
             + li("/privacy-policy/", "سياسة الخصوصية") + li("/terms/", "الشروط والأحكام") + "</ul>"]
    for k, (label, desc) in CATS.items():
        its, drs = cat_items[k], dr_by_cat[k]
        if not its and not drs: continue
        cnt = " · ".join(x for x in ((f"{len(its)} مقال منشور" if its else ""), (f"{len(drs)} قريبًا" if drs else "")) if x)
        parts.append(f'<h2><a href="/category/{k}/">{E(label)}</a> <span class="cnt">({cnt})</span></h2>')
        if its: parts.append("<ul>" + "".join(li(q["url"], q["title"]) for q in its) + "</ul>")
        for sk in list(sections_cfg) + [""]:
            sd = [d for d in drs if d["section"] == sk]
            if sd: parts.append(f'<h3>{E(sections_cfg[sk]["label"] if sk else "عناوين أخرى")}</h3><ul>' + "".join(li(d["url"], d["title"], True) for d in sd) + "</ul>")
    if profiles:
        parts.append("<h2>صفحات الشركات</h2><ul>" + "".join(li(c["_url"], f'{c["name_ar"]} ({c["name_en"]})') for c in profiles) + "</ul>")
    sm_body = (f'<div class="wrap narrow sitemap"><article><h1>خريطة الموقع</h1><p class="meta">كل مقالات {NAME_AR} المنشورة، وكل العناوين التي ما زالت قيد الكتابة (تظهر بعلامة «قريبًا»).</p>'
               + "".join(parts) + "</article></div>")
    ar_page("/sitemap/", "خريطة الموقع", f"خريطة موقع {NAME_AR}: كل المقالات المنشورة والعناوين القادمة مرتبة حسب القسم.", sm_body,
            crumbs=[("الرئيسية", "/"), ("خريطة الموقع", "/sitemap/")], kind="sitemap", lastmod=TODAY)

    # --------------------------------------------------------------- registries / inventories
    return dict(inv=inv, stats=stats, rows=rows, live=live, new=new_articles, profiles=profiles, companies=companies, drafts=drafts, sections_cfg=sections_cfg, cos=cos,
                trashed=[p for p in pages if p["status"] == "SOFT_TRASHED"], cat_items=cat_items)

# ====================================================================== new markdown articles
RESERVED = {"about", "contact", "affiliate-disclosure", "privacy-policy", "terms", "search", "category", "hosting-companies", "en", "assets", "images",
            "content-registry", "_legacy", "2026", "sitemap", "sitemap-ar", "sitemap-en", "robots", "404"}

def load_new_articles(legacy_paths):
    """content-ar/articles/*.md.  A file is published automatically as soon as its body has >= 300 words (no status flip needed).
    Optional front matter: title, description (auto from text), slug (default: registry slug), category (default: registry), published (default: today),
    registry_id (default: number at the start of the file name), status: draft (force hidden) / published (force, refuses < 300 words)."""
    d = ROOT / "content-ar" / "articles"
    reg = {a["id"]: a for a in load_json("content-registry/arabic-planned-articles.json").get("articles", [])}
    out, slugs, waiting = [], set(), 0
    for f in sorted(d.glob("*.md")):
        txt = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", txt, re.S)
        if not m: die(f"{f.name}: missing front matter (--- ... ---)")
        meta, body_md = yaml.safe_load(m.group(1)) or {}, m.group(2)
        status = str(meta.get("status") or "auto")
        if status == "draft" or not body_md.strip(): waiting += 1; continue
        rid = meta.get("registry_id")
        if rid is None and re.match(r"^(\d+)-", f.name): rid = int(re.match(r"^(\d+)-", f.name).group(1))
        r = reg.get(int(rid)) if str(rid or "").isdigit() else None
        title = meta.get("title") or (r or {}).get("title")
        slug = str(meta.get("slug") or (r or {}).get("slug") or "").strip("/")
        cat = meta.get("category") or (r or {}).get("category")
        if not title or not slug or not cat: die(f"{f.name}: needs title, slug and category (or a valid registry_id)")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug): die(f"{f.name}: slug must be lowercase latin letters, digits and hyphens")
        if slug in RESERVED or slug in slugs: die(f"{f.name}: slug '{slug}' is reserved or duplicated")
        if cat not in CATS: die(f"{f.name}: unknown category {cat}")
        if mdlib is None: raise SystemExit("markdown package required for new articles")
        html_body = mdlib.markdown(body_md, extensions=["tables", "sane_lists"])
        s = dict(h1_demoted=0, internal_links_rooted=0, affiliate_links_marked=0, external_links=0, images=0, tables=0)
        clean = sanitize(html_body, s)
        words = len(text_of(clean).split())
        if words < MIN_WORDS_NEW_ARTICLE:
            if status == "published": die(f"{f.name}: only {words} words (< {MIN_WORDS_NEW_ARTICLE}); refusing to publish a thin page. Remove 'status: published' or write more")
            waiting += 1; print(f"   (not published yet: {f.name} has {words} words, needs {MIN_WORDS_NEW_ARTICLE})"); continue
        slugs.add(slug)
        pub = str(meta.get("published") or TODAY)[:10]
        out.append(dict(title=title, desc=meta.get("description") or short(text_of(clean), 155), slug=slug, cat=cat, published=pub, body=clean, words=words,
                        author=meta.get("author") or "", path=None, trouble=bool(meta.get("troubleshooting")), registry_id=rid))
    print(f"   New Arabic articles published: {len(out)} (empty/short files waiting: {waiting})")
    out.sort(key=lambda p: p["published"], reverse=True)
    return out

# ====================================================================== sitemaps / robots / headers / registries
def write_sitemaps(ar):
    def urlset(lang):
        items = sorted(((u, w) for u, w in WRITTEN.items() if w["lang"] == lang and w["index"]), key=lambda x: x[0])
        xs = "".join(f"<url><loc>{BASE}{u}</loc>" + (f"<lastmod>{w['lastmod']}</lastmod>" if w.get("lastmod") else "") + "</url>\n" for u, w in items)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + xs + "</urlset>\n"), len(items)
    sar, nar = urlset("ar"); sen, nen = urlset("en")
    write_file("/sitemap-ar.xml", sar); write_file("/sitemap-en.xml", sen)
    write_file("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               f'<sitemap><loc>{BASE}/sitemap-ar.xml</loc><lastmod>{TODAY}</lastmod></sitemap>\n'
               f'<sitemap><loc>{BASE}/sitemap-en.xml</loc><lastmod>{TODAY}</lastmod></sitemap>\n</sitemapindex>\n')
    write_file("/robots.txt", f"User-agent: *\nAllow: /\nDisallow: /_legacy/\n\nSitemap: {BASE}/sitemap.xml\n")
    write_file("/_headers", "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
               "/assets/*\n  Cache-Control: public, max-age=86400\n/images/*\n  Cache-Control: public, max-age=604800\n")
    return nar, nen

def write_image_guide():
    rows = IMG_MANIFEST
    with open(ROOT / "content-registry" / "image-map-ar.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["article", "file_name", "folder", "where_in_article", "text_on_placeholder"])
        for r in rows: w.writerow([r["article"], r["name"], r["file"], r["where"], r["text"]])
    out, last = [], None
    for r in rows:
        if r["article"] != last:
            out.append(f'<tr class="art"><td colspan="4"><b>{E(r["article"])}</b><br><small dir="ltr">{E(r["article_path"])}</small></td></tr>'); last = r["article"]
        out.append(f'<tr><td><img src="{E(r["file"])}" width="150" loading="lazy"></td><td dir="ltr"><code>{E(r["name"])}</code><br><small>{E(r["file"])}</small></td>'
                   f'<td>{E(r["where"])}</td><td>{E(r["text"])}</td></tr>')
    html_doc = ('<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>دليل استبدال الصور</title><meta name="robots" content="noindex">'
                '<style>body{font-family:system-ui,Tahoma,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.8}table{width:100%;border-collapse:collapse}'
                'th,td{border:1px solid #ddd;padding:.4rem;text-align:right;vertical-align:top}th{background:#f0fdfa}tr.art td{background:#0b2545;color:#fff}tr.art small{color:#9fe}'
                'code{direction:ltr;background:#f1f5f9;padding:2px 6px;border-radius:4px}.box{background:#f0fdfa;border-right:4px solid #13a89e;padding:12px 16px;border-radius:8px}</style></head><body>'
                '<h1>دليل استبدال الصور (العربي)</h1><div class="box"><p><b>مجلد الصور العربي:</b> <code>images-ar/</code> داخل المشروع (جنب build.py). كل مقال له مجلد باسمه.</p>'
                '<ol><li>هات الصورة اللي عايزها وخليها <b>JPG</b> (امتداد <code>.jpg</code> صغير).</li>'
                '<li>غيّر اسمها لنفس اسم الملف الموجود في الجدول تحت (مكتوب كمان على الصورة الوهمية نفسها).</li>'
                '<li>حطها في مجلد المقال جوه <code>images-ar/</code> وبدّل الملف القديم.</li>'
                '<li>شغّل <code>python3 build.py</code> وارفع <code>dist</code> — الصورة بتظهر مكان الوهمية على طول.</li></ol>'
                '<p>أي ملف PNG/WEBP/JPEG أو <code>.JPG</code> بحروف كبيرة مش هيتنسخ وهيطلع تحذير في البناء. الصور الأعرض من 1600 بكسل بتتصغّر تلقائيًا. المقاس المثالي 1200×675.</p></div>'
                f'<p>عدد الصور: {len(rows)} — نفس الجدول في <code>content-registry/image-map-ar.csv</code>.</p>'
                '<table><tr><th>معاينة</th><th>اسم الملف</th><th>مكانها في المقال</th><th>النص المكتوب عليها</th></tr>' + "".join(out) + '</table></body></html>')
    (ROOT / "IMAGE-REPLACEMENT-GUIDE.html").write_text(html_doc, encoding="utf-8")

def write_registries(ar, en_count):
    write_image_guide()
    # content-registry copies shipped inside the project (not inside dist: they are editorial files, not public pages)
    rows = ar["rows"]
    with open(ROOT / "content-registry" / "legacy-arabic-inventory.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "status", "path", "title", "published", "labels", "words", "images", "tables", "raw_chars", "clean_chars", "result"])
        w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in w.fieldnames})
    inv = []
    for f in sorted((OUT / "en").rglob("*.html")):
        rel = "/" + f.relative_to(OUT).as_posix()
        url = rel[:-len("index.html")] if rel.endswith("/index.html") else rel
        w = WRITTEN.get(url[3:] if url.startswith("/en/") else url, WRITTEN.get(url))
    # English inventory straight from WRITTEN
    with open(ROOT / "content-registry" / "english-inventory.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["english_url", "original_root_url", "indexable", "in_sitemap_en"])
        for u, d in sorted(WRITTEN.items()):
            if d["lang"] == "en":
                orig = u[3:] if u.startswith("/en/") else u
                w.writerow([u, orig, d["index"], d["index"]])

def freeze_english_section():
    """English stays noindex + 'coming soon' banner EXCEPT pages that are real new content: a page whose datePublished is on/after
    content-registry/english-publish.json "live_from" (and that gen.py built as indexable) goes live automatically - indexable, in sitemap-en.xml, no banner.
    So: write content/articles/<slug>.md with published: <today>, push, done."""
    cfg = load_json("content-registry/english-publish.json")
    live_from = cfg["live_from"]
    banner = ('<div id="en-coming-soon" style="background:linear-gradient(135deg,#0b2545,#13a89e);color:#fff;padding:14px 20px;text-align:center;font-weight:700;font-size:16px;position:sticky;top:0;z-index:99">'
              'English section is under preparation and will launch soon. <a href="/" style="color:#fff;text-decoration:underline;margin-left:8px">النسخة العربية متاحة الآن</a></div>')
    frozen = live = 0
    for url, w in WRITTEN.items():
        if w["lang"] != "en": continue
        f = OUT / w["file"].lstrip("/")
        t = f.read_text(encoding="utf-8")
        m = re.search(r'"datePublished": ?"(\d{4}-\d{2}-\d{2})', t)
        if m and m.group(1) >= live_from and 'content="index,follow' in t and w["kind"] != "404":
            w["index"] = True; w["lastmod"] = w.get("lastmod") or m.group(1); live += 1; continue
        w["index"] = False
        t2 = re.sub(r'content="index, ?follow[^"]*"', 'content="noindex,follow"', t)
        if 'name="robots"' not in t2: t2 = t2.replace("<head>", '<head><meta name="robots" content="noindex,follow">', 1)
        if 'id="en-coming-soon"' not in t2: t2 = re.sub(r"<body([^>]*)>", lambda m_: f"<body{m_.group(1)}>" + banner, t2, count=1)
        if t2 != t: f.write_text(t2, encoding="utf-8")
        frozen += 1
    print(f"   English: {live} page(s) LIVE (published >= {live_from}), {frozen} frozen (noindex + banner)")
    return live


def build_planned_arabic_stubs(ar):
    """One 'coming soon' page per draft title: visible on the site (linked from category / sitemap page / search / company page),
    noindex,follow, never in sitemap-ar.xml.  Removed automatically once the article is published (registry_id in its front matter)."""
    drafts, sc, cos = ar["drafts"], ar["sections_cfg"], ar["cos"]
    n = 0
    for d in drafts:
        cat_label = CATS[d["cat"]][0]
        sec_label = sc[d["section"]]["label"] if d["section"] else ""
        sib = [x for x in drafts if x["section"] == d["section"] and x["url"] != d["url"]][:8]
        meta = f'<a href="/category/{d["cat"]}/">{E(cat_label)}</a>' + (f' › <a href="/category/{d["cat"]}/#s-{d["section"]}">{E(sec_label)}</a>' if sec_label else "") + (f' · {E(cos[d["company"]])}' if d["company"] in cos else "")
        body = (f'<div class="wrap narrow"><article><h1>{E(d["title"])}</h1><p class="meta">{meta}</p>'
                '<div class="note" style="margin:24px 0;padding:20px;border-radius:10px;background:var(--card);border-right:4px solid var(--acc)">'
                '<strong>هذا المقال قيد التجهيز</strong><br>سننشر المحتوى الكامل قريبًا.</div>'
                f'<p><a href="/category/{d["cat"]}/#s-{d["section"] or "other"}">كل عناوين هذا القسم</a> · <a href="/">الرئيسية</a> · <a href="/sitemap/">خريطة الموقع</a></p></article>'
                + (f'<section class="sec"><h2>عناوين أخرى في نفس القسم</h2><div class="grid">{draft_cards(sib, cos)}</div></section>' if sib else "") + "</div>")
        crumbs = [("الرئيسية", "/"), (cat_label, f"/category/{d['cat']}/"), (d["title"], d["url"])]
        ar_page(d["url"], d["title"], f"قريبًا: {d['title']}", body, index=False, kind="planned", crumbs=crumbs)
        n += 1
    print(f"   Draft pages: {n} 'coming soon' pages (noindex, linked from the site, NOT in sitemap-ar.xml)")
    return n


def main():
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir()
    n_en, ar_to_en, en_to_ar = build_english()
    shutil.copy(ROOT / "assets-ar" / "style-ar.css", OUT / "assets" / "style-ar.css")
    if (ROOT / "assets-ar" / "coupon-reveal.js").exists():
        shutil.copy(ROOT / "assets-ar" / "coupon-reveal.js", OUT / "assets" / "coupon-reveal.js")
    with open(OUT / "assets" / "style.css", "a", encoding="utf-8") as f:        # shared rule for the language switcher (English pages load only style.css)
        f.write("\n.nav a.langsw{border:1px solid var(--bd);border-radius:99px;padding:2px 12px;background:var(--card);white-space:nowrap}\n")
    ar = build_arabic()
    build_planned_arabic_stubs(ar)
    print(f"   Arabic images copied to dist/images/ar: {copy_arabic_images()}")
    freeze_english_section()   # decides which English pages are live BEFORE the sitemaps are written
    nar, nen = write_sitemaps(ar)
    write_registries(ar, n_en)
    summary = dict(english_html_files=n_en, sitemap_ar=nar, sitemap_en=nen, arabic=ar["inv"], arabic_stats=ar["stats"],
                   new_articles_published=len(ar["new"]), company_profiles=len(ar["profiles"]), warnings=REPORT["warnings"])
    (ROOT / "build-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
