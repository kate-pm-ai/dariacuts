# dariacuts.com – страницы для выкладки Алексею

- `pages/` – согласованные страницы как есть (тексты и дизайн не трогать).
- `site.json` – список страниц и их адреса на dariacuts.com.
- `tools/standard/` – стандарт сайта Алексея, снят с живой главной (иконки, шрифты).
- `python3 tools/build.py` – собрать: `docs/` (предпросмотр на GitHub Pages, noindex) и `dist/` (архив для Алексея, zip).
- `python3 tools/check.py` – проверить сборку против оригиналов.

Новая страница: положить HTML в `pages/`, добавить строку в `site.json`, собрать, проверить.
Сайт Алексея поменял шапку или шрифты: `python3 tools/build.py --refresh-standard`.

Перед новой партией страниц прочитать досье клиента с разбором прошлых ошибок: ~/WORKSPACE/CLIENTS/dariacuts.com/CLAUDE.md
