#!/usr/bin/env python3
"""Собрать страницу услуги из блоков готовой страницы (pages/youtube.html) и текста .md.

Код блоков берется из шаблона как есть: меняется только текст, видео и адреса.
Новых блоков и классов скрипт создать не может.

Видео: {"id": ...} в плане = YouTube из шаблона; {"from": "<data-title на сайте>"} = блок
article.work целиком с той страницы pages/, где эта работа уже стоит (YouTube или Vimeo),
меняются только подпись, надпись над ней, описание и alt.

  python3 tools/assemble.py plans/podcast.json
"""
import html, json, re, sys, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "pages" / "youtube.html"
OLD_URL = "https://dariacuts.com/youtube-video-editing-services/"
WA = "https://wa.me/34687631622?text="


def esc(s):
    return html.escape(s, quote=False)


def parse_md(path):
    """md -> meta + H1 + список H2-секций: абзацы, H3-карточки, жирные строки-кнопки."""
    text = Path(path).read_text().split("\n---\n")[0]
    meta = dict(re.findall(r"<!--\s*(\w+):\s*(.*?)\s*-->", text))
    text = re.sub(r"<!--.*?-->", "", text)
    secs, cur = [], None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            cur = {"h": line[2:], "paras": [], "items": [], "bold": []}
            secs.append(cur)
        elif line.startswith("## "):
            cur = {"h": line[3:], "paras": [], "items": [], "bold": []}
            secs.append(cur)
        elif line.startswith("### "):
            cur["items"].append({"h": line[4:], "p": []})
        elif line.startswith("**") and line.endswith("**"):
            cur["bold"].append([b.strip() for b in re.findall(r"\*\*(.+?)\*\*", line)])
        elif cur["items"]:
            cur["items"][-1]["p"].append(line)
        else:
            cur["paras"].append(line)
    return meta, secs[0], secs[1:]


def template_blocks():
    src = TEMPLATE.read_text()
    lines = src.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith('<section class="hero"'))
    foot = next(i for i, l in enumerate(lines) if l.startswith("<footer"))
    return src, lines, start, foot


def pick(pattern, s):
    m = re.search(pattern, s, re.S)
    if not m:
        raise SystemExit(f"в шаблоне не найден кусок: {pattern[:60]}")
    return m.group(0)


def btn(href_wa, label):
    return (f'<div class="ctas"><a class="btn btn-primary" href="{href_wa}" '
            f'data-contact="whatsapp">{esc(label)}</a></div>')


def site_work(title):
    """Блок article.work с этой работой с любой страницы сайта (первая страница, где он есть)."""
    for f in sorted((ROOT / "pages").glob("*.html")):
        for m in re.finditer(r'<article class="work">.*?</article>', f.read_text(), re.S):
            if f'data-title="{title}"' in m.group(0):
                return m.group(0)
    raise SystemExit(f"на сайте нет работы {title}")


def split_cta(pair):
    """['Have a Recorded Episode Ready? Send Your Brief.'] -> ('Have a Recorded Episode Ready?', 'Send Your Brief.')
    ['Already Shot Your Music Video?', 'Send Your Brief'] -> как есть (две жирные части в строке)"""
    if len(pair) > 1:
        return pair[0], pair[1]
    s = pair[0]
    q = s.index("?") + 1
    return s[:q].strip(), s[q:].strip()


def build(plan_path):
    plan = json.loads(Path(plan_path).read_text())
    meta, hero, secs = parse_md(ROOT / plan["text"])
    src, lines, start, foot = template_blocks()
    T = {k: lines[start + i] for i, k in enumerate(
        ["hero", "story", "formats", "work", "included", "process", "about", "reviews", "faq", "final"])}
    wa = WA + urllib.parse.quote(plan["wa_text"])

    def img_for(vid):
        m = re.search(r'data-video="[^"]*/' + re.escape(vid) + r'".*?<img src="([^"]+)"', src, re.S)
        if not m:
            raise SystemExit(f"в шаблоне нет превью для видео {vid}")
        return m.group(1)
    by_h = {s["h"]: s for s in secs}
    out = []

    def sec(name):
        return by_h[plan["blocks"][name]]

    # --- hero
    h = T["hero"]
    tpl_btn_wa = re.search(r'href="(https://wa\.me/[^"]+)"', h).group(1)
    # hero_video: null -> справа только цифры (нет подтвержденной релевантной работы для первого экрана)
    video = plan["videos"][plan["hero_video"]] if plan.get("hero_video") else None
    if video is None:
        hv = None
    elif "from" in video:
        a = site_work(video["from"])
        hv = {k: re.search(k + r'="([^"]+)"', a).group(1) for k in ("data-video", "data-original")}
        hv["img"] = re.search(r'<img src="([^"]+)"', a).group(1)
    else:
        hv = {"data-video": "https://www.youtube-nocookie.com/embed/" + video["id"],
              "data-original": "https://www.youtube.com/watch?v=" + video["id"], "img": img_for(video["id"])}
    hb = (f'<section class="hero" id="top"><div class="wrap hero-grid"><div class="hero-copy">'
          f'<p class="eyebrow">{esc(plan["hero_eyebrow"])}</p><h1>{esc(hero["h"])}</h1>'
          f'<p class="hero-intro">{esc(hero["paras"][0])}</p><ul class="hero-benefits">'
          + "".join(f"<li>{esc(b)}</li>" for b in plan["hero_benefits"]) + "</ul>"
          f'<div class="ctas"><a class="btn btn-primary" href="{wa}" data-contact="whatsapp">{esc(hero["bold"][0][0])}</a>'
          f'<a class="btn btn-ghost" href="#work">{esc(hero["bold"][0][1])}</a></div>'
          f'<p class="first-message">{esc(hero["paras"][1])}</p></div><div class="hero-evidence">'
          + ("" if hv is None else
             f'<button class="video-launch hero-video" type="button" data-video="{hv["data-video"]}" '
             f'data-title="{esc(plan["hero_video"])}" data-original="{hv["data-original"]}" '
             f'aria-label="Play {esc(plan["hero_video"])}"><img src="{hv["img"]}" alt="{esc(video["hero_alt"])}">'
             f'<span class="video-play" aria-hidden="true">▶</span></button>'
             f'<p class="video-caption">{esc(plan["hero_video"])} <span>{esc(plan.get("hero_caption", "Video editing by Daria"))}</span></p>')
          + pick(r'<div class="hero-facts">.*?</div>', h) +
          f'</div></div><div class="wrap hero-context"><p>{esc(hero["paras"][2])}</p></div></section>')
    out.append(hb)

    # --- story: H2 + абзацы + цитата-кнопка
    s = sec("story")
    q, b = split_cta(s["bold"][0])
    out.append(f'<section class="section"><div class="wrap story-grid"><div><p class="eyebrow">{esc(plan["eyebrows"]["story"])}</p>'
               f'<h2>{esc(s["h"])}</h2>' + "".join(f'<p class="lead">{esc(p)}</p>' for p in s["paras"]) +
               f'</div><div class="story-quote">{esc(q)}{btn(wa, b)}</div></div></section>')

    icons = re.findall(r'<article class="service">(<svg.*?</svg>)', T["formats"] + T["included"], re.S)

    def cards(items, icon_from=0):
        return '<div class="services">' + "".join(
            f'<article class="service">{icons[(icon_from + i) % len(icons)]}<h3>{esc(it["h"])}</h3>'
            + "".join(f"<p>{esc(p)}</p>" for p in it["p"]) + "</article>" for i, it in enumerate(items)) + "</div>"

    # --- formats: карточки + промежуточная кнопка
    s = sec("formats")
    q, b = split_cta(s["bold"][0])
    out.append(f'<section class="section section-paper" id="formats"><div class="wrap"><div class="section-head"><div>'
               f'<p class="eyebrow">{esc(plan["eyebrows"]["formats"])}</p><h2>{esc(s["h"])}</h2></div></div>'
               + cards(s["items"]) + f'<div class="{plan.get("formats_cta_class", "story-quote")}">{esc(q)}{btn(wa, b)}</div></div></section>')

    # --- work: тёмный блок с видео
    s = sec("work")
    works = ""
    for it in s["items"]:
        v = plan["videos"][it["h"]]
        if "from" in v:
            a = site_work(v["from"])
            a = re.sub(r'data-title="[^"]*"', f'data-title="{esc(it["h"])}"', a)
            a = re.sub(r'aria-label="Play [^"]*"', f'aria-label="Play {esc(it["h"])}"', a)
            a = re.sub(r'(<img src="[^"]+" alt=")[^"]*"', lambda m: m.group(1) + esc(v["alt"]) + '"', a)
            a = a[:a.index('<div class="work-copy">')] + (
                f'<div class="work-copy"><p class="eyebrow">{esc(v["eyebrow"])}</p><h3>{esc(it["h"])}</h3>'
                + "".join(f"<p>{esc(p)}</p>" for p in it["p"]) + "</div></article>")
            works += a
            continue
        works += (f'<article class="work"><button class="work-media video-launch" type="button" '
                  f'data-video="https://www.youtube-nocookie.com/embed/{v["id"]}" data-title="{esc(it["h"])}" '
                  f'data-original="https://www.youtube.com/watch?v={v["id"]}" aria-label="Play {esc(it["h"])}">'
                  f'<img src="{img_for(v["id"])}" alt="{esc(v["alt"])}" loading="lazy"><span class="video-play" aria-hidden="true">▶</span></button>'
                  f'<div class="work-copy"><p class="eyebrow">{esc(v["eyebrow"])}</p><h3>{esc(it["h"])}</h3>'
                  + "".join(f"<p>{esc(p)}</p>" for p in it["p"]) + "</div></article>")
    out.append(f'<section class="section section-dark" id="work"><div class="wrap"><div class="section-head"><div>'
               f'<p class="eyebrow">{esc(plan["eyebrows"]["work"])}</p><h2>{esc(s["h"])}</h2></div>'
               f'<p>{esc(s["paras"][0])}</p></div><div class="works">{works}</div>{btn(wa, s["bold"][0][0])}</div></section>')

    # --- included: вторая сетка карточек (без кнопки), вводный абзац в шапке блока как у work
    s = sec("included")
    intro = f'<p>{esc(s["paras"][0])}</p>' if s["paras"] else ""
    out.append(f'<section class="section section-paper"><div class="wrap"><div class="section-head"><div>'
               f'<p class="eyebrow">{esc(plan["eyebrows"]["included"])}</p><h2>{esc(s["h"])}</h2></div>{intro}</div>'
               + cards(s["items"], icon_from=4) + "</div></section>")

    # --- process: шаги + приглашение-кнопка
    s = sec("process")
    arts = re.findall(r'<div class="journey-art">(.*?)<span class="journey-number">', T["process"], re.S)
    steps = "".join(
        f'<li class="journey-step"><div class="journey-art">{arts[i % len(arts)]}<span class="journey-number">{i + 1:02d}</span></div>'
        f'<div class="journey-copy"><h3>{esc(it["h"])}</h3>' + "".join(f"<p>{esc(p)}</p>" for p in it["p"]) + "</div></li>"
        for i, it in enumerate(s["items"]))
    q, b = split_cta(s["bold"][0])
    out.append(f'<section class="section section-sage" id="process"><div class="wrap"><div class="section-head"><div>'
               f'<p class="eyebrow">{esc(plan["eyebrows"]["process"])}</p><h2>{esc(s["h"])}</h2></div></div>'
               f'<ol class="journey">{steps}</ol><div class="journey-invite">{esc(q)}{btn(wa, b)}</div></div></section>')

    # --- about: внутренние ссылки из плана (анкор из ТЗ -> только опубликованная страница), каждая один раз
    s = sec("about")
    links = dict(plan.get("links", []))

    def linkify(p):
        if not links:
            return p
        alt = "|".join(re.escape(esc(a)) for a in sorted(links, key=len, reverse=True))
        done = set()

        def a(m):
            if m.group(0) in done:
                return m.group(0)
            done.add(m.group(0))
            return f'<a href="{links[html.unescape(m.group(0))]}">{m.group(0)}</a>'
        return re.sub(alt, a, p)
    out.append(f'<section class="section"><div class="wrap"><div class="about-grid"><div><p class="eyebrow">{esc(plan["eyebrows"]["about"])}</p>'
               f'<h2>{esc(s["h"])}</h2>' + pick(r'<div class="benefit-tags">.*?</div>', T["about"]) +
               '</div><div class="about-copy">' + "".join(f'<p class="lead">{linkify(esc(p))}</p>' for p in s["paras"]) +
               "</div></div></div></section>")

    # --- reviews: блок целиком из шаблона, настоящие отзывы подставляет build.py; служебный комментарий шаблона не переносим
    out.append(re.sub(r"<!-- Placeholder testimonials:.*?-->", "", T["reviews"]))

    # --- faq
    s = sec("faq")
    qa = "".join(f'<details><summary><h3>{esc(it["h"])}</h3></summary><div class="answer">'
                 + "".join(f"<p>{esc(p)}</p>" for p in it["p"]) + "</div></details>" for it in s["items"])
    out.append(f'<section class="section" id="faq"><div class="wrap faq"><div><p class="eyebrow">{esc(plan["eyebrows"]["faq"])}</p>'
               f'<h2>{esc(s["h"])}</h2></div><div>{qa}</div></div></section>')

    # --- final: текст из md, «What happens next» и каналы связи из шаблона
    s = sec("final")
    f = T["final"]
    out.append(f'<section class="section section-sage final" id="contact"><div class="wrap"><p class="eyebrow">{esc(plan["eyebrows"]["final"])}</p>'
               f'<h2>{esc(s["h"])}</h2><p class="lead">{esc(s["paras"][0])}</p>'
               + pick(r'<div class="contact-next">.*?</div>', f) +
               f'<div class="ctas"><a class="btn btn-primary" href="{wa}" data-contact="whatsapp">{esc(s["bold"][0][0])}</a>'
               f'<a class="btn btn-ghost" href="#work">View My Work</a></div>'
               + f[f.index('<p class="contact-alternatives">'):])

    # --- шапка: мета, адрес, FAQ-разметка; подвал: текст в WhatsApp
    head = "\n".join(lines[:start])
    old_title = re.search(r"<title>(.*?)</title>", head).group(1)
    old_desc = re.search(r'<meta name="description" content="(.*?)"', head).group(1)
    url = meta["url"]
    head = head.replace(old_title, esc(meta["title"])).replace(old_desc, esc(meta["description"]).replace('"', "&quot;"))
    head = head.replace(OLD_URL, url)
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": it["h"], "acceptedAnswer": {"@type": "Answer", "text": " ".join(it["p"])}}
        for it in sec("faq")["items"]]}
    head = re.sub(r'<script type="application/ld\+json">\{"@context":"https://schema.org","@type":"FAQPage".*?</script>',
                  lambda m: '<script type="application/ld+json">' + json.dumps(faq_ld, ensure_ascii=False) + "</script>", head, flags=re.S)
    head = re.sub(r'("@type":"ProfessionalService","name":")[^"]*', lambda m: m.group(1) + "Daria Cuts - " + plan["service_type"] + " Services", head)
    head = re.sub(r'("serviceType":")[^"]*', lambda m: m.group(1) + plan["service_type"], head)
    tail = "\n".join(lines[foot:])
    tail = tail.replace(tpl_btn_wa, wa).replace(tpl_btn_wa.replace("'", "&#x27;"), wa)
    # nav-chat в шапке и WhatsApp в подвале шаблона закодированы иначе, чем кнопка Hero («!» вместо %21): меняем все ссылки WhatsApp
    head = re.sub(r'href="https://wa\.me/[^"]*"', f'href="{wa}"', head)
    tail = re.sub(r'href="https://wa\.me/[^"]*"', f'href="{wa}"', tail)
    tail = tail.replace("YouTube Video Editing Services", plan["service_type"] + " Services")
    page = head + "\n" + "\n".join(out) + "\n" + tail
    Path(ROOT / plan["out"]).write_text(page)
    print("собрано:", plan["out"])


if __name__ == "__main__":
    build(sys.argv[1])
