# Проверка собранного сайта dist/: JSON-LD (по словарю schema.org и требованиям Google к Product),
# canonical, robots, sitemap.xml, robots.txt, битые внутренние ссылки, alt у картинок, дубли title.
#   python tools/validate.py            # код выхода 1, если есть ошибки
import json, re, sys, urllib.request, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
CFG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
SITE = CFG['site_url'].rstrip('/')
BASE = '/' + CFG['base_path'].strip('/') + '/' if CFG['base_path'].strip('/') else '/'
ORIGIN = re.match(r'(https?://[^/]+)', SITE).group(1)
AVAIL = {'InStock', 'SoldOut', 'Reserved', 'OutOfStock', 'PreOrder', 'LimitedAvailability'}

errors, warns = [], []


def err(page, msg):
    errors.append(f'{page}: {msg}')


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.links, self.ld, self.h1, self.imgs, self.title = {}, [], [], 0, [], ''
        self.canonical = None
        self._ld = self._title = False
        self._buf = []

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == 'meta' and a.get('name'):
            self.meta[a['name']] = a.get('content', '')
        if tag == 'link' and a.get('rel') == 'canonical':
            self.canonical = a.get('href')
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag in ('img', 'script', 'link') and (a.get('src') or (tag == 'link' and a.get('rel') in ('stylesheet', 'icon') and a.get('href'))):
            self.links.append(a.get('src') or a.get('href'))
        if tag == 'img':
            self.imgs.append(a)
        if tag == 'h1':
            self.h1 += 1
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self._ld, self._buf = True, []
        if tag == 'title':
            self._title = True

    def handle_endtag(self, tag):
        if tag == 'script' and self._ld:
            self.ld.append(''.join(self._buf))
            self._ld = False
        if tag == 'title':
            self._title = False

    def handle_data(self, d):
        if self._ld:
            self._buf.append(d)
        if self._title:
            self.title += d


def page_url(f):
    rel = f.relative_to(DIST).as_posix()
    rel = rel[:-len('index.html')] if rel.endswith('index.html') else rel
    return ORIGIN + BASE + rel


def target_exists(href):
    href = href.split('#')[0].split('?')[0]
    if not href or href.startswith(('mailto:', 'tel:', 'http://', 'https://', 'data:', 'javascript:')):
        return True
    if not href.startswith(BASE):
        return False
    p = DIST / href[len(BASE):]
    return (p / 'index.html').exists() if href.endswith('/') else p.exists()


# ---------- словарь schema.org
VOCAB = ROOT / 'tools' / '.cache' / 'schemaorg.jsonld'
types, props = set(), set()
try:
    if not VOCAB.exists():
        VOCAB.parent.mkdir(parents=True, exist_ok=True)
        print('Скачиваю словарь schema.org ...')
        VOCAB.write_bytes(urllib.request.urlopen('https://schema.org/version/latest/schemaorg-current-https.jsonld', timeout=60).read())
    for node in json.loads(VOCAB.read_text(encoding='utf-8'))['@graph']:
        t = node.get('@type')
        t = t if isinstance(t, list) else [t]
        name = node['@id'].replace('schema:', '')
        if 'rdfs:Class' in t:
            types.add(name)
        if 'rdf:Property' in t:
            props.add(name)
except Exception as e:  # без сети проверим только структуру
    warns.append(f'словарь schema.org не загружен ({e}) - проверяю без него')


def check_vocab(page, node, path='$'):
    if isinstance(node, list):
        for i, x in enumerate(node):
            check_vocab(page, x, f'{path}[{i}]')
        return
    if not isinstance(node, dict):
        return
    t = node.get('@type')
    if t and types and t not in types:
        err(page, f'JSON-LD {path}: неизвестный тип {t}')
    for k, v in node.items():
        if not k.startswith('@') and props and k not in props:
            err(page, f'JSON-LD {path}: неизвестное свойство {k}')
        check_vocab(page, v, f'{path}.{k}')


def check_product(page, p, canonical, html_text):
    for k in ('name', 'image', 'offers', 'sku', 'itemCondition'):
        if not p.get(k):
            err(page, f'Product без {k}')
    for u in p.get('image', []):
        if not u.startswith('https://'):
            err(page, f'Product.image не абсолютный: {u}')
        elif not target_exists(u[len(ORIGIN):]):
            err(page, f'Product.image нет файла: {u}')
    o = p.get('offers') or {}
    if not isinstance(o.get('price'), (int, float)) or o['price'] <= 0:
        err(page, 'Offer.price не число')
    if o.get('priceCurrency') != 'RUB':
        err(page, 'Offer.priceCurrency не RUB')
    av = (o.get('availability') or '').replace('https://schema.org/', '')
    if av not in AVAIL:
        err(page, f'Offer.availability: {o.get("availability")}')
    if o.get('url') != canonical:
        err(page, 'Offer.url не совпадает с canonical')
    sold_badge = 'avail--sold' in html_text
    if (av == 'SoldOut') != sold_badge:
        err(page, f'availability={av}, а плашка «Продано» на странице: {sold_badge}')
    return av


def check_crumbs(page, b, canonical):
    items = b.get('itemListElement', [])
    for i, it in enumerate(items, start=1):
        if it.get('position') != i:
            err(page, 'BreadcrumbList: позиции не по порядку')
        u = it.get('item', '')
        if not u.startswith(ORIGIN) or not target_exists(u[len(ORIGIN):]):
            err(page, f'BreadcrumbList: нет страницы {u}')
    if items and items[-1].get('item') != canonical:
        err(page, 'BreadcrumbList: последняя крошка не равна canonical')


pages, titles, stats = {}, {}, {'Product': 0, 'BreadcrumbList': 0, 'SoldOut': 0, 'InStock': 0, 'Reserved': 0, 'ld': 0}
for f in sorted(DIST.rglob('*.html')):
    rel = f.relative_to(DIST).as_posix()
    if rel in ('showcase.html',):
        continue
    text = f.read_text(encoding='utf-8')
    p = Page()
    p.feed(text)
    url = page_url(f)
    robots = p.meta.get('robots', '')
    redirect = 'http-equiv="refresh"' in text
    pages[url] = robots
    if not redirect:
        if not p.title.strip():
            err(rel, 'нет title')
        if not p.meta.get('description'):
            err(rel, 'нет description')
        if p.h1 != 1:
            err(rel, f'h1 на странице: {p.h1}')
        if robots.startswith('index'):
            if p.canonical != url:
                err(rel, f'canonical {p.canonical} != {url}')
            titles.setdefault(p.title, []).append(rel)
        for img in p.imgs:
            if 'alt' not in img:
                err(rel, f'img без alt: {img.get("src")}')
    for h in p.links:
        if not target_exists(h):
            err(rel, f'битая ссылка {h}')
    for raw in p.ld:
        stats['ld'] += 1
        try:
            data = json.loads(raw)
        except ValueError as e:
            err(rel, f'JSON-LD не парсится: {e}')
            continue
        if data.get('@context') != 'https://schema.org':
            err(rel, 'JSON-LD без @context https://schema.org')
        check_vocab(rel, data)
        for node in data.get('@graph', [data]):
            t = node.get('@type')
            if t == 'Product':
                stats['Product'] += 1
                av = check_product(rel, node, p.canonical, text)
                stats[av] = stats.get(av, 0) + 1
            elif t == 'BreadcrumbList':
                stats['BreadcrumbList'] += 1
                check_crumbs(rel, node, p.canonical)

for t, rels in titles.items():
    if len(rels) > 1:
        err(', '.join(rels[:3]), f'одинаковый title «{t}»')

# ---------- sitemap.xml
ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
try:
    tree = ET.parse(DIST / 'sitemap.xml')
    locs = [u.find('s:loc', ns).text for u in tree.getroot().findall('s:url', ns)]
    for u in locs:
        if u not in pages:
            err('sitemap.xml', f'нет страницы {u}')
        elif not pages[u].startswith('index'):
            err('sitemap.xml', f'в sitemap страница с robots={pages[u]}: {u}')
    for u, r in pages.items():
        if r.startswith('index') and u not in locs:
            err('sitemap.xml', f'индексируемой страницы нет в sitemap: {u}')
except Exception as e:
    err('sitemap.xml', f'не читается: {e}')
    locs = []

# ---------- robots.txt
rb = (DIST / 'robots.txt').read_text(encoding='utf-8')
if f'Sitemap: {SITE}/sitemap.xml' not in rb:
    err('robots.txt', 'нет строки Sitemap')
if f'Disallow: {BASE}*?' not in rb:
    err('robots.txt', 'GET-параметры фильтров не закрыты (Disallow: /*?)')
if 'Clean-param:' not in rb:
    err('robots.txt', 'нет Clean-param для Яндекса')
for line in rb.splitlines():
    if line.startswith(('Disallow:', 'Allow:', 'Clean-param:', 'Sitemap:', 'User-agent:', '#')) or not line.strip():
        continue
    err('robots.txt', f'непонятная строка: {line}')

print(f'Страниц: {len(pages)}, в sitemap: {len(locs)}, блоков JSON-LD: {stats["ld"]}, Product: {stats["Product"]} '
      f'(InStock {stats.get("InStock", 0)}, Reserved {stats.get("Reserved", 0)}, SoldOut {stats.get("SoldOut", 0)}), '
      f'BreadcrumbList: {stats["BreadcrumbList"]}, словарь schema.org: {"да" if types else "нет"}')
for w in warns:
    print('ВНИМАНИЕ:', w)
if errors:
    print(f'\nОшибок: {len(errors)}')
    for e in errors[:80]:
        print(' -', e)
    sys.exit(1)
print('Ошибок нет.')
