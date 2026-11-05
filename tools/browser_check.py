#!/usr/bin/env python3
"""Проверка сборки в браузере: страницы архива, разложенные как на сайте (dist + vendor).

Ловит то, что не видно в коде: меню, карточки, видео, слайдер отзывов, кнопку «наверх»,
баннер куки, шрифты, картинки, ошибки скриптов, вылезание за край. Компьютер и телефон.
Запуск после build.py: /usr/local/bin/python3 tools/browser_check.py
"""
import asyncio, functools, http.server, json, shutil, sys, tempfile, threading
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "site.json").read_text())
WA = "https://wa.me/34687631622"
SIZES = ((1440, 900, "комп"), (390, 844, "телефон"))


def serve():
    site = Path(tempfile.mkdtemp(prefix="dariacuts-site-"))
    dist = sorted((ROOT / "dist").glob("dariacuts-pages-*/"))[-1]
    shutil.copytree(dist, site, dirs_exist_ok=True)
    shutil.copytree(ROOT / "vendor", site, dirs_exist_ok=True)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(site))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/"


async def new_page(ctx, url):
    pg = await ctx.new_page()
    pg.errs, pg.reqs = [], []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)[:80]))
    pg.on("response", lambda r: pg.reqs.append((r.url, r.status)))
    await pg.route("**/*googletagmanager*", lambda r: r.abort())
    await pg.route("**/player.vimeo.com/**", lambda r: r.abort())
    await pg.route("**/youtube.com/embed/**", lambda r: r.abort())
    await pg.goto(url, wait_until="networkidle")
    return pg


async def check(ctx, base, page, w):
    url = base + (page["slug"] + "/" if page["slug"] else "")
    bad = []
    pg = await new_page(ctx, url)
    if not await pg.evaluate("!!document.querySelector('#cc-main .cm')"):
        bad.append("нет баннера куки")
    await pg.add_style_tag(content="#cc-main .cm-wrapper{display:none!important}")
    await pg.evaluate("""async()=>{for(let y=0;y<document.body.scrollHeight;y+=500){scrollTo(0,y);await new Promise(r=>setTimeout(r,30))}}""")
    await pg.wait_for_timeout(600)
    d = await pg.evaluate("""()=>({
      imgs:[...document.querySelectorAll('img')].filter(i=>!(i.complete&&i.naturalWidth>0)).map(i=>i.getAttribute('src')),
      anchors:[...document.querySelectorAll('a[href^="#"]')].map(a=>a.getAttribute('href')).filter(x=>x.length>1&&!document.getElementById(x.slice(1))),
      wa:[...new Set([...document.querySelectorAll('a[href*="wa.me"]')].map(a=>a.href.split('?')[0]))],
      btt:document.getElementById('backToTop')?getComputedStyle(document.getElementById('backToTop')).opacity:'нет',
      over:document.documentElement.scrollWidth>innerWidth})""")
    if d["imgs"]: bad.append(f"картинки не загрузились: {d['imgs']}")
    if d["anchors"]: bad.append(f"якоря без цели: {d['anchors']}")
    if d["wa"] and d["wa"] != [WA]: bad.append(f"WhatsApp не тот: {d['wa']}")
    if d["btt"] != "1": bad.append("кнопка «наверх» не появилась")
    if d["over"]: bad.append("вылезает за край экрана")
    await pg.click("#backToTop")
    await pg.wait_for_timeout(2500)
    if await pg.evaluate("scrollY") > 5: bad.append("кнопка «наверх» не вернула наверх")
    if any("googleapis" in u or "gstatic" in u for u, _ in pg.reqs): bad.append("грузит Google Fonts")
    if any(s >= 400 for u, s in pg.reqs if u.startswith(base)):
        bad.append(f"битые файлы: {[u for u, s in pg.reqs if u.startswith(base) and s >= 400]}")
    # меню Services
    if await pg.locator("details.services-menu summary").is_visible():
        await pg.evaluate("scrollTo(0,0)")
        await pg.click("details.services-menu summary")
        await pg.evaluate("document.body.dispatchEvent(new MouseEvent('click',{bubbles:true}))")  # клик мимо, в пустое место
        if await pg.evaluate("document.querySelector('details.services-menu').open"):
            bad.append("меню не закрывается по клику мимо")
    # видео: каждое открывается в окне, ссылка на оригинал скрыта
    n = await pg.locator(".video-launch[data-video]").count()
    for i in range(n):
        btn = pg.locator(".video-launch[data-video]").nth(i)
        exp = await btn.get_attribute("data-video")
        await btn.scroll_into_view_if_needed(); await btn.click(); await pg.wait_for_timeout(500)
        if not await pg.evaluate("(e)=>{const f=[...document.querySelectorAll('iframe[src]')].find(f=>f.src.startsWith(e));const a=document.getElementById('video-original');return !!f&&!(a&&a.getClientRects().length)}", exp):
            bad.append(f"видео не открылось: {exp}")
        close = pg.locator('#video-dialog button:has-text("Close")').first
        if await close.count() and await close.is_visible():
            await close.click()
        else:
            await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(400)
        if await pg.evaluate("!!document.querySelector('#video-dialog[open]')"):
            bad.append("окно видео не закрывается кнопкой Close"); break
    # отзывы
    if await pg.locator("#reviews .review").count():
        reviews = json.loads((ROOT / "reviews.json").read_text())
        rv, dots = await pg.locator("#reviews .review").count(), await pg.locator(".review-dots button").count()
        if rv != len(reviews) or (len(reviews) > 1 and dots != len(reviews)):
            bad.append(f"отзывов {rv}, точек {dots}, а в reviews.json {len(reviews)}")
    # Cookie settings открывает окно настроек (сначала отказ в баннере, как посетитель)
    await pg.add_style_tag(content="#cc-main .cm-wrapper{display:block!important}")
    rej = pg.locator('#cc-main .cm button:has-text("Reject")').first
    if await rej.count() and await rej.is_visible():
        await rej.click(); await pg.wait_for_timeout(500)
    cs = pg.locator('button:has-text("Cookie settings")').first
    if await cs.count():
        await cs.scroll_into_view_if_needed(); await cs.click(); await pg.wait_for_timeout(700)
        if not await pg.evaluate("!!document.querySelector('#cc-main .pm')"): bad.append("Cookie settings не открывает окно")
    if pg.errs: bad.append(f"ошибки скриптов: {pg.errs}")
    cards = await pg.locator("article.service:has(.service-link)").count()
    await pg.close()
    # карточки ведут на свои страницы
    for i in range(cards):
        pg = await new_page(ctx, url)
        c = pg.locator("article.service:has(.service-link)").nth(i)
        href = await c.locator(".service-link").get_attribute("href")
        live = ["/" + q["slug"] + "/" for q in CFG["pages"] if q["slug"]]
        await c.scroll_into_view_if_needed()
        async with pg.expect_navigation() as nav:
            await c.click()
        resp = await nav.value
        if href not in live or not resp or resp.status != 200 or not await pg.locator("h1").count():
            bad.append(f"карточка {href} ведет на несуществующую страницу")
        await pg.close()
    return n, cards, bad


async def main():
    base = serve()
    failed = 0
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for page in CFG["pages"]:
            for w, h, tag in SIZES:
                ctx = await b.new_context(viewport={"width": w, "height": h})
                # cookieconsent прячет баннер от автоматических браузеров (hideFromBots)
                await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>false})")
                n, cards, bad = await check(ctx, base, page, w)
                await ctx.close()
                failed += len(bad)
                print(f"{page['id']:16} {tag:8} видео {n}, карточек {cards}: " + ("всё ок" if not bad else "; ".join(bad)))
        await b.close()
    print("ИТОГ:", "всё работает" if not failed else f"проблем {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
