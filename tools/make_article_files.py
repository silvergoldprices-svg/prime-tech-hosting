#!/usr/bin/env python3
"""Creates one empty article file per draft title: content-ar/articles/<id>-<slug>.md   (never overwrites).
Write the article under the front matter and push - it is published automatically once it has 300+ words."""
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
reg = json.loads((ROOT/"content-registry"/"arabic-planned-articles.json").read_text(encoding="utf-8"))["articles"]
CO = [("هوستنجر","hostinger"),("هوست جيتور","hostgator"),("بلوهوست","bluehost")]
KW = [("مراجعة","review"),("أسعار|سعر|تكلفة","pricing"),("جيدة للمبتدئين","for-beginners"),("لوحة تحكم|لوحة إدارة","control-panel"),("طريقة شراء|شراء استضافة","buy"),
 ("تثبيت قالب","install-theme"),("تثبيت","install"),("ربط الدومين","connect-domain"),("نقل الدومين","transfer-domain"),("نقل موقع","migrate-site"),
 ("بريد","email"),("SSL","ssl"),("نسخة احتياطية|نسخ احتياطي|استعادة","backup"),("تسريع|سرعة","speed"),("حماية|أمان","security"),
 ("حل مشكلة|إصلاح|حل ","fix"),("File Manager","file-manager"),("قاعدة بيانات|MySQL","mysql"),("PHP","php"),("Subdomain","subdomain"),
 ("استرداد","refund"),("إلغاء","cancel"),("تجديد","renewal"),("دومين مجاني|نطاق مجاني","free-domain"),("ترقية","upgrade"),("الفرق بين باقات","plans-difference"),
 ("مقارنة| أم ","vs"),("أفضل","best"),("مناسبة|يمكن استضافة|تسمح|تدعم","suitable"),("المواقع العربية","arabic-sites"),("الشركات","business-sites"),
 ("الأفلييت|التسويق بالعمولة","affiliate"),("المتاجر|متجر","store"),("الاشتراك السنوي","annual-plan"),("عدم ظهور|عدم فتح","site-not-loading"),
 ("قالب","theme"),("إضافة","plugin"),("شرح","guide"),("إعدادات","settings")]
used=set(); made=0
for a in reg:
    t=a["title"]; parts=[]
    for ar,en in CO:
        if (ar in t or en in t.lower()) and en not in parts: parts.append(en)
    for pat,en in KW:
        if re.search(pat,t) and en not in parts: parts.append(en)
    for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]+",t):
        w=w.lower().strip("-")
        if w not in parts and w not in ("for","and","in","pro","free"): parts.append(w)
    slug=re.sub(r"[^a-z0-9]+","-","-".join(parts[:7]).lower()).strip("-") or f"article-{a['id']}"
    if slug in used or slug in ("about","contact","search","category","terms","sitemap","en","assets","images"): slug=f"{slug}-{a['id']}"
    used.add(slug); a["slug_clean"]=slug
    f=ROOT/"content-ar"/"articles"/f"{a['id']:03d}-{slug}.md"
    if f.exists(): continue
    f.write_text(f"---\ntitle: {json.dumps(t,ensure_ascii=False)}\nslug: {slug}\ncategory: {a['category']}\nregistry_id: {a['id']}\n# description: وصف قصير (اختياري - لو سيبته فاضي بيتاخد من أول المقال)\n# published: 2026-11-10   (اختياري - تاريخ النشر، الافتراضي تاريخ أول بناء)\n---\n",encoding="utf-8"); made+=1
print("created",made)
