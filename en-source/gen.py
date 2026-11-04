#!/usr/bin/env python3
"""PrimeTech Hosting static site generator.
Run:  python3 gen.py        -> builds ./dist  (upload dist/ to Cloudflare Pages)
Content: content/pages, content/guides, content/comparisons, content/best, content/reviews (*.md)
Data:    data/hosts.json, data/coupons.json, data/site.json
Images:  auto-generated labelled cards in dist/images/. Put your own jpg with the SAME file name in images_custom/ to override.
"""
import json, os, re, shutil, html, csv, textwrap, glob
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
SITE = json.load(open(f"{ROOT}/data/site.json", encoding="utf-8"))
HOSTS = json.load(open(f"{ROOT}/data/hosts.json", encoding="utf-8"))
COUPONS = json.load(open(f"{ROOT}/data/coupons.json", encoding="utf-8"))
BASE = SITE["url"].rstrip("/")
NAME = SITE["name"]
H = {h["slug"]: h for h in HOSTS}
E = html.escape
NA = "Check the provider's site for current pricing"

CATS = []

PAGES = []      # dict(url,title,desc,index,updated,kind)
EXP_DEFAULT = "Check the provider's site"
def host_of(u): return re.sub(r"^https?://(www\.)?", "", u).split("/")[0]
IMAGES = []     # image map rows
SEARCH = []

# ---------------------------------------------------------------- helpers
def write(path, content):
    full = os.path.join(DIST, path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)

def parse_md(path):
    t = open(path, encoding="utf-8").read()
    meta = {}
    if t.startswith("---"):
        _, fm, body = t.split("---", 2)
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    else:
        body = t
    return meta, body.strip()

def aff_attrs():
    return 'rel="sponsored nofollow noopener" target="_blank"'

def host_url(slug):
    return H[slug]["url"]

def inline(s):
    s = E(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    def link(m):
        txt, url = m.group(1), html.unescape(m.group(2))
        if url.startswith("host:"):
            sl = url[5:]
            return f'<a href="{E(host_url(sl))}" {aff_attrs()}>{txt}</a>'
        if url.startswith("http"):
            return f'<a href="{E(url)}" rel="noopener" target="_blank">{txt}</a>'
        return f'<a href="{E(url)}">{txt}</a>'
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, s)

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def md_to_html(body):
    out, lines, i = [], body.splitlines(), 0
    faq, in_faq, cur_q, cur_a = [], False, None, []
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if ln.startswith("### ") and in_faq:
            if cur_q: faq.append((cur_q, " ".join(cur_a)))
            cur_q, cur_a = ln[4:].strip(), []
            out.append(f"<h3>{inline(cur_q)}</h3>"); i += 1; continue
        if ln.startswith("## "):
            if in_faq and cur_q: faq.append((cur_q, " ".join(cur_a))); cur_q, cur_a = None, []
            title = ln[3:].strip()
            in_faq = title.lower() in ("frequently asked questions", "faq", "faqs")
            out.append(f'<h2 id="{slugify(title)}">{inline(title)}</h2>'); i += 1; continue
        mi = re.match(r"^!\[([^\]]*)\]\((/images/[^)\s]+\.jpg)\)\s*$", ln.strip())
        if mi:
            out.append(f'<p><img class="post-img" src="{E(mi.group(2))}" alt="{E(mi.group(1))}" width="1200" height="630" loading="lazy" decoding="async"></p>'); i += 1; continue
        if ln.startswith("### "):
            out.append(f"<h3>{inline(ln[4:])}</h3>"); i += 1; continue
        if ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>"); i += 1; continue
        if ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>"); continue
        if re.match(r"\d+\. ", ln):
            items = []
            while i < len(lines) and re.match(r"\d+\. ", lines[i]):
                item_txt = re.sub(r"^\d+\. ", "", lines[i]); items.append(f"<li>{inline(item_txt)}</li>"); i += 1
            out.append("<ol>" + "".join(items) + "</ol>"); continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            rows = [r for r in rows if not all(re.match(r"^:?-+:?$", c) for c in r)]
            th = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            tb = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>'); continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"(#{1,3} |- |\d+\. |\||!\[)", lines[i]):
            para.append(lines[i].strip()); i += 1
        txt = " ".join(para)
        if in_faq and cur_q: cur_a.append(txt)
        out.append(f"<p>{inline(txt)}</p>")
    if in_faq and cur_q: faq.append((cur_q, " ".join(cur_a)))
    return "\n".join(out), faq

def words_in(htm):
    t = re.sub(r"<[^>]+>", " ", htm)
    return len(re.findall(r"[A-Za-z0-9'’$%.-]+", t))

# ---------------------------------------------------------------- images
FONT_B = f"{ROOT}/../assets-ar/fonts/DejaVuSans-Bold.ttf"      # bundled with the project
FONT_R = f"{ROOT}/../assets-ar/fonts/DejaVuSans.ttf"
PROJECT = os.path.abspath(f"{ROOT}/..")                          # project root (images-en/ lives here)
THEMES = {"home": ("#0b2545", "#13a89e"), "review": ("#10375c", "#2a9d8f"), "category": ("#1b263b", "#3a86ff"),
          "guide": ("#2d1e4f", "#7b5cff"), "compare": ("#3d1f1f", "#e07a5f"), "best": ("#12355b", "#f4a261"),
          "tool": ("#0f3d3e", "#52b788"), "coupon": ("#4a2c0a", "#f9a03f")}

def make_image(fname, text, sub, theme, page_url, purpose, base=None, n=None):
    """base/n given -> ARTICLE image: your own JPG goes to images-en/<base>/<base>-NN.jpg (NN=01 hero, 02.. inline); the placeholder prints that name."""
    os.makedirs(f"{DIST}/images", exist_ok=True)
    out = f"{DIST}/images/{fname}"
    label = f"{base}-{n:02d}.jpg" if base else None
    custom = next((c for c in ([f"{PROJECT}/images-en/{base}/{label}"] if base else []) + [f"{ROOT}/images_custom/{fname}"] if os.path.exists(c)), None)
    IMAGES.append([fname, page_url, purpose, text, "custom" if custom else "auto-generated", label or ""])
    if custom:
        im0 = Image.open(custom)
        if im0.width > 1600:
            im0 = im0.convert("RGB"); im0.resize((1600, round(im0.height * 1600 / im0.width)), Image.LANCZOS).save(out, "JPEG", quality=82, optimize=True)
        else:
            shutil.copy(custom, out)
        return
    c1, c2 = THEMES.get(theme, THEMES["guide"])
    W, Ht = 1200, 630
    im = Image.new("RGB", (W, Ht), c1)
    d = ImageDraw.Draw(im)
    r1, g1, b1 = Image.new("RGB", (1, 1), c1).getpixel((0, 0)); r2, g2, b2 = Image.new("RGB", (1, 1), c2).getpixel((0, 0))
    for y in range(Ht):
        t = y / Ht
        d.line([(0, y), (W, y)], fill=(int(r1 + (r2 - r1) * t * .55), int(g1 + (g2 - g1) * t * .55), int(b1 + (b2 - b1) * t * .55)))
    d.rectangle([60, 60, 74, Ht - 60], fill=c2)
    fb, fs, fl = ImageFont.truetype(FONT_B, 66), ImageFont.truetype(FONT_R, 32), ImageFont.truetype(FONT_B, 26)
    d.text((100, 70), NAME.upper(), font=fl, fill="#ffffff")
    lines = textwrap.wrap(text, 24)[:4]
    y = 180
    for l in lines:
        d.text((100, y), l, font=fb, fill="#ffffff"); y += 84
    if sub:
        d.text((100, Ht - 150), sub, font=fs, fill="#dbe7f3")
    if label:
        fl2 = ImageFont.truetype(FONT_B, 30); wl = d.textlength(label, font=fl2)
        d.rounded_rectangle([100, Ht - 100, 100 + wl + 40, Ht - 46], radius=12, fill="#ffffff"); d.text((120, Ht - 94), label, font=fl2, fill="#0b2545")
        d.text((100 + wl + 60, Ht - 90), "placeholder", font=ImageFont.truetype(FONT_R, 22), fill="#dbe7f3")
    im.save(out, "JPEG", quality=82, optimize=True)

# ---------------------------------------------------------------- layout
CSS = """:root{--bg:#fff;--fg:#14213d;--mut:#5b6b7f;--pri:#0b5ed7;--acc:#13a89e;--card:#f5f8fb;--bd:#dfe7ef;--warn:#fff7e0}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font:17px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg)}
a{color:var(--pri)}img{max-width:100%;height:auto}
.wrap{max-width:1100px;margin:0 auto;padding:0 20px}
.narrow{max-width:780px}
header.top{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--bd);z-index:10}
.nav{display:flex;align-items:center;gap:22px;height:64px}
.logo{font-weight:800;font-size:20px;color:var(--fg);text-decoration:none}.logo span{color:var(--acc)}
.nav a.l{color:var(--fg);text-decoration:none;font-weight:600;font-size:15px}
.nav a.l:hover{color:var(--pri)}.sp{flex:1}
.hero{background:linear-gradient(135deg,#0b2545,#13a89e);color:#fff;padding:64px 0}
.hero h1{font-size:clamp(30px,5vw,46px);line-height:1.15;margin:0 0 14px}.hero p{font-size:19px;max-width:640px;margin:0 0 22px;opacity:.95}
.btn{display:inline-block;background:var(--pri);color:#fff!important;padding:11px 20px;border-radius:8px;font-weight:700;text-decoration:none}
.btn.alt{background:#fff;color:var(--fg)!important}
.sbox{display:flex;gap:8px;max-width:520px}.sbox input{flex:1;padding:12px 14px;border-radius:8px;border:0;font-size:16px}
.sec{padding:44px 0}.sec h2{margin:0 0 18px;font-size:26px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:18px;text-decoration:none;color:var(--fg);display:block}
.card:hover{border-color:var(--pri)}.card h3{margin:0 0 6px;font-size:18px}.card p{margin:0;color:var(--mut);font-size:15px}
.badge{display:inline-block;font-size:12px;font-weight:700;background:#e3f1ff;color:#0b4a9e;border-radius:99px;padding:2px 9px;margin:6px 4px 0 0}
.badge.d{background:#fff0d6;color:#8a5300}
.crumbs{font-size:14px;color:var(--mut);padding:16px 0 0}.crumbs a{color:var(--mut)}
article{padding:10px 0 50px}article h1{font-size:clamp(28px,4.5vw,40px);line-height:1.2;margin:12px 0 10px}
article h2{margin:34px 0 10px;font-size:26px}article h3{margin:24px 0 6px;font-size:20px}
.meta{color:var(--mut);font-size:14px;margin-bottom:14px}
.disc{background:var(--warn);border:1px solid #f1dc9c;border-radius:8px;padding:10px 14px;font-size:14px;margin:14px 0}
.note{background:var(--card);border-left:4px solid var(--acc);padding:12px 16px;border-radius:6px;margin:16px 0}
.tw{overflow-x:auto;margin:16px 0}table{border-collapse:collapse;width:100%;min-width:560px;font-size:15px}
th,td{border:1px solid var(--bd);padding:9px 12px;text-align:left;vertical-align:top}th{background:var(--card)}
.hero-img,.post-img{border-radius:12px;margin:10px 0 16px;width:100%}
.filters{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}.filters input,.filters select{padding:10px;border:1px solid var(--bd);border-radius:8px;font-size:15px}
footer{background:#0b2545;color:#cfe0f2;padding:34px 0;margin-top:30px;font-size:14px}footer a{color:#fff;margin-right:16px}
@media(max-width:720px){.nav{gap:14px;overflow-x:auto}.hero{padding:44px 0}}
"""

JS_SEARCH = """(function(){var q=document.getElementById('q'),out=document.getElementById('res'),idx=[];
function run(){var t=q.value.trim().toLowerCase();if(!t){out.innerHTML='';return}var w=t.split(/\\s+/);
var r=idx.map(function(p){var s=0,h=(p.t+' '+p.d).toLowerCase();w.forEach(function(x){if(p.t.toLowerCase().indexOf(x)>-1)s+=3;if(h.indexOf(x)>-1)s+=1});return[s,p]}).filter(function(a){return a[0]>0}).sort(function(a,b){return b[0]-a[0]}).slice(0,20);
out.innerHTML=r.length?r.map(function(a){return'<a class="card" href="'+a[1].u+'"><h3>'+a[1].t.replace(/</g,'&lt;')+'</h3><p>'+a[1].d.replace(/</g,'&lt;')+'</p></a>'}).join(''):'<p>No results.</p>'}
fetch('/search-index.json').then(function(r){return r.json()}).then(function(j){idx=j;var p=new URLSearchParams(location.search).get('q');if(p){q.value=p;run()}});
q.addEventListener('input',run)})();"""

def nav_html():
    return ('<header class="top"><div class="wrap nav"><a class="logo" href="/">PrimeTech<span>Hosting</span></a>'
            '<a class="l" href="/hostinger/">Hostinger</a><a class="l" href="/bluehost/">Bluehost</a><a class="l" href="/hostgator/">HostGator</a>'
            '<a class="l" href="/compare/">Comparisons</a><a class="l" href="/coupons/">Coupons</a>'
            '<span class="sp"></span><a class="l" href="/search/">Search</a></div></header>')

def footer_html():
    return (f'<footer><div class="wrap"><p><strong>{E(NAME)}</strong>: {E(SITE["tagline"])}. We may earn a commission from links on this site. '
            'See our <a href="/affiliate-disclosure/" style="margin:0">Affiliate Disclosure</a>.</p><p>'
            '<a href="/about/">About</a><a href="/review-methodology/">Methodology</a><a href="/editorial-policy/">Editorial Policy</a>'
            '<a href="/contact/">Contact</a><a href="/privacy-policy/">Privacy</a><a href="/terms/">Terms</a><a href="/sitemap/">Sitemap</a></p></div></footer>')

def crumb_schema(crumbs):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": BASE + u} for i, (n, u) in enumerate(crumbs)]}

ORG = {"@type": "Organization", "@id": BASE + "/#org", "name": NAME, "url": BASE + "/",
       "logo": {"@type": "ImageObject", "url": BASE + "/images/logo.jpg"}}

def page(url, title, desc, body, schemas=None, index=True, crumbs=None, image=None, kind="page", updated=None,
         og_type="website", extra_head="", extra_js="", search=True, force_noindex=False):
    schemas = list(schemas or [])
    index = (index or bool(SITE.get("index_drafts"))) and not force_noindex
    if crumbs:
        schemas.append(crumb_schema(crumbs))
    full_title = title if title.endswith(NAME) else f"{title} | {NAME}"
    canon = BASE + url
    img = f"{BASE}/images/{image}" if image else f"{BASE}/images/home.jpg"
    robots = "index,follow,max-image-preview:large" if index else "noindex,follow"
    ga = ""
    if SITE.get("ga_id"):
        ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={E(SITE["ga_id"])}"></script>'
              f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag("js",new Date());gtag("config","{E(SITE["ga_id"])}")</script>')
    gsc = f'<meta name="google-site-verification" content="{E(SITE["gsc_verification"])}">' if SITE.get("gsc_verification") else ""
    sj = "".join(f'<script type="application/ld+json">{json.dumps(s, ensure_ascii=False)}</script>' for s in schemas)
    cb = ""
    if crumbs and len(crumbs) > 1:
        cb = '<nav class="crumbs wrap" aria-label="Breadcrumb">' + " &rsaquo; ".join(
            f'<a href="{u}">{E(n)}</a>' if i < len(crumbs) - 1 else E(n) for i, (n, u) in enumerate(crumbs)) + "</nav>"
    doc = f"""<!DOCTYPE html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(full_title)}</title><meta name="description" content="{E(desc)}"><meta name="robots" content="{robots}">
<link rel="canonical" href="{canon}"><link rel="stylesheet" href="/assets/style.css">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%230b2545'/%3E%3Ctext x='32' y='43' font-size='32' font-weight='700' text-anchor='middle' fill='%2313a89e' font-family='Arial'%3EP%3C/text%3E%3C/svg%3E">
<meta property="og:type" content="{og_type}"><meta property="og:site_name" content="{E(NAME)}"><meta property="og:title" content="{E(full_title)}">
<meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{canon}"><meta property="og:image" content="{img}">
<meta property="og:locale" content="en_US"><meta name="twitter:card" content="summary_large_image">{gsc}{extra_head}{sj}{ga}</head>
<body>{nav_html()}{cb}{body}{footer_html()}{extra_js}</body></html>"""
    write(url.rstrip("/") + "/index.html" if url != "/" else "/index.html", doc)
    PAGES.append(dict(url=url, title=title, desc=desc, index=index, updated=updated, kind=kind))
    if index and search:
        SEARCH.append({"u": url, "t": title, "d": desc})

def has_aff(htm):
    return "sponsored" in htm

DISC = ('<p class="disc"><strong>Disclosure:</strong> This page contains affiliate links. We may earn a commission if you buy through them, at no extra cost to you. '
        '<a href="/affiliate-disclosure/">Learn more</a>.</p>')

def types_badges(h):
    return "".join(f'<span class="badge">{E(t.upper() if t == "vps" else t.title())}</span>' for t in h["types"])

def host_card(h):
    draft = "" if h["status"] == "published" else ""
    return (f'<a class="card" href="/reviews/{h["slug"]}/"><h3>{E(h["name"])}</h3><p>{E(h["domain"])}</p>{types_badges(h)}</a>')

def cta(h, label=None):
    return f'<a class="btn" href="{E(h["url"])}" {aff_attrs()}>{E(label or "Visit " + h["name"])}</a>'

def is_pub(h):
    return h["status"] == "published"

# ---------------------------------------------------------------- build
# ---------------------------------------------------------------- content plan (clusters)
SEC = {"A": ("Reviews and Pricing", "Commercial investigation", "review"), "B": ("Coupons and Discounts", "Transactional", "coupon"),
       "C": ("Comparisons", "Commercial investigation", "compare"), "D": ("Tutorials", "Informational (how-to)", "guide"),
       "E": ("Troubleshooting", "Informational (problem solving)", "category")}
ORDER = ["hostinger", "bluehost", "hostgator"]

def load_plan():
    plan, seen_pairs, counters = [], {}, {}
    for ln in open(f"{ROOT}/content/plan.txt", encoding="utf-8"):
        if ln.startswith("#") or not ln.strip(): continue
        host, sec, title, kw = ln.rstrip("\n").split("|")
        counters[host] = counters.get(host, 0) + 1
        e = dict(id=counters[host], host=host, sec=sec, title=title, kw=kw, slug=slugify(kw), status="planned", note="", merged_into="")
        e["url"] = f"/{host}/{e['slug']}/"
        if e["id"] == 1:
            e["url"] = f"/reviews/{host}/"
        if sec == "C":
            m = re.match(r"(\w+) vs (\w+)$", kw)
            if m and m.group(1) in H and m.group(2) in H:
                key = frozenset((m.group(1), m.group(2)))
                if key in seen_pairs:
                    e["status"] = "merged"; e["merged_into"] = seen_pairs[key]["url"]
                    e["note"] = "Duplicate topic of " + seen_pairs[key]["kw"] + "; merged to avoid keyword cannibalization"
                else:
                    seen_pairs[key] = e
            e["url"] = e["merged_into"] or f"/compare/{e['slug']}/"
        if re.search(r"student discount|\b\d+ off", kw):
            e["note"] = (e["note"] + "; " if e["note"] else "") + "Verify the claim (discount existence/figure) before writing"
        if os.path.exists(f"{ROOT}/content/articles/{e['slug']}.md") and e["status"] == "planned":
            e["status"] = "written"
        if e["status"] == "written" or (e["id"] == 1 and is_pub(H[e["host"]])):
            e["note"] = ""
        elif re.search(r"choice plus|hatchling|baby plan|business plan", kw):
            e["note"] = (e["note"] + "; " if e["note"] else "") + "Plan name may be outdated; confirm it exists on the provider's current pricing page"
        plan.append(e)
    return plan

def article_images(htm, base, title, theme, url):
    """No picture written in the .md -> a picture after the first paragraph of every 2nd heading (max 5): <base>-02.jpg, -03.jpg ...
    You wrote ![alt](/images/<base>-02.jpg) lines yourself -> nothing is moved; a placeholder is made only for names that have no file yet."""
    own = re.findall(r'<img class="post-img" src="/images/([^"]+?)\.jpg"', htm)
    if own:
        for stem in own:
            m = re.match(r"^(.+)-(\d\d)$", stem)
            make_image(f"{stem}.jpg", title, "", theme, url, f"Inline image: {title}", base=m.group(1) if m else None, n=int(m.group(2)) if m else None) if m else None
        return htm
    parts = re.split(r"(?=<h2 )", htm)
    out, n = [parts[0]], 1
    for idx, sec in enumerate(parts[1:]):
        h = re.match(r'<h2 id="([^"]*)">(.*?)</h2>', sec)
        if idx % 2 == 1 and h and n < 6 and not re.search(r"faq|frequently|conclusion|final", h.group(1)):
            n += 1; fn = f"{base}-{n:02d}.jpg"; text = re.sub(r"<[^>]+>", "", h.group(2))
            make_image(fn, html.unescape(text), title, theme, url, f"Inline image {n}: {title}", base=base, n=n)
            tag = f'<p><img class="post-img" src="/images/{fn}" alt="{E(html.unescape(text))}" width="1200" height="630" loading="lazy" decoding="async"></p>'
            m2 = re.search(r"</h2>\s*<p>.*?</p>", sec, re.S); cut = m2.end() if m2 else h.end()
            sec = sec[:cut] + tag + sec[cut:]
        out.append(sec)
    return "".join(out)

def build_plan():
    plan = load_plan()
    n_written = 0
    for e in plan:
        if e["status"] == "merged" or e["id"] == 1:
            continue
        hname = H[e["host"]]["name"]
        sname, intent, theme = SEC[e["sec"]]
        img = f"{e['slug']}.jpg"
        make_image(img, e["title"], f"{hname} · {sname}", theme, e["url"], f"Hero image: {e['title']}", **(dict(base=e["slug"], n=1) if e["status"] == "written" else {}))
        crumbs = [("Home", "/"), (hname, f"/{e['host']}/")] if e["sec"] != "C" else [("Home", "/"), ("Comparisons", "/compare/")]
        crumbs.append((e["title"], e["url"]))
        path = f"{ROOT}/content/articles/{e['slug']}.md"
        if e["status"] == "written":
            meta, b = parse_md(path)
            for req in ("description", "published", "updated"):
                assert meta.get(req), f"{path}: missing {req}"
            htm, faq = md_to_html(b)
            htm = article_images(htm, e["slug"], meta.get("title", e["title"]), theme, e["url"])
            title = meta.get("title", e["title"])
            basis = f'<p class="meta">{E(meta["review_basis"])}</p>' if meta.get("review_basis") else ""
            top = f'<p class="meta">Published {meta["published"]} · Updated {meta["updated"]} · By {E(SITE["author_name"])}</p>{basis}' + (DISC if has_aff(htm) else "") + \
                  f'<img class="hero-img" src="/images/{img}" width="1200" height="630" alt="{E(e["title"])}" fetchpriority="high">'
            htm = htm.replace("</h1>", "</h1>" + top, 1) if "<h1>" in htm else f"<h1>{E(title)}</h1>{top}{htm}"
            sch = [{"@context": "https://schema.org", "@type": "Article", "headline": title, "description": meta["description"], "image": f"{BASE}/images/{img}",
                    "datePublished": meta["published"], "dateModified": meta["updated"],
                    "author": {"@type": "Organization", "name": SITE["author_name"], "url": BASE + "/author/"},
                    "publisher": {"@id": BASE + "/#org"}, "mainEntityOfPage": BASE + e["url"]}]
            if faq:
                sch.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
            page(e["url"], title, meta["description"], f'<div class="wrap narrow"><article>{htm}</article></div>', sch, index=True,
                 crumbs=crumbs, image=img, kind="article", updated=meta["updated"], og_type="article")
            n_written += 1
        else:
            body = (f'<div class="wrap narrow"><article><h1>{E(e["title"])}</h1><p class="meta">{E(hname)} · {E(sname)}</p>'
                    f'<img class="hero-img" src="/images/{img}" width="1200" height="630" alt="{E(e["title"])}" fetchpriority="high">'
                    f'<p class="note">Full article is being written. Meanwhile, see our <a href="/reviews/{e["host"]}/">{E(hname)} review</a> and the <a href="/{e["host"]}/">{E(hname)} hub</a>.</p></article></div>')
            page(e["url"], e["title"], f"Planned article: {e['title']}", body,
                 [{"@context": "https://schema.org", "@type": "WebPage", "name": e["title"], "url": BASE + e["url"]}],
                 index=False, crumbs=crumbs, image=img, kind="stub", force_noindex=True)

    def link(e):
        mark = "" if (e["status"] == "written" or e["id"] == 1 and is_pub(H[e["host"]])) else ''
        return f'<li><a href="{e["url"]}">{E(e["title"])}</a>{mark}</li>'
    # host hubs
    for h in HOSTS:
        hs = h["slug"]
        mine = [e for e in plan if e["host"] == hs and e["status"] != "merged"]
        comps = [e for e in plan if e["sec"] == "C" and e["status"] != "merged" and hs in e["kw"].split(" vs ")]
        img = f"hub-{hs}.jpg"
        make_image(img, f"{h['name']} guides", "Reviews · Coupons · Fixes", "category", f"/{hs}/", f"Hero for {h['name']} hub")
        secs = ""
        for s, (sname, _, _) in SEC.items():
            items = comps if s == "C" else [e for e in mine if e["sec"] == s]
            secs += f"<h2>{E(h['name'])} {E(sname.lower())}</h2><ul>" + "".join(link(e) for e in items) + "</ul>"
        done = [e for e in mine if e["status"] == "written" or (e["id"] == 1 and is_pub(h))]
        sch = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": f"{h['name']} guides", "url": f"{BASE}/{hs}/"}]
        if done:
            sch.append({"@context": "https://schema.org", "@type": "ItemList", "name": f"{h['name']} articles", "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": BASE + e["url"], "name": e["title"]} for i, e in enumerate(done)]})
        body = (f'<div class="wrap narrow"><article><h1>{E(h["name"])} Reviews, Coupons, Tutorials and Fixes</h1>'
                f'<p>Everything we publish about {E(h["name"])}: pricing explained, coupons, comparisons, setup tutorials and troubleshooting. </p>'
                f'<img class="hero-img" src="/images/{img}" width="1200" height="630" alt="{E(h["name"])} guides">{secs}</article></div>')
        page(f"/{hs}/", f"{h['name']} Reviews, Coupons, Tutorials and Fixes", f"All our {h['name']} content: review, pricing, coupons, comparisons, tutorials and troubleshooting guides.",
             body, sch, index=True, crumbs=[("Home", "/"), (h["name"], f"/{hs}/")], image=img, kind="cluster")
    # comparisons hub
    comps = [e for e in plan if e["sec"] == "C" and e["status"] != "merged"]
    make_image("hub-comparisons.jpg", "Hosting comparisons", "Head to head", "compare", "/compare/", "Hero for comparisons hub")
    body = ('<div class="wrap narrow"><article><h1>Hosting Comparisons</h1><ul>' + "".join(link(e) for e in comps) + '</ul></article></div>')
    page("/compare/", "Hosting Comparisons", "Head-to-head web hosting comparisons for Hostinger, Bluehost and HostGator.", body,
         [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "Hosting Comparisons", "url": BASE + "/compare/"}],
         index=True, crumbs=[("Home", "/"), ("Comparisons", "/compare/")], image="hub-comparisons.jpg", kind="cluster")
    cl = "".join(link(e) for e in plan if e["sec"] == "B" and e["status"] != "merged")
    coupon_links = f"<h2>Coupon guides by provider</h2><ul>{cl}</ul>"
    # plan export
    with open(f"{ROOT}/content-plan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["host", "id", "section", "title", "primary_keyword", "search_intent", "url", "image_file", "status", "note"])
        for e in plan:
            sname, intent, _ = SEC[e["sec"]]
            w.writerow([e["host"], e["id"], sname, e["title"], e["kw"], intent, e["url"],
                        (f"review-{e['host']}.jpg" if e["id"] == 1 else f"{e['slug']}.jpg") if e["status"] != "merged" else "", e["status"], e["note"]])
    st = {}
    for e in plan: st[e["status"]] = st.get(e["status"], 0) + 1
    print("plan:", st)
    return coupon_links


def build():
    if os.path.exists(DIST): shutil.rmtree(DIST)
    os.makedirs(f"{DIST}/assets")
    write("/assets/style.css", CSS)
    write("/assets/search.js", JS_SEARCH)

    any_pub = any(is_pub(h) for h in HOSTS)
    make_image("home.jpg", "Independent web hosting reviews", "Reviews. Comparisons. Guides.", "home", "/", "Home hero + default social image")
    make_image("logo.jpg", NAME, "", "home", "/ (Organization logo)", "Logo used in schema")

    # ---- host review pages
    for h in HOSTS:
        url = f"/reviews/{h['slug']}/"
        img = f"review-{h['slug']}.jpg"
        make_image(img, f"{h['name']} Review", "Hosting review", "review", url, f"Hero image for {h['name']} review")
        custom_body = ""
        extra_faq = []
        cm = f"{ROOT}/content/reviews/{h['slug']}.md"
        meta = {}
        if os.path.exists(cm):
            meta, b = parse_md(cm)
            custom_body, extra_faq = md_to_html(b)
        tested = h.get("hands_on_tested")
        label = ("Hands-on review: written after using the service." if tested else
                 "Overview based on provider documentation. We have not tested this service ourselves.")
        def val(x, f=lambda v: v): return E(f(x)) if x not in (None, "") else NA
        yn = lambda v: "Yes" if v else "No"
        rows = [("Plan types", ", ".join(("VPS" if t == "vps" else t.title()) for t in h["types"])),
                ("Starting price", val(h["starting_price"])), ("Renewal price", val(h["renewal_price"])),
                ("Money-back guarantee", val(h["money_back_days"], lambda v: f"{v} days") if h["money_back_days"] else "Check the provider's site"),
                ("Free domain", yn(h["free_domain"]) if h["free_domain"] is not None else "Check the provider's site"),
                ("Free SSL", yn(h["free_ssl"]) if h["free_ssl"] is not None else "Check the provider's site"),
                ("Last verified", E(h["last_verified"]) if h["last_verified"] else "Not yet verified")]
        if h.get("sources"):
            rows.append(("Source", " ".join(f'<a href="{E(u)}" rel="noopener" target="_blank">{E(host_of(u))}</a>' for u in h["sources"])))
        tbl = '<div class="tw"><table><tbody>' + "".join(f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in rows) + "</tbody></table></div>"
        soon = "" if (custom_body and is_pub(h)) else '<p class="note">Full review is being written.</p>'
        body = (f'<div class="wrap narrow"><article><h1>{E(h["name"])} Review</h1>'
                f'<p class="meta">{E(label)} Prices change often, so confirm on the provider\'s site.</p>{DISC}'
                f'<img class="hero-img" src="/images/{img}" width="1200" height="630" alt="{E(h["name"])} review" fetchpriority="high">'
                f'<h2>{E(h["name"])} at a glance</h2>{tbl}<p>{cta(h)}</p>{soon}{custom_body}</article></div>')
        desc = meta.get("description") or f"{h['name']} hosting overview: plan types, pricing information and what to check before you buy."
        faq_schema = []
        if extra_faq and is_pub(h):
            faq_schema = [{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in extra_faq]}]
        page(url, meta.get("title") or f"{h['name']} Review", desc, body,
             schemas=[{"@context": "https://schema.org", "@type": "WebPage", "name": f"{h['name']} Review", "url": BASE + url, "description": desc,
                       "primaryImageOfPage": f"{BASE}/images/{img}", "publisher": {"@id": BASE + "/#org"}}] + faq_schema,
             index=is_pub(h), crumbs=[("Home", "/"), ("Reviews", "/reviews/"), (f"{h['name']} Review", url)], image=img, kind="review",
             updated=h["last_verified"], force_noindex=False)

    # ---- reviews hub
    make_image("reviews.jpg", "All hosting reviews", f"{len(HOSTS)} providers", "category", "/reviews/", "Reviews hub hero")
    body = (f'<div class="wrap"><article><h1>Web Hosting Reviews</h1><p class="meta">Each page says whether it is a hands-on review or an overview based on provider documentation.</p>'
            f'<div class="grid">{"".join(host_card(h) for h in HOSTS)}</div></article></div>')
    page("/reviews/", "Web Hosting Reviews", "Browse hosting provider reviews and overviews, each labelled as hands-on or based on provider documentation.",
         body, [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "Web Hosting Reviews", "url": BASE + "/reviews/"}],
         index=any_pub, crumbs=[("Home", "/"), ("Reviews", "/reviews/")], image="reviews.jpg", kind="hub")

    # ---- category pages
    for slug, title, typ, intro in CATS:
        url = f"/category/{slug}/"
        hs = [h for h in HOSTS if typ is None or typ in h["types"]]
        img = f"category-{slug}.jpg"
        make_image(img, title, f"{len(hs)} providers", "category", url, f"Hero for category {title}")
        pub = any(is_pub(h) for h in hs)
        body = (f'<div class="wrap"><article><h1>{E(title)}</h1><p>{E(intro)}</p>'
                f'<img class="hero-img" src="/images/{img}" width="1200" height="630" alt="{E(title)}">'
                f'<h2>Providers that offer {E(title.replace("Best ", "").lower())}</h2><div class="grid">{"".join(host_card(h) for h in hs)}</div></article></div>')
        page(url, title, f"{title}: providers to consider and links to our reviews. {intro}"[:300], body,
             [{"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "url": BASE + url},
              {"@context": "https://schema.org", "@type": "ItemList", "name": title, "itemListElement": [
                  {"@type": "ListItem", "position": i + 1, "url": f"{BASE}/reviews/{h['slug']}/", "name": h["name"]} for i, h in enumerate(hs)]}],
             index=pub, crumbs=[("Home", "/"), (title, url)], image=img, kind="category")

    # ---- editorial content: guides / comparisons / best
    section = {"guides": ("Guides", "guide"), "comparisons": ("Comparisons", "compare"), "best": ("Best Of", "best")}
    section_urls = {"guides": "/guides/", "comparisons": "/compare/", "best": "/best/"}
    listing = {k: [] for k in section}
    for folder, (sname, theme) in section.items():
        for p in sorted(glob.glob(f"{ROOT}/content/{folder}/*.md")):
            meta, b = parse_md(p)
            slug = os.path.basename(p)[:-3]
            url = f"{section_urls[folder]}{slug}/"
            for req in ("title", "description", "published", "updated", "image_text"):
                assert meta.get(req), f"{p}: missing front matter '{req}'"
            if meta.get("status", "published") != "published":
                continue
            htm, faq = md_to_html(b)
            img = f"{folder}-{slug}.jpg"
            make_image(img, meta["image_text"], meta.get("image_sub", ""), theme, url, f"Hero: {meta['title']}", base=f"{folder}-{slug}", n=1)
            htm = article_images(htm, f"{folder}-{slug}", meta["title"], theme, url)
            hosts_l = [x.strip() for x in meta.get("hosts", "").split(",") if x.strip()]
            for x in hosts_l: assert x in H, f"{p}: unknown host {x}"
            cards = ""
            if folder == "best" and hosts_l:
                cards = f'<div class="grid">{"".join(host_card(H[x]) for x in hosts_l)}</div>'
            kind_label = meta.get("review_basis", "")
            basis = f'<p class="meta">{E(kind_label)}</p>' if kind_label else ""
            top_block = (f"<p class=meta>Published {meta['published']} · Updated {meta['updated']} · By {E(SITE['author_name'])}</p>" + basis
                         + (DISC if has_aff(htm) or cards else "")
                         + f'<img class=hero-img src=/images/{img} width=1200 height=630 alt="{E(meta["image_text"])}" fetchpriority=high>')
            body = '<div class="wrap narrow"><article>' + htm.replace("</h1>", "</h1>" + top_block, 1) + cards + "</article></div>"
            sch = [{"@context": "https://schema.org", "@type": "Article", "headline": meta["title"], "description": meta["description"],
                    "image": f"{BASE}/images/{img}", "datePublished": meta["published"], "dateModified": meta["updated"],
                    "author": {"@type": "Organization", "name": SITE["author_name"], "url": BASE + "/author/"},
                    "publisher": {"@id": BASE + "/#org"}, "mainEntityOfPage": BASE + url}]
            if faq:
                sch.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
            if folder == "best" and hosts_l:
                sch.append({"@context": "https://schema.org", "@type": "ItemList", "name": meta["title"], "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "url": f"{BASE}/reviews/{x}/", "name": H[x]["name"]} for i, x in enumerate(hosts_l)]})
            page(url, meta["title"], meta["description"], body, sch, index=True,
                 crumbs=[("Home", "/"), (sname, section_urls[folder]), (meta["title"], url)], image=img, kind=folder,
                 updated=meta["updated"], og_type="article")
            listing[folder].append((meta["title"], url, meta["description"], words_in(htm)))
    for folder, (sname, theme) in section.items():
        items = listing[folder]
        if folder == "comparisons" or (folder in ("guides", "best") and not items): continue
        url = section_urls[folder]
        img = f"hub-{folder}.jpg"
        make_image(img, sname, "", theme, url, f"Hero for {sname} hub")
        cards = "".join(f'<a class="card" href="{u}"><h3>{E(t)}</h3><p>{E(d)}</p></a>' for t, u, d, _ in items) or "<p>Articles are coming soon.</p>"
        body = f'<div class="wrap"><article><h1>{sname}</h1><div class="grid">{cards}</div></article></div>'
        page(url, sname, f"{sname} from {NAME}: independent hosting content.", body,
             [{"@context": "https://schema.org", "@type": "CollectionPage", "name": sname, "url": BASE + url}],
             index=bool(items), crumbs=[("Home", "/"), (sname, url)], image=img, kind="hub")

    coupon_links = build_plan()

    # ---- compare tool
    make_image("tool-compare.jpg", "Hosting comparison table", "Filter by plan type", "tool", "/tools/compare/", "Compare tool hero")
    data = [{k: h[k] for k in ("slug", "name", "types", "starting_price", "renewal_price", "money_back_days", "last_verified", "status")} for h in HOSTS]
    tool_js = ("<script>var D=" + json.dumps(data) + ";var T=document.getElementById('t'),s=document.getElementById('s'),f=document.getElementById('f');"
               "var NA=\"Check the provider's site\";function r(){var q=s.value.toLowerCase(),y=f.value;T.innerHTML=D.filter(function(h){return(!y||h.types.indexOf(y)>-1)&&h.name.toLowerCase().indexOf(q)>-1})"
               ".map(function(h){return'<tr><td><a href=\"/reviews/'+h.slug+'/\">'+h.name+'</a></td><td>'+h.types.join(', ')+'</td><td>'+(h.starting_price||NA)+'</td><td>'+(h.renewal_price||NA)+'</td><td>'+(h.money_back_days?h.money_back_days+' days':NA)+'</td><td>'+(h.last_verified||'Not yet verified')+'</td></tr>'}).join('')}"
               "s.oninput=r;f.onchange=r;r()</script>")
    body = ('<div class="wrap"><article><h1>Hosting Comparison Table</h1><p>Filter providers by plan type. Figures come from our data file and show when each provider was last verified.</p>'
            '<div class="filters"><input id="s" placeholder="Search provider" aria-label="Search provider"><select id="f" aria-label="Plan type"><option value="">All plan types</option>'
            '<option value="shared">Shared</option><option value="wordpress">WordPress</option><option value="vps">VPS</option><option value="cloud">Cloud</option><option value="dedicated">Dedicated</option></select></div>'
            '<div class="tw"><table><thead><tr><th>Provider</th><th>Plan types</th><th>Starting price</th><th>Renewal price</th><th>Money-back</th><th>Last verified</th></tr></thead><tbody id="t"></tbody></table></div></article></div>')
    page("/tools/compare/", "Hosting Comparison Table", "Compare web hosting providers by plan type, price and guarantee, with a last-verified date for every provider.",
         body, [{"@context": "https://schema.org", "@type": "WebPage", "name": "Hosting Comparison Table", "url": BASE + "/tools/compare/"}],
         index=any_pub, crumbs=[("Home", "/"), ("Compare Hosting", "/tools/compare/")], image="tool-compare.jpg", kind="tool", extra_js=tool_js)

    # ---- coupons
    make_image("coupons.jpg", "Hosting coupons", "Verified offers only", "coupon", "/coupons/", "Coupons hub hero")
    rows = ""
    for c in COUPONS:
        hh = H.get(c["host"])
        if hh:
            rows += f'<tr><td><a href="/reviews/{hh["slug"]}/">{E(hh["name"])}</a></td><td><code>{E(c.get("code",""))}</code></td><td>{E(c.get("description",""))}</td><td>{E(c.get("expires", EXP_DEFAULT))}</td><td>{E(c.get("last_verified",""))}</td></tr>'
    tb = (f'<div class="tw"><table><thead><tr><th>Provider</th><th>Code</th><th>Offer</th><th>Expires</th><th>Last verified</th></tr></thead><tbody>{rows}</tbody></table></div>' if rows
          else "<p>We have no verified coupons to list right now. We only publish offers we have checked.</p>")
    body = f'<div class="wrap narrow"><article><h1>Web Hosting Coupons</h1>{DISC}<p>Offers change often and may expire without notice. Confirm terms on the provider\'s site.</p>{tb}{coupon_links}</article></div>'
    page("/coupons/", "Web Hosting Coupons", "Verified web hosting coupons and deals, each with an expiry and last-verified date.", body,
         [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "Web Hosting Coupons", "url": BASE + "/coupons/"}],
         index=bool(rows), crumbs=[("Home", "/"), ("Coupons", "/coupons/")], image="coupons.jpg", kind="hub")

    # ---- trust pages
    ctc = SITE.get("contact_email")
    for p in sorted(glob.glob(f"{ROOT}/content/pages/*.md")):
        meta, b = parse_md(p)
        slug = os.path.basename(p)[:-3]
        htm, _ = md_to_html(b)
        if slug == "contact":
            htm = htm.replace("<p>CONTACT_BLOCK</p>", f'<p>Email: <a href="mailto:{E(ctc)}">{E(ctc)}</a></p>' if ctc else "<p>Contact details are coming soon.</p>")
        if slug == "author":
            bio = SITE.get("author_bio")
            htm = htm.replace("<p>This page will describe the author or team behind PrimeTech Hosting, including real experience with websites and hosting.</p>",
                              f"<p>{E(bio)}</p>" if bio else "<p>Author details are coming soon.</p>")
        url = f"/{slug}/"
        idx = not ((slug == "contact" and not ctc) or (slug == "author" and not SITE.get("author_bio")))
        stype = {"about": "AboutPage", "contact": "ContactPage"}.get(slug, "WebPage")
        body = f'<div class="wrap narrow"><article>{htm}</article></div>'
        page(url, meta["title"], meta["description"], body,
             [{"@context": "https://schema.org", "@type": stype, "name": meta["title"], "url": BASE + url, "description": meta["description"]}],
             index=idx, crumbs=[("Home", "/"), (meta["title"], url)], kind="trust")

    # ---- search + sitemap html + 404 + home
    body = ('<div class="wrap narrow"><article><h1>Search</h1><div class="filters"><input id="q" placeholder="Search reviews, guides, comparisons" '
            'style="flex:1" aria-label="Search"></div><div class="grid" id="res"></div></article></div>')
    page("/search/", "Search", "Search PrimeTech Hosting reviews, guides and comparisons.", body, index=True,
         crumbs=[("Home", "/"), ("Search", "/search/")], extra_js='<script src="/assets/search.js" defer></script>', search=False)

    # home
    hub_cards = "".join(f'<a class="card" href="/{h["slug"]}/"><h3>{E(h["name"])}</h3><p>Review, pricing, coupons, tutorials and fixes</p></a>' for h in HOSTS)
    body = (f'<section class="hero"><div class="wrap"><h1>Hostinger, Bluehost and HostGator: reviews, prices, coupons and fixes</h1>'
            f'<p>Independent guides to three popular hosting providers. Every page says what we tested and what comes from provider documentation.</p>'
            f'<form class="sbox" action="/search/" method="get"><input name="q" placeholder="Search reviews, coupons and tutorials" aria-label="Search"><button class="btn" type="submit">Search</button></form></div></section>'
            f'<section class="sec"><div class="wrap"><h2>Choose a provider</h2><div class="grid">{hub_cards}</div>'
            f'<p><a class="btn" href="/tools/compare/">Open the comparison table</a> <a class="btn alt" style="border:1px solid #dfe7ef" href="/compare/">Read comparisons</a></p></div></section>'
            f'<section class="sec"><div class="wrap narrow"><h2>How we review</h2><p>We separate hands-on reviews from overviews based on provider documentation, keep prices in one verified data file, and never invent ratings or test results. Read our <a href="/review-methodology/">review methodology</a> and <a href="/editorial-policy/">editorial policy</a>.</p></div></section>')
    home_schema = [{"@context": "https://schema.org", **ORG},
                   {"@context": "https://schema.org", "@type": "WebSite", "@id": BASE + "/#website", "name": NAME, "url": BASE + "/",
                    "description": SITE["tagline"], "publisher": {"@id": BASE + "/#org"}, "inLanguage": "en",
                    "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint", "urlTemplate": BASE + "/search/?q={search_term_string}"},
                                        "query-input": "required name=search_term_string"}}]
    page("/", f"{NAME}: Hostinger, Bluehost and HostGator Reviews and Guides", "Independent reviews, pricing explanations, coupons, tutorials and troubleshooting guides for Hostinger, Bluehost and HostGator.",
         body, home_schema, index=True, image="home.jpg", kind="home", search=False)

    write("/404.html", f'<!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Page not found | {E(NAME)}</title><meta name="robots" content="noindex"><link rel="stylesheet" href="/assets/style.css"></head><body>{nav_html()}<div class="wrap narrow"><article><h1>Page not found</h1><p>That page does not exist. Try the <a href="/">home page</a>, the <a href="/reviews/">reviews</a> or <a href="/search/">search</a>.</p></article></div>{footer_html()}</body></html>')

    # sitemap html (indexable pages only)
    live = [p for p in PAGES if p["index"]]
    groups = {}
    for p in live: groups.setdefault(p["kind"], []).append(p)
    names = {"home": "Home", "hub": "Hubs", "category": "Categories", "review": "Reviews", "tool": "Tools", "trust": "About and policies", "guides": "Guides", "comparisons": "Comparisons", "best": "Best of", "article": "Articles", "cluster": "Provider hubs"}
    sm = "".join(f"<h2>{names.get(k,k)}</h2><ul>" + "".join(f'<li><a href="{p["url"]}">{E(p["title"])}</a></li>' for p in v) + "</ul>" for k, v in groups.items())
    page("/sitemap/", "Sitemap", "All pages on PrimeTech Hosting.", f'<div class="wrap narrow"><article><h1>Sitemap</h1>{sm}</article></div>',
         index=True, crumbs=[("Home", "/"), ("Sitemap", "/sitemap/")], search=False)

    # xml sitemap / robots / headers / search index
    xs = "".join(f"<url><loc>{BASE}{p['url']}</loc>" + (f"<lastmod>{p['updated']}</lastmod>" if p["updated"] else "") + "</url>" for p in live)
    write("/sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xs}</urlset>')
    write("/robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    write("/search-index.json", json.dumps(SEARCH, ensure_ascii=False))
    write("/_headers", "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n/images/*\n  Cache-Control: public, max-age=604800\n")

    with open(f"{ROOT}/image-map.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["image_file", "used_on_page", "purpose", "text_on_image", "source", "name_for_your_jpg"]); w.writerows(IMAGES)

    print(f"pages built: {len(PAGES)} | indexable: {len(live)} | noindex drafts: {len(PAGES)-len(live)} | images: {len(IMAGES)}")
    for k, v in listing.items():
        for t, u, d, wc in v: print(f"  {u} words={wc}")

if __name__ == "__main__":
    build()
