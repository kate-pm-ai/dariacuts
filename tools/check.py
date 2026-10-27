#!/usr/bin/env python3
"""Проверка сборки: каждая страница архива против согласованного оригинала.

Запуск после build.py. Печатает по каждой странице «сошлось N из N»
и список провалов. Код выхода 1, если хоть что-то не сошлось.
"""
import html, json, re, sys, urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "site.json").read_text())
STD = ROOT / "tools" / "standard"
SKIP_TAGS = {"script", "style", "noscript", "template"}
_live_cache = {}


class Text(HTMLParser):
    """Видимый текст + alt картинок, без скриптов и стилей."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.h1 = [], 0, []
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        if tag == "h1":
            self._in_h1 = True
            self.h1.append("")
        a = dict(attrs)
        if tag == "img" and a.get("alt"):
            self.parts.append("[alt] " + a["alt"])

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip:
            self.skip -= 1
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        if self.skip:
            return
        self.parts.append(data)
        if self._in_h1:
            self.h1[-1] += data


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def parse(h):
    t = Text()
    t.feed(h)
    return norm(" ".join(t.parts)), [norm(x) for x in t.h1]


def meta(h, pattern):
    m = re.search(pattern, h)
    return m.group(1) if m else None


def live_ok(path):
    if path not in _live_cache:
        try:
            req = urllib.request.Request(CFG["site"] + path, method="HEAD")
            _live_cache[path] = urllib.request.urlopen(req, timeout=15).status == 200
        except Exception:
            _live_cache[path] = False
    return _live_cache[path]


def local_refs(h):
    refs = re.findall(r'(?:src|href)="(/[^/"][^"]*|/)"', h)
    refs += re.findall(r"url\(['\"]?(/[^/'\")][^'\")]*)", h)
    return sorted(set(r.split("#")[0].split("?")[0] for r in refs))


def check_page(page, dist, docs):
    src = (ROOT / page["src"]).read_text()
    arch_path = dist / page["slug"] / "index.html" if page["slug"] else dist / "index.html"
    out = arch_path.read_text()
    prev = (docs / arch_path.relative_to(dist)).read_text()
    og = CFG["og_image"]
    res = []

    def ok(name, cond, detail=""):
        res.append((name, bool(cond), detail))

    ok("нет Google Fonts", "fonts.googleapis.com" not in out and "fonts.gstatic.com" not in out)
    ok("иконки сайта и manifest как на живом сайте", (STD / "icons.html").read_text().strip() in out)
    ok("шрифты Алексея (preload + 9 @font-face)",
       (STD / "preload.html").read_text().strip() in out and out.count("@font-face") == 9)
    ok("og:image = og-cover.webp", meta(out, r'og:image" content="([^"]+)"') == og)
    ok("twitter:image = og-cover.webp", meta(out, r'twitter:image" content="([^"]+)"') == og)
    ok("YouTube встроен как на живом сайте (youtube.com/embed)", "youtube-nocookie.com" not in out)
    ok("нет зашитых base64-картинок", not re.search(r"data:image/[a-z+]+;base64", out))

    missing = []
    for ref in local_refs(out):
        if ref == "/":
            continue
        if not (dist / ref.lstrip("/")).exists() and not live_ok(ref):
            missing.append(ref)
    ok("все локальные ссылки ведут на файл (архив или живой сайт)", not missing, ", ".join(missing))

    imgs = re.findall(r'<img\b[^>]*\ssrc="([^"]+)"', out)
    raster = [s for s in imgs if not s.startswith("http")]
    ok("картинки работ в avif и в /assets/images/",
       all(s.startswith("/assets/images/") and s.endswith(".avif") for s in raster),
       ", ".join(s for s in raster if not s.endswith(".avif")))

    btt = (STD / "back-to-top.html").read_text()
    ok("кнопка «наверх» как на живом сайте", btt in out and out.count('id="backToTop"') == 1)
    reviews = json.loads((ROOT / "reviews.json").read_text())
    sec = lambda h: re.search(r'<section[^>]*id="reviews".*?</section>', h, re.S)
    rv = sec(out).group(0) if sec(out) else ""
    ok("отзывы: только настоящие из reviews.json, дословно",
       rv.count('class="review"') == len(reviews)
       and all(html.escape(x, quote=False) in rv for r in reviews for x in r["quote"].split("\n"))
       and all(html.escape(r["name"]) in rv for r in reviews)
       and all("<br>".join(html.escape(x, quote=False) for x in r["quote"].split("\n")) in rv for r in reviews))
    ok("точки слайдера внутри блока отзывов", len(reviews) < 2 or '</article></div><div class="review-dots"' in rv)
    strip = lambda h: re.sub(r'<section[^>]*id="reviews".*?</section>', "", h, count=1, flags=re.S)
    t_src, h1_src = parse(strip(src))
    t_out, h1_out = parse(strip(out.replace(btt, "")))
    ok("ровно один H1", len(h1_out) == 1, str(len(h1_out)))
    ok("H1 как в оригинале", h1_out == h1_src)
    ok("title как в оригинале", meta(out, r"<title>(.*?)</title>") == meta(src, r"<title>(.*?)</title>"))
    ok("description как в оригинале",
       meta(out, r'name="description" content="([^"]*)"') == meta(src, r'name="description" content="([^"]*)"'))
    ok("видимый текст совпадает на 100%", t_out == t_src,
       "" if t_out == t_src else f"длина {len(t_src)} -> {len(t_out)}")

    def norm_urls(x):
        for p in CFG["pages"]:
            if p["slug"]:
                x = re.sub(re.escape(f'{CFG["site"]}/{p["slug"]}') + r'/?(?=")', p["url"], x)
        return x
    ld = lambda h: [norm_urls(x).replace("https://dariacuts.com/images/og-cover.jpg", og)
                    for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]
    if page["id"] == "home":
        live_ld = (STD / "home-schema.html").read_text().strip()
        faq = lambda h: [x for x in ld(h) if '"FAQPage"' in x]
        ok("микроразметка главной: блок Алексея дословно + наш FAQ", live_ld in out and faq(out) == faq(src)
           and len(re.findall(r'application/ld\+json', out)) == 2)
    else:
        ok("микроразметка не изменилась (кроме адреса картинки)", ld(out) == ld(src))

    for marker in ("GTM-M48NZGMV", "cookieconsent@3.1.0", "Cookie settings", "Reject"):
        ok(f"на месте {marker}", out.count(marker) == src.count(marker) and out.count(marker) > 0)

    ok("canonical = адрес из ТЗ", meta(out, r'rel="canonical" href="([^"]+)"') == page["url"])
    ok("og:url = адрес из ТЗ", meta(out, r'og:url" content="([^"]+)"') == page["url"])
    stray = [u for p in CFG["pages"] if p["slug"]
             for u in re.findall(re.escape(f'{CFG["site"]}/{p["slug"]}') + r'/?(?=["\s<])', out) if u != p["url"]]
    ok("адреса страниц везде в одном варианте", not stray, ", ".join(sorted(set(stray))))
    ok("в архиве нет noindex", "noindex" not in out)
    ok("в предпросмотре noindex стоит", 'content="noindex,nofollow,noarchive"' in prev)

    p = CFG["preview_prefix"]
    unprefixed = re.sub(rf'((?:src|href)="){re.escape(p)}/', r"\1/", prev)
    unprefixed = re.sub(rf"(url\(['\"]?){re.escape(p)}/", r"\1/", unprefixed)
    unprefixed = re.sub(r'[ \t]*<meta name="robots" content="[^"]*">\s*\n?', "", unprefixed, count=1)
    ok("предпросмотр = архив (кроме приставки путей и noindex)", unprefixed == out)
    return res


def main():
    dists = sorted((ROOT / "dist").glob("dariacuts-pages-*/"))
    if not dists:
        sys.exit("нет сборки, сначала tools/build.py")
    dist, docs = dists[-1], ROOT / "docs"
    failed = 0
    for page in CFG["pages"]:
        res = check_page(page, dist, docs)
        good = sum(1 for _, c, _ in res if c)
        print(f"{page['id']}: сошлось {good} из {len(res)}")
        for name, c, detail in res:
            if not c:
                failed += 1
                print(f"   ПРОВАЛ: {name} {detail}")
    print("ИТОГ:", "всё сошлось" if not failed else f"провалов {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
