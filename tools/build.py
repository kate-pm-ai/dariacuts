#!/usr/bin/env python3
"""Сборка страниц dariacuts.com под устройство сайта Алексея.

Вход:  pages/*.html (согласованные страницы как есть) + site.json.
Выход: docs/  - предпросмотр на GitHub Pages (noindex, пути с приставкой /dariacuts)
       dist/  - архив для Алексея (пути от корня сайта, без noindex) + zip

Стандарт Алексея (иконки, шрифты, @font-face) берется дословно с живой главной
и хранится в tools/standard/. Обновить: build.py --refresh-standard
"""
import base64, hashlib, html, io, json, re, shutil, sys, urllib.request, zipfile
from datetime import date
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
STD = ROOT / "tools" / "standard"
CFG = json.loads((ROOT / "site.json").read_text())
AVIF_QUALITY = 80

GOOGLE_FONTS_RE = re.compile(
    r'[ \t]*<link[^>]*(?:fonts\.googleapis\.com|fonts\.gstatic\.com)[^>]*>\s*\n?')
ROBOTS_RE = re.compile(r'[ \t]*<meta name="robots" content="[^"]*">\s*\n?')
DATA_IMG_RE = re.compile(r'<img\b[^>]*?\ssrc="data:image/[a-z+]+;base64,([^"]+)"[^>]*>')
LOCAL_IMG_RE = re.compile(r'<img\b[^>]*?\ssrc="img/([^"]+)"[^>]*>')


def refresh_standard():
    live = urllib.request.urlopen(CFG["site"] + "/").read().decode()
    head = live.split("</head>")[0]
    start = head.index('<link rel="icon" type="image/x-icon"')
    end = head.index(">", head.index('href="/site.webmanifest"')) + 1
    icons = head[start:end]
    p1 = head.index('rel="preload"')
    p1 = head.rindex("<link", 0, p1)
    p2 = head.index(">", head.index('rel="preload"', head.index('rel="preload"') + 1)) + 1
    preload = head[p1:p2]
    faces = re.findall(r"@font-face\s*{[^}]*}", live)
    STD.mkdir(parents=True, exist_ok=True)
    (STD / "icons.html").write_text(icons + "\n")
    (STD / "preload.html").write_text(preload + "\n")
    (STD / "font-face.css").write_text("\n".join(faces) + "\n")
    print(f"стандарт обновлен: иконки, preload, {len(faces)} @font-face")


def head_block():
    icons = (STD / "icons.html").read_text().strip()
    preload = (STD / "preload.html").read_text().strip()
    faces = (STD / "font-face.css").read_text().strip()
    return f"{icons}\n{preload}\n<style>\n{faces}\n</style>\n"


def label_of(tag, fallback):
    m = re.search(r'\salt="([^"]*)"', tag)
    text = html.unescape(m.group(1)) if m and m.group(1) else fallback
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or fallback


class Images:
    """Пул картинок работ: одинаковые байты -> один файл."""

    def __init__(self):
        self.by_hash, self.files = {}, {}

    def add(self, raw, label):
        h = hashlib.sha1(raw).hexdigest()
        if h in self.by_hash:
            return self.by_hash[h]
        name = CFG["image_prefix"] + label
        n, base = 2, name
        while name + ".avif" in self.files:
            name, n = f"{base}-{n}", n + 1
        img = Image.open(io.BytesIO(raw))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "AVIF", quality=AVIF_QUALITY)
        fname = name + ".avif"
        self.files[fname] = buf.getvalue()
        self.by_hash[h] = fname
        return fname


def transform(page, src_html, images):
    out = src_html
    # 1. шрифты Google -> стандарт Алексея (иконки, preload, @font-face)
    first = GOOGLE_FONTS_RE.search(out)
    if not first:
        raise SystemExit(f"{page['id']}: не найдены строки Google Fonts")
    out = out[:first.start()] + "__HEAD_BLOCK__\n" + out[first.start():]
    out = GOOGLE_FONTS_RE.sub("", out).replace("__HEAD_BLOCK__\n", head_block(), 1)

    # 2. картинка для соцсетей
    og = CFG["og_image"]
    out = re.sub(r'(<meta property="og:image" content=")[^"]*(")', rf"\g<1>{og}\2", out)
    out = re.sub(r'("image"\s*:\s*")https://dariacuts\.com/images/og-cover\.jpg(")', rf"\g<1>{og}\2", out)
    if 'name="twitter:image"' not in out:
        out = re.sub(r'(<meta name="twitter:description"[^>]*>)',
                     rf'\1\n  <meta name="twitter:image" content="{og}" />', out, count=1)
    else:
        out = re.sub(r'(<meta name="twitter:image" content=")[^"]*(")', rf"\g<1>{og}\2", out)

    # 3. адрес страницы
    url = page["url"]
    out = re.sub(r'(<link rel="canonical" href=")[^"]*(")', rf"\g<1>{url}\2", out)
    out = re.sub(r'(<meta property="og:url" content=")[^"]*(")', rf"\g<1>{url}\2", out)

    # 4. картинки работ: base64 и img/ -> /assets/images/*.avif
    def sub_data(m):
        raw = base64.b64decode(m.group(1))
        fname = images.add(raw, label_of(m.group(0), page["id"]))
        tag = m.group(0)
        s = tag.index('src="') + 5
        e = tag.index('"', s)
        return tag[:s] + "/assets/images/" + fname + tag[e:]

    out = DATA_IMG_RE.sub(sub_data, out)

    def sub_local(m):
        path = ROOT / Path(page["src"]).parent / "img" / m.group(1)
        fname = images.add(path.read_bytes(), label_of(m.group(0), Path(m.group(1)).stem))
        return m.group(0).replace(f'src="img/{m.group(1)}"', f'src="/assets/images/{fname}"')

    out = LOCAL_IMG_RE.sub(sub_local, out)
    # крошечная svg-текстура фона в CSS (data:image/svg+xml, без base64) - часть дизайна, остается
    if re.search(r"data:image/[a-z+]+;base64", out):
        raise SystemExit(f"{page['id']}: осталась зашитая base64-картинка вне тегов img, нужен разбор руками")
    return out


def with_prefix(text, prefix):
    text = re.sub(r'((?:src|href)=")/(?!/)', rf"\1{prefix}/", text)
    return re.sub(r"(url\(['\"]?)/(?!/)", rf"\1{prefix}/", text)


def out_path(base, page):
    return base / page["slug"] / "index.html" if page["slug"] else base / "index.html"


def main():
    if "--refresh-standard" in sys.argv or not (STD / "icons.html").exists():
        refresh_standard()
    images = Images()
    built = {p["id"]: transform(p, (ROOT / p["src"]).read_text(), images) for p in CFG["pages"]}

    stamp = date.today().isoformat()
    docs = ROOT / "docs"
    dist = ROOT / "dist" / f"dariacuts-pages-{stamp}"
    for d in (docs, dist):
        if d.exists():
            shutil.rmtree(d)  # оба каталога целиком генерируются этим скриптом
    for page in CFG["pages"]:
        prod = built[page["id"]]
        archive = out_path(dist, page)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(ROBOTS_RE.sub("", prod, count=1))
        prev = out_path(docs, page)
        prev.parent.mkdir(parents=True, exist_ok=True)
        prev.write_text(with_prefix(prod, CFG["preview_prefix"]))
    for base in (dist, docs):
        (base / "assets" / "images").mkdir(parents=True, exist_ok=True)
        for fname, data in images.files.items():
            (base / "assets" / "images" / fname).write_bytes(data)
    shutil.copytree(ROOT / "vendor", docs, dirs_exist_ok=True)
    (docs / ".nojekyll").write_text("")

    readme = (ROOT / "tools" / "README-alexey.txt").read_text()
    pages_list = "\n".join(f"  {p['url']}  ->  {out_path(Path(''), p)}" for p in CFG["pages"])
    imgs = "\n".join(f"  assets/images/{f}" for f in sorted(images.files))
    (dist / "README.txt").write_text(readme.format(pages=pages_list, images=imgs))
    zpath = dist.with_suffix(".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(dist.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(dist))
    print(f"страниц: {len(built)}, картинок: {len(images.files)}")
    print(f"предпросмотр: {docs}\nархив: {zpath}")


if __name__ == "__main__":
    main()
