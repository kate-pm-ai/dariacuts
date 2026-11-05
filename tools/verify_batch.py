#!/usr/bin/env python3
"""Проверка собранных страниц партии против .md и шаблонов.  python3 tools/verify_batch.py <id> [<id> ...]"""
import html, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "site.json").read_text())
OLD = ["youtube", "short-form", "2d-animation", "motion-graphics"]
SPEC = json.loads((ROOT.parent / "Страницы услуг Ноябрь 2026" / "tools" / "spec.json").read_text())
SPEC_ID = {"music-video": "music", "instagram-reels": "reels", "social-media": "social", "tiktok": "tiktok"}
page = {p["id"]: p for p in CFG["pages"]}
built = lambda pid: (ROOT / "docs" / page[pid]["slug"] / "index.html").read_text()
norm = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def classes(s):
    out = set()
    for m in re.findall(r'class="([^"]*)"', s):
        out |= set(m.split())
    return out


old_cls = set().union(*(classes(built(o)) for o in OLD))
fails = 0
for pid in sys.argv[1:]:
    plan = json.loads((ROOT / "plans" / f"{SPEC_ID[pid]}.json").read_text()) if (ROOT / "plans" / f"{SPEC_ID[pid]}.json").exists() else None
    plan = plan or json.loads((ROOT / "plans" / f"{pid}.json").read_text())
    src = built(pid)
    tpl = "short-form" if "story-quote-action" in plan.get("formats_cta_class", "") else "youtube"
    res = []
    new = sorted(classes(src) - old_cls)
    res.append(("а) нет классов вне четырех старых страниц", not new, new))
    st = lambda s: re.findall(r"<style[^>]*>(.*?)</style>", s, re.S)
    res.append((f"б) блоки style = шаблон {tpl}", st(src) == st(built(tpl)), len(st(src))))
    md = (ROOT / plan["text"]).read_text().split("\n---\n")[0]
    meta = dict(re.findall(r"<!--\s*(\w+):\s*(.*?)\s*-->", md))
    body = re.sub(r"<!--.*?-->", "", md)
    frags = []
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("**"):
            frags += re.findall(r"\*\*(.+?)\*\*", line)
        else:
            frags.append(re.sub(r"^#+\s*", "", line))
    text = norm(src[src.index("<main") if "<main" in src else src.index('<section class="hero"'):src.index("<footer")])
    miss = [f for f in frags if norm(f) not in text]
    res.append((f"в) фрагменты .md на странице дословно: {len(frags) - len(miss)} из {len(frags)}", not miss, miss))
    t = html.unescape(re.search(r"<title>(.*?)</title>", src).group(1))
    d = html.unescape(re.search(r'<meta name="description" content="(.*?)"', src).group(1))
    c = re.search(r'<link rel="canonical" href="(.*?)"', src).group(1)
    res.append(("г) title, description, canonical как в .md", (t, d, c) == (meta["title"], meta["description"], meta["url"]), (t == meta["title"], d == meta["description"], c)))
    h2 = [norm(h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", text and src[:src.index("<footer")], re.S)]
    want = [b[0] for b in SPEC[SPEC_ID[pid]]["blocks"][1:]]
    h2_tz = [h for h in h2 if h in want]
    res.append(("д) H2 в порядке ТЗ", h2_tz == want, [h for h in h2 if h not in want]))
    res.append(("е) youtube-nocookie = 0", src.count("youtube-nocookie") == 0, src.count("youtube-nocookie")))
    geo = [w for w in ("Barcelona", "London", "UK", "Britain") if re.search(r"\b" + w + r"\b", text + " " + t + " " + d)]
    res.append(("ж) география в контенте и мета = 0", not geo, geo))
    print(f"### {pid}  (шаблон {tpl})")
    for name, ok, info in res:
        fails += not ok
        print(("  ok    " if ok else "  ПРОВАЛ ") + name + ("" if ok else f"  -> {info}"))
print("ИТОГ: провалов", fails)
sys.exit(1 if fails else 0)
