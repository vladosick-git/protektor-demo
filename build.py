#!/usr/bin/env python3
"""Сборка сайта «Протектор» из таблиц data/tires.csv и data/wheels.csv в папку dist/.

    python build.py                 # собрать сайт
    python build.py --serve         # собрать и открыть http://localhost:8080/protektor-demo/
    python build.py --today 2026-10-15   # зафиксировать «сегодня» (для проданных и демо)

Нужен только Python 3.10+. Pillow (pip install pillow) нужен, чтобы ужать фото в webp;
без него фото копируются как есть.
"""
import argparse, csv, html, io, json, re, shutil, sys, urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / 'dist'
SRC = ROOT / 'src'
PHOTOS = ROOT / 'photos'

try:
    from PIL import Image, ImageOps
except ImportError:  # сайт соберётся и без Pillow
    Image = None

E = html.escape
NB = ' '
problems = []


def warn(msg):
    problems.append(msg)


# ---------------------------------------------------------------- утилиты

TR = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
              ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's', 't', 'u', 'f',
               'h', 'ts', 'ch', 'sh', 'sch', '', 'y', '', 'e', 'yu', 'ya']))


def slugify(s):
    s = ''.join(TR.get(c, c) for c in str(s).lower())
    s = s.replace('*', '').replace('+', '-plus').replace(',', '-').replace('.', '-')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def num(s, default=None):
    s = str(s or '').strip().replace(' ', '').replace(' ', '').replace(',', '.').replace('мм', '').replace('₽', '')
    if not s:
        return default
    try:
        v = float(s)
        return int(v) if v.is_integer() else v
    except ValueError:
        return default


def rub(n):
    return f'{int(n):,}'.replace(',', NB) + NB + '₽'


def mm(v):
    return f'{v:.1f}'.replace('.', ',')


def comma(v):
    return str(v).replace('.', ',')


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def ddmmyyyy(d):
    return d.strftime('%d.%m.%Y')


def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d.%m.%y'):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return 'bad'


# ---------------------------------------------------------------- чтение таблиц

def read_table(path, url=''):
    """CSV из файла или из опубликованной Google-таблицы. Разделитель ; или , определяется сам,
    кодировка UTF-8 (с BOM или без) или Windows-1251 (так сохраняет старый Excel)."""
    if url:
        raw = urllib.request.urlopen(url, timeout=30).read()
        src = url
    else:
        raw = path.read_bytes()
        src = path.name
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1251')
    head = text.split('\n', 1)[0]
    delim = ';' if head.count(';') >= head.count(',') else ','
    rows = []
    for i, r in enumerate(csv.DictReader(io.StringIO(text), delimiter=delim), start=2):
        r = {(k or '').strip().lower().replace(' ', '_'): (v or '').strip() for k, v in r.items()}
        if not any(r.values()):
            continue
        r['_line'] = f'{src}, строка {i}'
        rows.append(r)
    return rows


STATUS = {'в наличии': 'stock', 'есть': 'stock', 'наличие': 'stock', '': 'stock',
          'бронь': 'reserved', 'резерв': 'reserved', 'забронировано': 'reserved',
          'продано': 'sold', 'продан': 'sold', 'продана': 'sold'}
SEASON = {'зима': 'zima', 'зимние': 'zima', 'лето': 'leto', 'летние': 'leto', 'всесезон': 'vsesezon', 'всесезонные': 'vsesezon'}
SEASON_SLUG = {'zima': 'zimnie', 'leto': 'letnie', 'vsesezon': 'vsesezonnye'}
SEASON_NAME = {'zima': 'Зимние', 'leto': 'Летние', 'vsesezon': 'Всесезонные'}
SEASON_SHORT = {'zima': 'Зима', 'leto': 'Лето', 'vsesezon': 'Всесезонные'}
SEASON_GEN = {'zima': 'зимних', 'leto': 'летних', 'vsesezon': 'всесезонных'}
SPEED = {'Q': 160, 'R': 170, 'S': 180, 'T': 190, 'H': 210, 'V': 240, 'W': 270, 'Y': 300}
LOAD_KG = {88: 560, 89: 580, 90: 600, 91: 615, 92: 630, 93: 650, 94: 670, 95: 690, 96: 710, 97: 730, 98: 750,
           99: 775, 100: 800, 101: 825, 102: 850, 103: 875, 104: 900}
BRAND_SLUG = {'Nokian Tyres': 'nokian'}


def tire_state(season, avg):
    steps = [(7.5, 'Отличное'), (6, 'Хорошее'), (5, 'Среднее')] if season == 'zima' else [(6, 'Отличное'), (4.5, 'Хорошее'), (3.5, 'Среднее')]
    for lim, name in steps:
        if avg >= lim:
            return name
    return 'На сезон'


def state_cls(name):
    return {'отличное': 'ok', 'хорошее': 'ok', 'среднее': 'mid'}.get(name.lower().split(',')[0], 'low')


def load_fitment():
    fit = {}
    p = ROOT / 'data' / 'fitment.csv'
    if p.exists():
        for r in read_table(p):
            fit[(r.get('тип', ''), r.get('ключ', '').replace(' ', '').lower())] = r.get('подходит_на', '')
    return fit


def common(r, kind):
    """Общие поля шин и дисков: артикул, статус, кол-во, цена, даты."""
    line = r['_line']
    sku = r.get('артикул', '').upper()
    if not sku:
        warn(f'{line}: пустой артикул, строка пропущена')
        return None
    status = STATUS.get(r.get('статус', '').lower())
    if not status:
        warn(f'{line}: статус «{r.get("статус")}» не понят (пишите: в наличии, бронь или продано), строка пропущена')
        return None
    qty = num(r.get('кол_во'))
    price = num(r.get('цена_комплект'))
    if not qty or not price:
        warn(f'{line} ({sku}): нет количества или цены, строка пропущена')
        return None
    added = parse_date(r.get('дата_поступления'))
    sold = parse_date(r.get('дата_продажи'))
    if added == 'bad' or sold == 'bad':
        warn(f'{line} ({sku}): дата не в формате 2026-10-15 или 15.10.2026, строка пропущена')
        return None
    if status == 'sold' and not sold:
        warn(f'{line} ({sku}): статус «продано», но нет даты продажи - беру сегодняшнюю')
        sold = TODAY
    return dict(kind=kind, sku=sku, skuslug=slugify(sku), status=status, qty=int(qty), price=int(price),
                each=int(round(price / qty / 100) * 100), added=added or TODAY, sold=sold if status == 'sold' else None,
                note=r.get('примечание', ''), line=line)


def load_tires(fit):
    out = []
    for r in read_table(ROOT / 'data' / 'tires.csv', CFG.get('sheet_csv_url_tires', '')):
        t = common(r, 'tire')
        if not t:
            continue
        line, sku = t['line'], t['sku']
        season = SEASON.get(r.get('сезон', '').lower())
        w, h, d = num(r.get('ширина')), num(r.get('профиль')), num(str(r.get('диаметр', '')).upper().replace('R', ''))
        if not season or not (w and h and d):
            warn(f'{line} ({sku}): нет сезона или размера, строка пропущена')
            continue
        treads = [num(x) for x in re.split(r'[/;|]', r.get('протектор_мм', '')) if x.strip()]
        if not treads or None in treads:
            warn(f'{line} ({sku}): протектор пишите через «/» по каждому колесу, например 8,6/8,5/8,4/8,5 - строка пропущена')
            continue
        if len(treads) == 1 and t['qty'] > 1:
            treads = treads * t['qty']
        if len(treads) != t['qty']:
            warn(f'{line} ({sku}): замеров протектора {len(treads)}, а колёс {t["qty"]}')
        avg = round(sum(treads) / len(treads) + 1e-9, 1)
        spikes = r.get('шипы', '').lower()
        studs = None if season != 'zima' else spikes in ('да', 'шипы', '1', 'yes', 'ш')
        state = r.get('состояние') or tire_state(season, avg)
        size = f'{w}/{h} R{d}'
        li, si = r.get('индекс_нагрузки', ''), r.get('индекс_скорости', '').upper()
        brand, model = r.get('бренд', ''), r.get('модель', '')
        t.update(season=season, w=int(w), h=int(h), d=int(d), size=size, li=li, si=si, brand=brand, model=model,
                 year=int(num(r.get('год'), 0) or 0), dot=r.get('dot', ''), treads=treads, avg=avg, studs=studs,
                 hernia=r.get('грыжи_порезы') or 'нет', repairs=r.get('ремонты') or 'нет', studs_lost=r.get('выпавшие_шипы', ''),
                 state=state.capitalize(), cars=fit.get(('шины', size.replace(' ', '').lower()), ''))
        t['title'] = f'{brand} {model}'.strip()
        t['slug'] = slugify(f'{BRAND_SLUG.get(brand, brand)} {model} {w} {h} r{d} {sku}')
        t['url'] = f'shiny/{t["slug"]}/'
        t['type_name'] = 'Шипы' if studs else ('Липучка' if studs is False else '')
        out.append(t)
    return out


def load_wheels(fit):
    out = []
    for r in read_table(ROOT / 'data' / 'wheels.csv', CFG.get('sheet_csv_url_wheels', '')):
        t = common(r, 'wheel')
        if not t:
            continue
        line, sku = t['line'], t['sku']
        d, width, et, co = num(str(r.get('диаметр', '')).upper().replace('R', '')), num(r.get('ширина')), num(r.get('et')), num(r.get('цо'))
        pcd = r.get('pcd', '').lower().replace('х', 'x').replace('*', 'x').replace('.', ',').replace(' ', '')
        if not (d and width and pcd and et is not None and co):
            warn(f'{line} ({sku}): нужны диаметр, ширина, pcd, et и цо - строка пропущена')
            continue
        kind = r.get('тип', 'литые').lower()
        origin = r.get('происхождение', '').lower()
        make = r.get('марка', '')
        if kind.startswith('шт'):
            title = 'Штампованные'
        else:
            title = kind.capitalize() + (f', оригинал {make}' if origin == 'оригинал' and make else f', {origin}' if origin else '')
        state = (r.get('состояние') or 'хорошее').capitalize()
        defects = r.get('дефекты', '')
        t.update(d=int(d), width=width, pcd=pcd, et=int(et), co=co, wkind=kind, origin=origin, make=make,
                 wmodel=r.get('модель_диска', ''), color=r.get('цвет', ''), state=state, defects=defects,
                 repair=r.get('ремонт') or 'нет', title=title,
                 spec=f'R{int(d)} {comma(width)}J {pcd} ET{int(et)} ЦО {comma(co)}',
                 cars=fit.get(('диски', f'{pcd}{comma(co)}'.lower()), ''))
        t['full_state'] = state + (f', {defects}' if defects else '')
        t['slug'] = slugify(f'{kind} {origin} {make} r{int(d)} {pcd} et{int(et)} {sku}')
        t['url'] = f'diski/{t["slug"]}/'
        out.append(t)
    return out


# ---------------------------------------------------------------- фото

IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp')
SIZES = (480, 1080)


def caption_of(name):
    stem = re.sub(r'^[\d\s._-]+', '', Path(name).stem).replace('_', ' ').strip()
    if re.match(r'^(img|dsc|photo|pxl|image|whatsapp)\b', stem, re.I):
        return ''
    return stem


def photo_dir(sku):
    for cand in (sku, slugify(sku).upper(), slugify(sku)):
        p = PHOTOS / cand
        if p.is_dir():
            return p
    return None


def process_image(src, key, idx):
    """Ужимает фото в webp двух размеров. Возвращает (src_small, src_big, w, h)."""
    out_dir = DIST / 'assets' / 'p' / key
    out_dir.mkdir(parents=True, exist_ok=True)
    if Image is None:
        dst = out_dir / f'{idx}{src.suffix.lower()}'
        shutil.copy2(src, dst)
        rel = f'assets/p/{key}/{dst.name}'
        return rel, rel, 1200, 800
    cache = out_dir / f'{idx}-{SIZES[-1]}.webp'
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        w0, h0 = im.size
        res = []
        for w in SIZES:
            dst = out_dir / f'{idx}-{w}.webp'
            if not (dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime):
                k = min(1.0, w / w0)
                im.resize((round(w0 * k), round(h0 * k)), Image.LANCZOS).save(dst, 'WEBP', quality=78, method=5)
            res.append(f'assets/p/{key}/{dst.name}')
        k = min(1.0, SIZES[-1] / w0)
        return res[0], res[1], round(w0 * k), round(h0 * k)


POOL = {}


def pool_for(item):
    """Демо-режим: товарам без своих фото даём фото из photos/_pool/<группа>/ по кругу."""
    group = ({'zima': 'зима', 'leto': 'лето', 'vsesezon': 'лето'}[item['season']] if item['kind'] == 'tire'
             else ('штампованные' if item['wkind'].startswith('шт') else 'литые'))
    if group not in POOL:
        d = PHOTOS / '_pool' / group
        POOL[group] = sorted(p for p in d.glob('*') if p.suffix.lower() in IMG_EXT) if d.is_dir() else []
    files = POOL[group]
    if not files:
        return []
    n = int(re.sub(r'\D', '', item['sku']) or 0)
    return [files[n % len(files)]]


def attach_photos(items):
    for it in items:
        d = photo_dir(it['sku'])
        files = sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXT) if d else []
        it['demo_photo'] = False
        if not files and CFG.get('demo'):
            files = pool_for(it)
            it['demo_photo'] = bool(files)
        it['photos'] = []
        for i, f in enumerate(files, start=1):
            key = it['skuslug'] if not it['demo_photo'] else 'pool-' + slugify(f.parent.name)
            idx = i if not it['demo_photo'] else slugify(f.stem)
            sm, big, w, h = process_image(f, key, idx)
            cap = '' if it['demo_photo'] else caption_of(f.name)
            it['photos'].append(dict(sm=sm, big=big, w=w, h=h, cap=cap))
        if not it['photos'] and not CFG.get('demo'):
            warn(f'{it["line"]} ({it["sku"]}): нет фото в папке photos/{it["sku"]}/')


# ---------------------------------------------------------------- ссылки и иконки

def U(path=''):
    return BASE + path.lstrip('/')


def ABS(path=''):
    return ORIGIN + U(path)


def img_url(rel):
    return U(rel)


ICONS = {
    'phone': '<path fill="currentColor" stroke="none" d="M6.6 10.8a15.2 15.2 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z"/>',
    'wa': '<circle cx="12" cy="12" r="11" fill="#25D366" stroke="none"/><path fill="#fff" stroke="none" d="M17 14.3c-.3-.1-1.6-.8-1.8-.9-.3-.1-.4-.1-.6.1l-.9 1c-.2.2-.3.2-.6.1-.3-.1-1.1-.4-2.1-1.3-.8-.7-1.3-1.5-1.4-1.8-.2-.3 0-.4.1-.6l.4-.5.3-.5c.1-.2 0-.3 0-.5l-.8-2c-.2-.5-.4-.4-.6-.4h-.5c-.2 0-.5.1-.7.3-.2.3-.9.9-.9 2.2s1 2.6 1.1 2.7c.1.2 1.9 2.9 4.6 4.1 1.7.7 2.3.8 3.2.6.5-.1 1.6-.6 1.8-1.3.2-.6.2-1.2.2-1.3-.1-.1-.3-.2-.6-.3z"/><path fill="#fff" stroke="none" d="M12 4.6a7.4 7.4 0 0 0-6.4 11.2L4.6 19.4l3.7-1A7.4 7.4 0 1 0 12 4.6zm0 13.5c-1.2 0-2.4-.3-3.4-.9l-.2-.1-2.2.6.6-2.1-.2-.3A6.1 6.1 0 1 1 12 18.1z"/>',
    'tg': '<circle cx="12" cy="12" r="11" fill="#2AABEE" stroke="none"/><path fill="#fff" stroke="none" d="M5.6 11.7l11-4.3c.5-.2 1 .1.8.9l-1.9 8.9c-.1.6-.5.8-1 .5l-2.9-2.1-1.4 1.3c-.2.2-.3.3-.6.3l.2-3 5.4-4.9c.2-.2 0-.3-.3-.1l-6.7 4.2-2.9-.9c-.6-.2-.6-.6.3-.8z"/>',
    'heart': '<path d="M12 20.3S3.5 15.4 3.5 9.3A4.6 4.6 0 0 1 12 6.8a4.6 4.6 0 0 1 8.5 2.5c0 6.1-8.5 11-8.5 11z"/>',
    'search': '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    'chev': '<path d="M7 10l5 5 5-5"/>',
    'chev-r': '<path d="M10 6l6 6-6 6"/>',
    'chev-l': '<path d="M14 6l-6 6 6 6"/>',
    'arrow': '<path d="M4 12h15M14 7l5 5-5 5"/>',
    'check': '<circle cx="12" cy="12" r="10" fill="currentColor" stroke="none"/><path d="M7.5 12.3l3 3 6-6.2" stroke="#fff" stroke-width="2.2"/>',
    'tread': '<path d="M6 3v18M18 3v18M6 5.5l6 3 6-3M6 10.5l6 3 6-3M6 15.5l6 3 6-3"/>',
    'tires': '<rect x="3" y="3.5" width="7.5" height="17" rx="3.5"/><rect x="13.5" y="3.5" width="7.5" height="17" rx="3.5"/><path d="M6.7 7v10M17.2 7v10"/>',
    'rim': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.4"/><path d="M12 9.6V3.4M14.3 11.3l5.9-1.9M13.4 14l3.6 5M10.6 14l-3.6 5M9.7 11.3L3.8 9.4"/>',
    'grid': '<rect x="4" y="4" width="7" height="7" rx="1" fill="currentColor"/><rect x="13" y="4" width="7" height="7" rx="1" fill="currentColor"/><rect x="4" y="13" width="7" height="7" rx="1" fill="currentColor"/><rect x="13" y="13" width="7" height="7" rx="1" fill="currentColor"/>',
    'list': '<path d="M4 6.5h16M4 12h16M4 17.5h16"/>',
    'wrench': '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9l-3.8 3.8z" fill="currentColor" stroke="none"/>',
    'camera': '<path d="M22 18.5a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-10a2 2 0 0 1 2-2h3.5l2-3h5l2 3H20a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    'calendar': '<rect x="3.5" y="4.5" width="17" height="16" rx="2"/><path d="M8 2.5v4M16 2.5v4M3.5 9.5h17M7 13h2M11 13h2M15 13h2M7 16.5h2M11 16.5h2"/>',
    'star': '<path fill="currentColor" stroke="none" d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5-4.8-4.6 6.6-.9z"/>',
    'image': '<rect x="3" y="3.5" width="18" height="17" rx="2"/><circle cx="8.5" cy="9" r="1.7"/><path d="M21 15.5l-5-5L5 20.5"/>',
    'pin': '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="2.8"/>',
    'menu': '<path d="M3.5 6.5h17M3.5 12h17M3.5 17.5h17"/>',
    'close': '<path d="M6 6l12 12M18 6L6 18"/>',
    'filter': '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2.2"/><circle cx="10" cy="17" r="2.2"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'loupe': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5l5 5M7.5 10.5c0-1.7 1.3-3 3-3"/>',
    'gauge': '<path d="M5 3v18M19 3v18M5 6l7 3 7-3M5 12l7 3 7-3M5 18l7 3 7-3" opacity=".9"/>',
    'ok': '<path d="M5 12.5l4.5 4.5L19 7.5" stroke-width="2.4"/>',
    'upload': '<path d="M12 16V4M7 9l5-5 5 5M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
}
LOGO = ('<svg class="logo__mark" viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="24" r="24" fill="#FFD20A"/>'
        '<g fill="none" stroke="#141414" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M26.5 8.5l-4 7.5 4.5 7-4.5 8 3.5 8.5"/><path d="M21.5 11.5l-8 1.5M22.5 19.5l-9.5 2M22 28l-8.5 3M24 35.5l-6.5 3.5"/>'
        '<path d="M28.5 13l6.5-3.5M27.5 21l8.5-1.5M26.5 29.5l8 1M28.5 37l5.5 1"/></g></svg>')


def ic(name, cls=''):
    return f'<svg class="i{(" " + cls) if cls else ""}" aria-hidden="true"><use href="#i-{name}"/></svg>'


def sprite():
    syms = ''.join(f'<symbol id="i-{k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
                   f'stroke-linecap="round" stroke-linejoin="round">{v}</symbol>' for k, v in ICONS.items())
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{syms}</svg>'


# ---------------------------------------------------------------- общий каркас страницы

def tel_href():
    return 'tel:+' + re.sub(r'\D', '', CFG['phone'])


def wa_href(text=''):
    q = ('?text=' + urllib.request.quote(text)) if text else ''
    return f'https://wa.me/{CFG["whatsapp"]}{q}'


def tg_href():
    return f'https://t.me/{CFG["telegram"]}'


def nav_html():
    zs = ''.join(f'<a href="{U(tire_size_url("zima", s))}">{E(s)}</a>' for s in CFG['popular_tire_sizes'])
    seasons = ''.join(f'<a href="{U("shiny/" + SEASON_SLUG[s] + "/")}">{SEASON_NAME[s]} шины</a>' for s in ('zima', 'leto', 'vsesezon')
                      if f'shiny/{SEASON_SLUG[s]}/' in LANDINGS)
    ds = ''.join(f'<a href="{U(f"diski/r{d}/")}">Диски R{d}</a>' for d in sorted({w["d"] for w in WHEELS}) if f'diski/r{d}/' in LANDINGS)
    pw = ''.join(f'<a href="{U(wheel_url_by_label(s))}">{E(s)}</a>' for s in CFG['popular_wheels'] if wheel_url_by_label(s) in LANDINGS)
    return f'''<nav class="nav" aria-label="Каталог">
 <div class="nav__item"><a class="nav__link" href="{U('shiny/')}">Шины{ic('chev', 'nav__chev')}</a>
  <div class="nav__drop"><div class="nav__col"><b>По сезону</b>{seasons}<a href="{U('shiny/')}">Все шины</a></div><div class="nav__col"><b>Зимние, популярные размеры</b>{zs}</div></div></div>
 <div class="nav__item"><a class="nav__link" href="{U('diski/')}">Диски{ic('chev', 'nav__chev')}</a>
  <div class="nav__drop"><div class="nav__col"><b>По диаметру</b>{ds}<a href="{U('diski/')}">Все диски</a></div><div class="nav__col"><b>Популярные</b>{pw}</div></div></div>
 <a class="nav__link" href="{U('kolesa/')}">Колёса в сборе</a>
 <a class="nav__link" href="{U('vykup/')}">Выкуп шин</a>
 <a class="nav__link" href="{U('shinomontazh/')}">Шиномонтаж</a>
 <a class="nav__link" href="{U('dostavka/')}">Доставка</a>
</nav>'''


def header_html():
    phone = E(CFG['phone'])
    return f'''<div class="topbar"><div class="wrap topbar__in">
 <span class="topbar__city">{E(CFG['city'])}{ic('chev')}</span><span class="topbar__dot">·</span><span>{E(CFG['address'])}</span><span class="topbar__dot">·</span><span>{E(CFG['hours'])}</span>
 <span class="topbar__right"><a class="topbar__phone" href="{tel_href()}" data-goal="call">{phone}</a>
 <a class="topbar__soc" href="{wa_href()}" data-goal="whatsapp" aria-label="Написать в WhatsApp" rel="nofollow noopener" target="_blank">{ic('wa')}</a>
 <a class="topbar__soc" href="{tg_href()}" data-goal="telegram" aria-label="Написать в Telegram" rel="nofollow noopener" target="_blank">{ic('tg')}</a></span>
</div></div>
<header class="header"><div class="wrap header__in">
 <a class="logo" href="{U()}" aria-label="Протектор - на главную">{LOGO}<span class="logo__txt"><b>ПРОТЕКТОР</b><small>{E(CFG['tagline'])}</small></span></a>
 {nav_html()}
 <form class="search" role="search" action="{U('poisk/')}" data-search><label class="sr" for="q">Поиск по каталогу</label>{ic('search')}<input id="q" name="q" type="search" placeholder="Размер, бренд или артикул" autocomplete="off"><div class="search__drop" hidden></div></form>
 <a class="header__fav" href="{U('izbrannoe/')}" aria-label="Избранное">{ic('heart')}<span class="fav-count" hidden></span></a>
 <button class="btn btn--y header__lead" type="button" data-open="lead">Оставить заявку</button>
 <a class="header__phone" href="{tel_href()}" data-goal="call">{ic('phone')}<span>{phone}</span></a>
 <button class="burger" type="button" aria-label="Меню" aria-expanded="false" aria-controls="mmenu">{ic('menu')}</button>
</div>
<div class="mmenu" id="mmenu" hidden><div class="wrap">
 <form class="search search--m" role="search" action="{U('poisk/')}"><label class="sr" for="qm">Поиск</label>{ic('search')}<input id="qm" name="q" type="search" placeholder="Размер, бренд или артикул"></form>
 <a href="{U('shiny/zimnie/')}">Зимние шины</a><a href="{U('shiny/letnie/')}">Летние шины</a><a href="{U('diski/')}">Диски</a>
 <a href="{U('kolesa/')}">Колёса в сборе</a><a href="{U('vykup/')}">Выкуп шин</a><a href="{U('shinomontazh/')}">Шиномонтаж</a><a href="{U('dostavka/')}">Доставка</a><a href="{U('kontakty/')}">Контакты</a><a href="{U('izbrannoe/')}">Избранное</a>
 <p class="mmenu__info">{E(CFG['city'])}, {E(CFG['address'])}<br>{E(CFG['hours'])}</p>
</div></div>
</header>'''


def footer_html():
    demo = ('<p class="footer__demo">Демо-сайт для портфолио: ассортимент, цены и контакты вымышленные, заявки никуда не отправляются.</p>'
            if CFG.get('demo') else '')
    return f'''<footer class="footer"><div class="wrap footer__in">
 <a class="logo logo--inv" href="{U()}" aria-label="Протектор - на главную">{LOGO}<span class="logo__txt"><b>ПРОТЕКТОР</b><small>{E(CFG['tagline'])}</small></span></a>
 <div class="footer__contacts"><p>{ic('pin')}{E(CFG['city'])}, {E(CFG['address'])}</p><p>{ic('phone')}<a href="{tel_href()}" data-goal="call">{E(CFG['phone'])}</a></p></div>
 <nav class="footer__nav" aria-label="Разделы"><a href="{U('shiny/')}">Шины</a><a href="{U('diski/')}">Диски</a><a href="{U('vykup/')}">Выкуп</a><a href="{U('dostavka/')}">Доставка</a><a href="{U('kontakty/')}">Контакты</a><a href="{U('politika/')}">Политика конфиденциальности</a></nav>
 <div class="footer__soc"><a href="{wa_href()}" data-goal="whatsapp" aria-label="WhatsApp" rel="nofollow noopener" target="_blank">{ic('wa')}</a><a href="{tg_href()}" data-goal="telegram" aria-label="Telegram" rel="nofollow noopener" target="_blank">{ic('tg')}</a></div>
 <p class="footer__copy">© {TODAY.year} {E(CFG['site_name'])}</p>
</div>{('<div class="wrap">' + demo + '</div>') if demo else ''}</footer>'''


def consent():
    return (f'<label class="consent"><input type="checkbox" name="agree" required> <span>Согласен на обработку персональных данных '
            f'по <a href="{U("politika/")}" target="_blank">политике</a></span></label>')


def dialogs_html():
    return f'''<dialog class="dlg" id="dlg-lead" aria-labelledby="dlg-lead-t"><form class="dlg__box form" method="dialog" data-form="lead" novalidate>
 <button class="dlg__x" type="button" data-close aria-label="Закрыть">{ic('close')}</button>
 <div class="form__body"><h2 class="dlg__t" id="dlg-lead-t">Оставить заявку</h2><p class="dlg__sub">Подберём шины или диски под ваш автомобиль и перезвоним за 15 минут.</p>
 <label class="fld"><span>Имя</span><input name="name" autocomplete="name" placeholder="Как к вам обращаться"></label>
 <label class="fld"><span>Телефон *</span><input name="phone" type="tel" autocomplete="tel" placeholder="+7 (___) ___-__-__" required data-phone></label>
 <label class="fld"><span>Что ищете</span><input name="what" placeholder="Например, 205/55 R16 зима"></label>
 {consent()}<button class="btn btn--y btn--wide" type="submit">Отправить заявку</button></div>
 <div class="form__ok" hidden>{ic('check')}<h2 class="dlg__t">Заявка принята</h2><p>Перезвоним в течение 15 минут в рабочее время ({E(CFG['hours'])}).</p><button class="btn btn--line" type="button" data-close>Хорошо</button></div>
</form></dialog>
<dialog class="dlg" id="dlg-bron" aria-labelledby="dlg-bron-t"><form class="dlg__box form" method="dialog" data-form="bron" novalidate>
 <button class="dlg__x" type="button" data-close aria-label="Закрыть">{ic('close')}</button>
 <div class="form__body"><h2 class="dlg__t" id="dlg-bron-t">Бронь на {CFG['reserve_days']} дня</h2>
 <div class="bron-item"><b data-bron-title></b><span data-bron-price></span></div>
 <p class="dlg__sub">Отложим комплект, пока вы едете. Предоплата не нужна.</p>
 <input type="hidden" name="sku">
 <label class="fld"><span>Имя</span><input name="name" autocomplete="name" placeholder="Как к вам обращаться"></label>
 <label class="fld"><span>Телефон *</span><input name="phone" type="tel" autocomplete="tel" placeholder="+7 (___) ___-__-__" required data-phone></label>
 {consent()}<button class="btn btn--y btn--wide" type="submit">Забронировать</button></div>
 <div class="form__ok" hidden>{ic('check')}<h2 class="dlg__t">Комплект отложен</h2><p data-bron-ok></p><button class="btn btn--line" type="button" data-close>Хорошо</button></div>
</form></dialog>
<div class="toast" role="status" aria-live="polite" hidden></div>'''


def mbar_html():
    return f'''<nav class="mbar" aria-label="Связаться"><a class="mbar__b" href="{tel_href()}" data-goal="call">{ic('phone')}Позвонить</a>
<a class="mbar__b" href="{wa_href()}" data-goal="whatsapp" rel="nofollow noopener" target="_blank">{ic('wa')}WhatsApp</a>
<button class="mbar__b mbar__b--y" type="button" data-open="lead">Заявка</button></nav>'''


def metrika_html():
    mid = CFG.get('metrika_id')
    if not mid:
        return ''
    return ('<script>(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();'
            'k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})'
            '(window,document,"script","https://mc.yandex.ru/metrika/tag.js","ym");'
            f'ym({mid},"init",{{clickmap:true,trackLinks:true,accurateTrackBounce:true,webvisor:true}});</script>'
            f'<noscript><div><img src="https://mc.yandex.ru/watch/{mid}" style="position:absolute;left:-9999px" alt=""></div></noscript>')


def crumbs_html(crumbs):
    parts = []
    for i, (name, path) in enumerate(crumbs):
        last = i == len(crumbs) - 1
        parts.append(f'<span aria-current="page">{E(name)}</span>' if last else f'<a href="{U(path)}">{E(name)}</a>')
    return '<nav class="crumbs" aria-label="Навигация">' + '<span class="crumbs__sep">/</span>'.join(parts) + '</nav>'


def crumbs_ld(crumbs):
    return {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': ABS(p)} for i, (n, p) in enumerate(crumbs)]}


def org_ld():
    return {'@type': 'TireShop', '@id': ABS() + '#org', 'name': CFG['site_name'], 'description': 'Б/у шины и диски с проверкой',
            'url': ABS(), 'telephone': '+' + re.sub(r'\D', '', CFG['phone']), 'image': ABS('assets/img/og.png'),
            'logo': ABS('assets/img/logo.png'), 'priceRange': '₽₽',
            'address': {'@type': 'PostalAddress', 'streetAddress': CFG['address'], 'addressLocality': CFG['city'],
                        'postalCode': CFG['postal_code'], 'addressCountry': 'RU'},
            'geo': {'@type': 'GeoCoordinates', 'latitude': CFG['geo'][0], 'longitude': CFG['geo'][1]},
            'openingHours': CFG['opening_hours'],
            'aggregateRating': {'@type': 'AggregateRating', 'ratingValue': CFG['rating']['value'], 'reviewCount': CFG['rating']['count']}}


PAGES = {}  # path -> dict(robots, sitemap, lastmod)


def write_page(path, html_text, robots='index,follow', lastmod=None, sitemap=True):
    out = DIST / path / 'index.html' if (path == '' or path.endswith('/')) else DIST / path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding='utf-8')
    PAGES[path] = dict(robots=robots, sitemap=sitemap and robots.startswith('index'), lastmod=lastmod or TODAY)


def layout(path, title, desc, body, crumbs=None, ld=None, robots='index,follow', og_image=None, og_type='website',
           body_cls='', lastmod=None, sitemap=True, canonical=None):
    graph = list(ld or [])
    if crumbs:
        graph.append(crumbs_ld(crumbs))
    ld_html = ''
    if graph:
        ld_html = ('<script type="application/ld+json">' +
                   json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False).replace('</', '<\\/') + '</script>')
    canon = ABS(canonical if canonical is not None else path)
    og_img = ABS(og_image) if og_image else ABS('assets/img/og.png')
    yv = f'<meta name="yandex-verification" content="{E(CFG["yandex_verification"])}">\n' if CFG.get('yandex_verification') else ''
    page_cfg = json.dumps({'base': BASE, 'demo': bool(CFG.get('demo')), 'metrika': CFG.get('metrika_id') or '',
                           'phone': CFG['phone'], 'reserveDays': CFG['reserve_days'], 'today': TODAY.isoformat()}, ensure_ascii=False)
    doc = f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canon}">
{yv}<meta property="og:type" content="{og_type}"><meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{canon}"><meta property="og:image" content="{og_img}"><meta property="og:locale" content="ru_RU"><meta property="og:site_name" content="{E(CFG['site_name'])}">
<meta name="theme-color" content="#1e2224">
<link rel="icon" href="{U('assets/img/favicon.svg')}" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Unbounded:wght@700;800&display=swap">
<link rel="stylesheet" href="{U('assets/css/site.css')}?v={VERSION}">
{ld_html}
<script>window.PK={page_cfg}</script>
{metrika_html()}
</head>
<body class="{body_cls}">
{sprite()}
<a class="skip" href="#main">Перейти к содержимому</a>
{header_html()}
<main id="main">
{body}
</main>
{footer_html()}
{mbar_html()}
{dialogs_html()}
<script src="{U('assets/js/metrika.js')}?v={VERSION}"></script>
<script src="{U('assets/js/app.js')}?v={VERSION}" defer></script>
</body>
</html>
'''
    write_page(path, doc, robots, lastmod, sitemap)


# ---------------------------------------------------------------- структура каталога

def size_slug(size):
    return slugify(size.replace('/', ' '))


def pcd_slug(pcd):
    return slugify(pcd)


def tire_size_url(season, size):
    p = f'shiny/{SEASON_SLUG[season]}/{size_slug(size)}/'
    return p if p in LANDINGS else f'shiny/{size_slug(size)}/'


def wheel_url_by_label(label):
    m = re.match(r'R(\d+)\s+(\S+)', label)
    return f'diski/r{m.group(1)}-{pcd_slug(m.group(2))}/' if m else 'diski/'


def is_live(it):
    return it['status'] != 'sold' or (TODAY - it['sold']).days <= CFG['sold_keep_days']


def in_stock(it):
    return it['status'] in ('stock', 'reserved')


def sets_word(n):
    return plural(n, 'комплект', 'комплекта', 'комплектов')


def sort_fresh(items):
    return sorted(items, key=lambda t: (t['added'], t['sku']), reverse=True)


def tire_landing_path(t):
    return f'shiny/{SEASON_SLUG[t["season"]]}/{size_slug(t["size"])}/'


def wheel_landing_path(w):
    return f'diski/r{w["d"]}-{pcd_slug(w["pcd"])}/'


def build_landings():
    L = {}
    tl = [t for t in TIRES if is_live(t)]
    wl = [w for w in WHEELS if is_live(w)]

    def add(path, kind, items, h1, crumbs, preset, **kw):
        L[path] = dict(path=path, kind=kind, items=items, stock=[i for i in items if in_stock(i)], h1=h1,
                       crumbs=crumbs, preset=preset, **kw)

    home = ('Главная', '')
    add('shiny/', 'tire', tl, 'Б/у шины', [home, ('Шины', 'shiny/')], {}, scope='all')
    for s in ('zima', 'leto', 'vsesezon'):
        items = [t for t in tl if t['season'] == s]
        if items:
            add(f'shiny/{SEASON_SLUG[s]}/', 'tire', items, f'{SEASON_NAME[s]} шины б/у',
                [home, ('Шины', 'shiny/'), (SEASON_NAME[s], f'shiny/{SEASON_SLUG[s]}/')], {'season': [s]}, scope='season', season=s)
    sizes = sorted({t['size'] for t in tl}, key=lambda z: (int(z[-2:]), z))
    for z in sizes:
        items = [t for t in tl if t['size'] == z]
        w, h, d = items[0]['w'], items[0]['h'], items[0]['d']
        add(f'shiny/{size_slug(z)}/', 'tire', items, f'Шины {z} б/у', [home, ('Шины', 'shiny/'), (z, f'shiny/{size_slug(z)}/')],
            {'w': w, 'h': h, 'd': d}, scope='size', size=z)
        for s in ('zima', 'leto', 'vsesezon'):
            si = [t for t in items if t['season'] == s]
            if si:
                add(f'shiny/{SEASON_SLUG[s]}/{size_slug(z)}/', 'tire', si, f'{SEASON_NAME[s]} шины {z} б/у',
                    [home, ('Шины', 'shiny/'), (SEASON_NAME[s], f'shiny/{SEASON_SLUG[s]}/'), (z, f'shiny/{SEASON_SLUG[s]}/{size_slug(z)}/')],
                    {'w': w, 'h': h, 'd': d, 'season': [s]}, scope='season_size', size=z, season=s)
    add('diski/', 'wheel', wl, 'Б/у диски', [home, ('Диски', 'diski/')], {}, scope='all')
    for d in sorted({w['d'] for w in wl}):
        items = [w for w in wl if w['d'] == d]
        add(f'diski/r{d}/', 'wheel', items, f'Диски R{d} б/у', [home, ('Диски', 'diski/'), (f'R{d}', f'diski/r{d}/')],
            {'d': d}, scope='d', d=d)
        for pcd in sorted({w['pcd'] for w in items}):
            pi = [w for w in items if w['pcd'] == pcd]
            add(f'diski/r{d}-{pcd_slug(pcd)}/', 'wheel', pi, f'Диски R{d} {pcd}',
                [home, ('Диски', 'diski/'), (f'R{d}', f'diski/r{d}/'), (pcd, f'diski/r{d}-{pcd_slug(pcd)}/')],
                {'d': d, 'pcd': pcd}, scope='d_pcd', d=d, pcd=pcd)
    return L


# ---------------------------------------------------------------- карточки

def nophoto(kind):
    return dict(sm=f'assets/img/nophoto-{kind}.svg', big=f'assets/img/nophoto-{kind}.svg', w=1080, h=720, cap='')


def first_photo(it):
    return it['photos'][0] if it['photos'] else nophoto(it['kind'])


def img_tag(ph, alt, cls='', sizes='(max-width: 767px) 100vw, 320px', lazy=True, big=False, prio=False):
    src = ph['big'] if big else ph['sm']
    attrs = [f'class="{cls}"'] if cls else []
    attrs.append(f'src="{U(src)}"')
    if ph['sm'] != ph['big']:
        attrs.append(f'srcset="{U(ph["sm"])} {SIZES[0]}w, {U(ph["big"])} {SIZES[1]}w" sizes="{sizes}"')
    attrs.append(f'alt="{E(alt)}" width="{ph["w"]}" height="{ph["h"]}"')
    if lazy:
        attrs.append('loading="lazy"')
    if prio:
        attrs.append('fetchpriority="high"')
    attrs.append('decoding="async"')
    return '<img ' + ' '.join(attrs) + '>'


def full_title(it):
    if it['kind'] == 'tire':
        return f'{it["title"]} {it["size"]} {it["li"]}{it["si"]}, {it["qty"]} шт'
    return f'{wheel_h1_name(it)} {it["spec"]}, {it["qty"]} шт'


def wheel_h1_name(w):
    if w['wkind'].startswith('шт'):
        return 'Штампованные диски'
    if w['origin'] == 'оригинал' and w['make']:
        o = f' {w["make"]} оригинал'
    elif w['origin'] == 'реплика':
        o = ' реплика'
    else:
        o = ''
    return f'{w["wkind"].capitalize()} диски{o}'


def bron_attrs(it):
    return f'data-bron="{E(it["sku"])}" data-title="{E(full_title(it))}" data-price="{E(rub(it["price"]))}"'


def landing_of(it):
    return tire_landing_path(it) if it['kind'] == 'tire' else wheel_landing_path(it)


def card(it, lazy=True):
    url = U(it['url'])
    ph = first_photo(it)
    sold = it['status'] == 'sold'
    alt = f'{full_title(it)}, фото {"для примера" if it.get("demo_photo") else "комплекта"}'
    badge = ''
    if sold:
        badge = '<span class="sold-band">Продано</span>'
    elif it['status'] == 'reserved':
        badge = '<span class="badge badge--res">В брони</span>'
    st = f'<span class="state state--{state_cls(it["state"])}">{ic("check")}<span>{E(it["state"] if it["kind"] == "tire" else it["full_state"])}</span></span>'
    if it['kind'] == 'tire':
        tags = ''.join(f'<span class="tag">{E(x)}</span>' for x in (it['type_name'], str(it['year']) if it['year'] else '') if x)
        meta = f'<p class="card__meta"><span>{E(it["size"])} {E(it["li"] + it["si"])}</span>{tags}</p>'
        rows = (f'<p class="card__row">{ic("tread", "i--g")}<span>Протектор: {mm(it["avg"])} мм</span></p>'
                f'<p class="card__row">{ic("tires")}<span>{it["qty"]} шт</span>{"" if sold else st}</p>')
    else:
        meta = f'<p class="card__meta card__meta--spec">{E(it["spec"])}</p>'
        rows = f'<p class="card__row">{ic("rim")}<span>{it["qty"]} шт</span></p>' + ('' if sold else f'<p class="card__row card__row--st">{st}</p>')
    if sold:
        foot = (f'<div class="card__foot card__foot--sold"><s class="card__old">{rub(it["price"])}</s>'
                f'<a class="card__more" href="{U(landing_of(it))}">Смотреть похожие{ic("arrow")}</a></div>')
    else:
        each = f'<small>{rub(it["each"])}/шт</small>' if it['qty'] > 1 else '<small>за 1 шт</small>'
        if it['status'] == 'stock':
            btn = f'<button class="btn btn--y btn--sm" type="button" {bron_attrs(it)}>Забронировать</button>'
        else:
            btn = '<button class="btn btn--line btn--sm" type="button" data-open="lead">Узнать о брони</button>'
        foot = f'<div class="card__foot"><p class="card__price"><b>{rub(it["price"])}</b>{each}</p>{btn}</div>'
    return (f'<article class="card card--{it["kind"]}{" is-sold" if sold else ""}" data-sku="{E(it["sku"])}">'
            f'<a class="card__img" href="{url}" tabindex="-1" aria-hidden="true">{img_tag(ph, alt, lazy=lazy)}{badge}</a>'
            f'<button class="card__fav" type="button" data-fav="{E(it["sku"])}" aria-label="В избранное" aria-pressed="false">{ic("heart")}</button>'
            f'<div class="card__body"><h2 class="card__t"><a href="{url}">{E(it["title"])}</a></h2>{meta}{rows}{foot}</div></article>')


def mini_card(it):
    ph = first_photo(it)
    sub = f'{mm(it["avg"])} мм' if it['kind'] == 'tire' else it['spec']
    return (f'<a class="mini" href="{U(it["url"])}">{img_tag(ph, full_title(it), "mini__img", sizes="160px")}'
            f'<span class="mini__body"><b>{E(it["title"])}</b><span>{E(sub)}</span><strong>{rub(it["price"])}</strong></span>{ic("chev-r", "mini__chev")}</a>')


def item_json(it):
    base = dict(sku=it['sku'], url=U(it['url']), html=card(it), st=it['status'], price=it['price'], qty=it['qty'],
                added=it['added'].toordinal(), sold=it['sold'].toordinal() if it['sold'] else 0, title=full_title(it),
                name=it['title'], img=U(first_photo(it)['sm']))
    if it['kind'] == 'tire':
        base.update(season=it['season'], w=it['w'], h=it['h'], d=it['d'], size=it['size'], brand=it['brand'],
                    type='ship' if it['studs'] else ('lip' if it['studs'] is False else ''), year=it['year'], tread=it['avg'])
    else:
        base.update(d=it['d'], width=it['width'], pcd=it['pcd'], et=it['et'], co=it['co'], kind=it['wkind'], origin=it['origin'])
    return base


# ---------------------------------------------------------------- общие блоки

def check_block():
    steps = [('tires', 'Замеряем протектор<br>на каждом колесе'), ('loupe', 'Проверяем на грыжи,<br>порезы и ремонты'),
             ('calendar', 'Смотрим дату<br>выпуска (DOT)'), ('camera', 'Фотографируем<br>без фильтров')]
    li = ''.join(f'<li>{ic(i)}<span>{t}</span></li>' for i, t in steps)
    return f'<section class="block check"><h2 class="h2">Как мы проверяем каждый комплект</h2><ul class="check__list">{li}</ul></section>'


def buyout_block(full=False):
    title = 'Выкупим ваши шины'
    return f'''<section class="block buy" id="vykup-form"><div class="buy__head"><h2 class="buy__t">{title}</h2><p>Оценим по фото за 15 минут</p></div>
<form class="buy__form form" data-form="vykup" novalidate><div class="form__body buy__fields">
 <label class="buy__drop">{ic('image')}<span><b>Загрузить фото</b><small>или перетащите сюда</small></span><input type="file" name="photo" accept="image/*" multiple></label>
 <label class="fld"><span>Размер</span><input name="size" placeholder="Например, 205/55 R16"></label>
 <label class="fld"><span>Телефон</span><input name="phone" type="tel" placeholder="+7 (___) ___-__-__" required data-phone autocomplete="tel"></label>
 <button class="btn btn--y" type="submit">Оценить</button>
 {consent() if full else ''}</div>
 <div class="form__ok buy__ok" hidden>{ic('check')}<p><b>Фото получили.</b> Оценщик напишет в WhatsApp или перезвонит в течение 15 минут.</p></div>
</form></section>'''


def reviews_block():
    r = CFG['rating']
    cards = ''.join(f'''<figure class="rev"><img class="rev__ava" src="{U('assets/img/ava-' + x['avatar'] + '.webp')}" alt="" width="56" height="56" loading="lazy">
<figcaption><b>{E(x['name'])}</b><span class="rev__stars" role="img" aria-label="5 из 5">{ic('star') * 5}</span></figcaption><blockquote>{E(x['text'])}</blockquote></figure>'''
                    for x in CFG['reviews'])
    return f'''<section class="block revs"><div class="revs__head"><p class="revs__rate">{ic('star')}<b>{comma(r['value'])} на {E(r['source'])}</b> · {r['count']} отзывов</p>
<a class="link" href="{U('kontakty/')}">Все отзывы{ic('arrow')}</a></div><div class="revs__list">{cards}</div></section>'''


# ---------------------------------------------------------------- тексты посадочных

def top_brands(items, n=3):
    from collections import Counter
    return [b for b, _ in Counter(i['brand'] for i in items).most_common(n)]


def landing_texts(L):
    st, items = L['stock'], L['items']
    n = len(st)
    city = CFG['city_in']
    prices = [i['price'] for i in st] or [i['price'] for i in items]
    pmin = min(prices) if prices else 0
    core = L['h1'].replace(' б/у', '').replace('Б/у ', '')
    core_l = core[0].lower() + core[1:]
    core_c = core[0].upper() + core[1:]
    title = (f'{core_c} б/у {city} - {n} {sets_word(n)} от {rub(pmin)} | {CFG["site_name"]}' if n
             else f'{core_c} б/у {city} - под заказ | {CFG["site_name"]}')
    seo_h2 = f'Б/у {core_l} {city}'
    if L['kind'] == 'tire':
        what_gen = {'all': 'шин', 'season': f'{SEASON_GEN.get(L.get("season"), "")} шин', 'size': f'шин {L.get("size", "")}',
                    'season_size': f'{SEASON_GEN.get(L.get("season"), "")} шин {L.get("size", "")}'}[L['scope']]
        brands = ', '.join(top_brands(st or items))
        desc = (f'{n} {sets_word(n)} {what_gen} б/у с проверкой: остаток протектора по каждому колесу, год выпуска, реальные фото. '
                f'{brands}. Бронь на {CFG["reserve_days"]} дня, шиномонтаж при покупке комплекта бесплатно.')
        ship = sum(1 for i in st if i['studs'])
        lip = sum(1 for i in st if i['studs'] is False)
        avg = sum(i['avg'] for i in st) / n if n else 0
        p1 = (f'В «{CFG["site_name"]}е» можно подобрать б/у {what_gen} с проверкой и честным описанием состояния. '
              f'Сейчас в наличии {n} {sets_word(n)}' + (f' от брендов {E(brands)} и других' if brands else '') + '. ')
        if ship or lip:
            p1 += f'Шипованных - {ship}, на липучке - {lip}. '
        if n:
            p1 += f'Цены от {rub(min(prices))} до {rub(max(prices))} за комплект.'
        p2 = ('Каждый комплект проходит проверку: замеряем остаток протектора на каждом колесе, смотрим грыжи, порезы и ремонты, '
              'определяем год выпуска по DOT и фотографируем без фильтров. ')
        if n:
            p2 += f'Средний остаток протектора в этой подборке - {mm(avg)} мм. '
        p2 += f'Комплект можно забронировать на {CFG["reserve_days"]} дня, а шиномонтаж при покупке комплекта - бесплатно.'
        if L.get('size'):
            cars = next((i['cars'] for i in items if i['cars']), '')
            if cars:
                p2 += f' Размер {L["size"]} ставят на {E(cars)}.'
    else:
        what = {'all': 'дисков', 'd': f'дисков R{L.get("d")}', 'd_pcd': f'дисков R{L.get("d")} {L.get("pcd")}'}[L['scope']]
        kinds = sorted({i['wkind'] for i in st})
        desc = (f'{n} {sets_word(n)} {what} б/у: литые оригинальные, реплики и штампованные. Указываем PCD, вылет ET и ЦО, '
                f'показываем сколы и следы ремонта на фото. Бронь на {CFG["reserve_days"]} дня.')
        p1 = (f'В наличии {n} {sets_word(n)} {what}' + (f': {", ".join(kinds)}' if kinds else '') + '. ' +
              (f'Цены от {rub(min(prices))} до {rub(max(prices))} за комплект. ' if n else '') +
              'У каждого комплекта указаны диаметр, ширина, сверловка PCD, вылет ET и центральное отверстие, чтобы диски сели без проставок и колец.')
        p2 = ('Перед продажей проверяем диски на стенде: нет ли биения, трещин и следов сварки. Сколы, бордюрку и правку описываем '
              'в карточке и показываем на фото крупным планом.')
        if L.get('pcd'):
            cars = sorted({i['cars'] for i in items if i['cars']}, key=len)
            if cars:
                p2 += f' Сверловка {L["pcd"]} подходит, например, на {E(cars[-1])} - проверяйте ЦО и вылет под свой автомобиль.'
    return dict(title=title, desc=desc, seo_h2=seo_h2, p1=p1, p2=p2)


def landing_chips(L):
    chips = []
    if L['kind'] == 'tire':
        season = L.get('season') or 'zima'
        for z in CFG['popular_tire_sizes']:
            p = tire_size_url(season, z) if L['scope'] in ('season', 'season_size') else f'shiny/{size_slug(z)}/'
            if p in LANDINGS:
                chips.append((z, p, z == L.get('size')))
        if L.get('size') and L.get('season'):
            for s in ('leto', 'zima', 'vsesezon'):
                p = f'shiny/{SEASON_SLUG[s]}/{size_slug(L["size"])}/'
                if s != L['season'] and p in LANDINGS:
                    chips.append((f'{SEASON_NAME[s]} {L["size"]}', p, False))
        if L['scope'] in ('all', 'size'):
            for s in ('zima', 'leto'):
                p = f'shiny/{SEASON_SLUG[s]}/'
                if p in LANDINGS:
                    chips.insert(0, (f'{SEASON_NAME[s]}', p, False))
    else:
        for lab in CFG['popular_wheels']:
            p = wheel_url_by_label(lab)
            if p in LANDINGS:
                chips.append((lab, p, p == L['path']))
    return chips


def similar_links(L):
    out = []
    if L['kind'] == 'tire' and L.get('size'):
        if L.get('season'):
            for s in ('leto', 'zima', 'vsesezon'):
                p = f'shiny/{SEASON_SLUG[s]}/{size_slug(L["size"])}/'
                if s != L['season'] and p in LANDINGS and LANDINGS[p]['stock']:
                    out.append((f'{L["size"]} {SEASON_NAME[s].lower().replace("ние", "о").replace("всесезонные", "всесезон")}', p))
        same_d = [z for z in CFG['popular_tire_sizes'] if z != L['size']]
        same_d.sort(key=lambda z: (z[-3:] != L['size'][-3:], z))
        for z in same_d[:3]:
            p = tire_size_url(L.get('season') or 'zima', z)
            if p in LANDINGS:
                out.append((f'{z} {SEASON_NAME[L.get("season") or "zima"].lower().replace("ние", "а").replace("всесезонные", "всесезон")}', p))
    elif L['kind'] == 'wheel' and L.get('d'):
        for p, X in LANDINGS.items():
            if X['kind'] == 'wheel' and X['scope'] == 'd_pcd' and X['path'] != L['path'] and X['stock'] and (X['d'] == L['d'] or X['pcd'] == L.get('pcd')):
                out.append((f'R{X["d"]} {X["pcd"]}', p))
    return out[:4]


# ---------------------------------------------------------------- фильтры

PRICE_STEPS = [2000, 4000, 8000, 12000, 16000, 20000, 30000, 40000, 60000]


def opt(v, label, cur):
    return f'<option value="{E(str(v))}"{" selected" if str(cur) == str(v) else ""}>{E(str(label))}</option>'


def ck(name, value, label, checked=False, count=None):
    n = f'<em class="ck__n" data-n="{E(str(value))}">{count}</em>' if count is not None else ''
    return (f'<label class="ck"><input type="checkbox" name="{name}" value="{E(str(value))}"{" checked" if checked else ""}>'
            f'<span class="ck__box"></span><span class="ck__l">{E(label)}</span>{n}</label>').replace('<label class="ck">', '<label class="ck is-zero">' if count == 0 else '<label class="ck">')


def filters_html(L, stock_count):
    pre = L['preset']
    head = (f'<div class="flt__head"><p class="flt__title">Фильтры</p><button class="flt__reset" type="button" data-flt-reset>Сбросить</button>'
            f'<button class="flt__x" type="button" data-flt-close aria-label="Закрыть фильтры">{ic("close")}</button></div>')
    price = (f'<fieldset class="flt__g"><legend>Цена</legend><div class="flt__two">'
             f'<label class="sel"><span class="sr">Цена от</span><select name="pmin">{opt("", "от 0 ₽", "")}{"".join(opt(p, "от " + rub(p), "") for p in PRICE_STEPS[:-1])}</select>{ic("chev")}</label>'
             f'<label class="sel"><span class="sr">Цена до</span><select name="pmax">{opt("", "любая", "")}{"".join(opt(p, "до " + rub(p), "") for p in PRICE_STEPS[1:])}</select>{ic("chev")}</label></div></fieldset>')
    qty = f'<fieldset class="flt__g"><legend>Количество</legend><div class="flt__row">{ck("qty", 4, "4 шт")}{ck("qty", 2, "2 шт")}{ck("qty", 1, "1 шт")}</div></fieldset>'
    stock = (f'<label class="tgl"><input type="checkbox" name="stock" value="1" checked><span class="tgl__s"></span><span>Только в наличии</span></label>')
    go = (f'<button class="btn btn--y btn--wide flt__go" type="button" data-flt-apply>Показать <span data-count>{stock_count}</span></button>'
          f'<button class="flt__reset flt__reset--foot" type="button" data-flt-reset>Сбросить фильтры</button>')
    if L['kind'] == 'tire':
        pool = [t for t in TIRES if is_live(t)]
        ws = sorted({t['w'] for t in pool}); hs = sorted({t['h'] for t in pool}); ds = sorted({t['d'] for t in pool})
        size = (f'<fieldset class="flt__g"><legend>Размер</legend><div class="flt__three">'
                f'<label class="sel"><span class="sr">Ширина</span><select name="w">{opt("", "Ширина", pre.get("w", ""))}{"".join(opt(v, v, pre.get("w", "")) for v in ws)}</select>{ic("chev")}</label>'
                f'<label class="sel"><span class="sr">Профиль</span><select name="h">{opt("", "Профиль", pre.get("h", ""))}{"".join(opt(v, v, pre.get("h", "")) for v in hs)}</select>{ic("chev")}</label>'
                f'<label class="sel"><span class="sr">Диаметр</span><select name="d">{opt("", "Диаметр", pre.get("d", ""))}{"".join(opt(v, f"R{v}", pre.get("d", "")) for v in ds)}</select>{ic("chev")}</label>'
                f'</div></fieldset>')
        seasons = pre.get('season', [])
        season = (f'<fieldset class="flt__g"><legend>Сезон</legend><div class="flt__col">' +
                  ''.join(ck('season', s, SEASON_SHORT[s], s in seasons) for s in ('zima', 'leto', 'vsesezon')) + '</div></fieldset>')
        typ = f'<fieldset class="flt__g" data-g="type"><legend>Тип</legend><div class="flt__col">{ck("type", "ship", "Шипованные")}{ck("type", "lip", "Липучка")}</div></fieldset>'
        from collections import Counter
        bc = Counter(t['brand'] for t in L['stock'])
        # все бренды раздела, чтобы выбранный бренд не терялся при переходе на другую посадочную; пустые - серые
        bpool = [t for t in pool if t['season'] in pre['season']] if pre.get('season') else pool
        allb = sorted({t['brand'] for t in bpool}, key=lambda b: (-bc.get(b, 0), b))
        brand = (f'<fieldset class="flt__g"><legend>Бренд</legend><div class="flt__col flt__brands">' +
                 ''.join(ck('brand', b, b, False, bc.get(b, 0)) for b in allb) + '</div></fieldset>')
        tread = (f'<fieldset class="flt__g"><legend>Остаток протектора</legend><div class="range">'
                 f'<output data-tread-out>от 0 мм</output><input type="range" name="tread" min="0" max="10" step="0.5" value="0" aria-label="Остаток протектора не меньше, мм"></div></fieldset>')
        years = sorted({t['year'] for t in pool if t['year']})
        year = (f'<fieldset class="flt__g"><legend>Год выпуска</legend><label class="sel"><span class="sr">Год выпуска от</span>'
                f'<select name="year">{opt("", "любой", "")}{"".join(opt(y, f"от {y}", "") for y in years)}</select>{ic("chev")}</label></fieldset>')
        body = size + season + typ + brand + tread + year + qty + price
    else:
        pool = [w for w in WHEELS if is_live(w)]
        ds = sorted({w['d'] for w in pool}); pcds = sorted({w['pcd'] for w in pool})
        ets = sorted({w['et'] for w in pool}); cos = sorted({w['co'] for w in pool}); widths = sorted({w['width'] for w in pool})
        size = (f'<fieldset class="flt__g"><legend>Диаметр и сверловка</legend><div class="flt__two">'
                f'<label class="sel"><span class="sr">Диаметр</span><select name="d">{opt("", "Диаметр", pre.get("d", ""))}{"".join(opt(v, f"R{v}", pre.get("d", "")) for v in ds)}</select>{ic("chev")}</label>'
                f'<label class="sel"><span class="sr">PCD</span><select name="pcd">{opt("", "PCD", pre.get("pcd", ""))}{"".join(opt(v, v, pre.get("pcd", "")) for v in pcds)}</select>{ic("chev")}</label>'
                f'</div></fieldset>')
        et = (f'<fieldset class="flt__g"><legend>Вылет ET</legend><div class="flt__two">'
              f'<label class="sel"><span class="sr">ET от</span><select name="etmin">{opt("", "от", "")}{"".join(opt(v, f"от {v}", "") for v in ets)}</select>{ic("chev")}</label>'
              f'<label class="sel"><span class="sr">ET до</span><select name="etmax">{opt("", "до", "")}{"".join(opt(v, f"до {v}", "") for v in ets)}</select>{ic("chev")}</label></div></fieldset>')
        co = f'<fieldset class="flt__g"><legend>ЦО, мм</legend><div class="flt__row flt__row--wrap">' + ''.join(ck('co', c, comma(c)) for c in cos) + '</div></fieldset>'
        wd = f'<fieldset class="flt__g"><legend>Ширина</legend><div class="flt__row flt__row--wrap">' + ''.join(ck('width', x, f'{comma(x)}J') for x in widths) + '</div></fieldset>'
        kind = (f'<fieldset class="flt__g"><legend>Тип</legend><div class="flt__col">' +
                ''.join(ck('kind', k, k.capitalize()) for k in sorted({w['wkind'] for w in pool})) + '</div></fieldset>')
        origin = (f'<fieldset class="flt__g"><legend>Происхождение</legend><div class="flt__col">{ck("origin", "оригинал", "Оригинал")}{ck("origin", "реплика", "Реплика")}</div></fieldset>')
        body = size + et + co + wd + kind + origin + qty + price
    return f'<form class="flt__form" data-flt onsubmit="return false">{head}<div class="flt__body">{body}{stock}</div><div class="flt__foot">{go}</div></form>'


def pager_html(n, per):
    pages = max(1, -(-n // per))
    if pages == 1:
        return ''
    nums = ''.join(f'<a class="pager__n{" is-on" if i == 1 else ""}" href="?page={i}" rel="nofollow"{" aria-current=" + chr(34) + "page" + chr(34) if i == 1 else ""}>{i}</a>'
                   for i in range(1, min(pages, 3) + 1))
    if pages > 4:
        nums += '<span class="pager__gap">…</span>'
    if pages > 3:
        nums += f'<a class="pager__n" href="?page={pages}" rel="nofollow">{pages}</a>'
    return (f'<div class="pager__nums">{nums}<a class="pager__n pager__next" href="?page=2" rel="nofollow" aria-label="Следующая страница">{ic("chev-r")}</a></div>'
            f'<button class="btn btn--line pager__more" type="button" data-more>Показать ещё</button>')


def render_landing(L):
    tx = landing_texts(L)
    per = CFG['per_page']
    stock = sort_fresh(L['stock'])
    sold = sorted([i for i in L['items'] if i['status'] == 'sold'], key=lambda i: i['sold'], reverse=True)[:4]
    n = len(stock)
    unit = 'комплект' if True else ''
    count_txt = f'{n} {sets_word(n)} в наличии' if n else 'Сейчас нет в наличии'
    cards = ''.join(card(it, lazy=i > 2) for i, it in enumerate(stock[:per]))
    if not stock:
        cards = ''
    chips = ''.join(f'<a class="chip{" is-on" if on else ""}" href="{U(p)}"{" aria-current=" + chr(34) + "page" + chr(34) if on else ""}>{E(lab)}</a>'
                    for lab, p, on in landing_chips(L))
    sold_html = ''
    if sold:
        sold_html = (f'<section class="sold-recent" data-sold-recent><h2 class="h3">Недавно продано</h2>'
                     f'<p class="muted">Проданные комплекты висят на сайте {CFG["sold_keep_days"]} дней с плашкой «Продано» - так видно, что ассортимент живой.</p>'
                     f'<div class="grid grid--sold">{"".join(card(i) for i in sold)}</div></section>')
    sim = similar_links(L)
    sim_html = ('<p class="seo__sim"><b>Похожие размеры:</b> ' + ' '.join(f'<a class="link" href="{U(p)}">{E(lab)}</a>' for lab, p in sim) + '</p>') if sim else ''
    cat_cfg = json.dumps({'kind': L['kind'], 'preset': L['preset'], 'path': L['path'], 'per': per, 'scope': L['scope']}, ensure_ascii=False)
    empty_note = '' if n else '<p class="empty__lead">Этот размер сейчас разобрали. Оставьте заявку - позвоним, как только привезём.</p>'
    body = f'''<div class="wrap">
{crumbs_html(L['crumbs'])}
<div class="cat-head"><h1 class="h1">{E(L['h1'])}</h1><p class="cat-head__count" data-count-text>{count_txt}</p></div>
{f'<nav class="chips" aria-label="Популярные размеры">{chips}</nav>' if chips else ''}
<div class="cat" data-catalog='{E(cat_cfg)}'>
 <aside class="flt" id="flt" aria-label="Фильтры">{filters_html(L, n)}</aside>
 <div class="flt-shade" data-flt-close hidden></div>
 <section class="res" aria-label="Товары">
  <div class="res__bar"><button class="btn btn--line res__fbtn" type="button" data-flt-open aria-controls="flt">{ic('filter')}Фильтры<span class="res__fn" data-fn hidden></span></button>
   <label class="sel sel--inline"><span class="sr">Сортировка</span><select data-sort><option value="new">Сначала свежие</option><option value="cheap">Сначала дешевле</option><option value="exp">Сначала дороже</option><option value="tread">По остатку протектора</option></select>{ic('chev')}</label>
   <div class="view" role="group" aria-label="Вид списка"><button class="view__b is-on" type="button" data-view="grid" aria-pressed="true">{ic('grid')}<span>Плитка</span></button><button class="view__b" type="button" data-view="list" aria-pressed="false">{ic('list')}<span>Список</span></button></div>
  </div>
  <div class="active" data-active></div>
  {empty_note}
  <div class="grid grid--{L['kind']}" data-grid>{cards}</div>
  <div class="empty" data-empty hidden><p>По таким фильтрам ничего нет.</p><button class="btn btn--line" type="button" data-flt-reset>Сбросить фильтры</button> <button class="btn btn--y" type="button" data-open="lead">Подобрать под заказ</button></div>
  <nav class="pager" data-pager aria-label="Страницы">{pager_html(n, per)}</nav>
  {sold_html}
 </section>
</div>
{check_block()}
{buyout_block()}
{reviews_block()}
<section class="block seo"><h2 class="h2">{E(tx['seo_h2'])}</h2><div class="seo__cols"><p>{tx['p1']}</p><p>{tx['p2']}</p></div>{sim_html}</section>
</div>'''
    ld = [{'@type': 'CollectionPage', 'name': L['h1'], 'url': ABS(L['path']), 'description': tx['desc'],
           'mainEntity': {'@type': 'ItemList', 'numberOfItems': n, 'itemListElement': [
               {'@type': 'ListItem', 'position': i + 1, 'url': ABS(it['url'])} for i, it in enumerate(stock[:per])]}}]
    robots = 'index,follow' if n else 'noindex,follow'
    lastmod = max([i['added'] for i in L['items']] + [i['sold'] for i in L['items'] if i['sold']], default=TODAY)
    og = stock[0]['photos'][0]['big'] if stock and stock[0]['photos'] else None
    layout(L['path'], tx['title'], tx['desc'], body, crumbs=L['crumbs'], ld=ld, robots=robots, og_image=og,
           body_cls='page-cat', lastmod=lastmod)


# ---------------------------------------------------------------- карточка товара

def similar_items(it, n=3):
    pool = [x for x in (TIRES if it['kind'] == 'tire' else WHEELS) if x is not it and x['status'] == 'stock']
    if it['kind'] == 'tire':
        same = [x for x in pool if x['size'] == it['size'] and x['season'] == it['season']]
        if len(same) < n:
            same += [x for x in pool if x['d'] == it['d'] and x['season'] == it['season'] and x not in same]
        # сначала комплекты со своими фото, потом ближайшие по протектору и цене
        same.sort(key=lambda x: (not x['photos'] or x.get('demo_photo', False), x['qty'] != it['qty'],
                                 abs(x['avg'] - it['avg']) + abs(x['price'] - it['price']) / 8000))
    else:
        same = [x for x in pool if x['d'] == it['d'] and x['pcd'] == it['pcd']]
        same.sort(key=lambda x: (not x['photos'] or x.get('demo_photo', False), x['co'] != it['co'], abs(x['et'] - it['et']), abs(x['price'] - it['price'])))
    return same[:n]


def tire_condition_box(t):
    new = 12 if t['season'] == 'zima' else 9
    bars = ''.join(f'<li><span>Колесо {i + 1}</span><span class="bar" aria-hidden="true"><i style="width:{min(100, round(v / new * 100))}%"></i></span><b>{mm(v)} мм</b></li>'
                   for i, v in enumerate(t['treads']))
    rows = [('Грыжи и порезы', t['hernia']), ('Ремонты', t['repairs'])]
    if t['studs']:
        rows.append(('Выпавших шипов', t['studs_lost'] or '0'))
    rows_html = ''.join(f'<div><dt>{E(a)}:</dt><dd>{E(str(b))}</dd></div>' for a, b in rows)
    return (f'<section class="box"><h2 class="box__t">Состояние</h2><ul class="wheels">{bars}</ul>'
            f'<p class="avg"><span>Средний остаток</span><b>{mm(t["avg"])} мм</b></p><dl class="kv kv--plain">{rows_html}</dl></section>')


def tire_spec_box(t):
    li = num(t['li'])
    rows = [('Сезон', SEASON_SHORT[t['season']])]
    if t['type_name']:
        rows.append(('Тип', 'шипованные' if t['studs'] else 'липучка'))
    rows += [('Год выпуска', t['year']), ('DOT', t['dot'] or '-'),
             ('Индекс нагрузки', f'{t["li"]} ({LOAD_KG[li]} кг)' if li in LOAD_KG else t['li']),
             ('Индекс скорости', f'{t["si"]} (до {SPEED[t["si"]]} км/ч)' if t['si'] in SPEED else t['si']),
             ('Количество', f'{t["qty"]} шт')]
    return spec_box(rows, t['cars'])


def spec_box(rows, cars):
    dl = ''.join(f'<div><dt>{E(a)}</dt><dd>{E(str(b))}</dd></div>' for a, b in rows if b not in ('', None))
    tags = ''.join(f'<span class="tag tag--l">{E(c.strip())}</span>' for c in cars.split(',') if c.strip())
    fit = f'<h3 class="box__st">Подойдут на</h3><div class="tags">{tags}</div>' if tags else ''
    return f'<section class="box"><h2 class="box__t">Характеристики</h2><dl class="kv">{dl}</dl>{fit}</section>'


def wheel_boxes(w):
    cond = [('Общее состояние', w['state']), ('Дефекты', w['defects'] or 'нет'), ('Правка', w['repair']), ('Цвет', w['color']),
            ('Проверка на стенде', 'биения нет')]
    cond_html = ''.join(f'<div><dt>{E(a)}:</dt><dd>{E(str(b))}</dd></div>' for a, b in cond if b)
    box1 = f'<section class="box"><h2 class="box__t">Состояние</h2><dl class="kv kv--plain">{cond_html}</dl></section>'
    origin = {'оригинал': f'оригинал {w["make"]}'.strip(), 'реплика': f'реплика {w["make"]}'.strip()}.get(w['origin'], '')
    rows = [('Диаметр', f'R{w["d"]}'), ('Ширина', f'{comma(w["width"])}J'), ('Сверловка (PCD)', w['pcd']), ('Вылет (ET)', w['et']),
            ('ЦО', f'{comma(w["co"])} мм'), ('Тип', w['wkind']), ('Происхождение', origin), ('Модель', w['wmodel']),
            ('Количество', f'{w["qty"]} шт')]
    return box1 + spec_box(rows, w['cars'])


def product_ld(it, desc):
    avail = {'stock': 'InStock', 'reserved': 'Reserved', 'sold': 'SoldOut'}[it['status']]
    imgs = [ABS(p['big']) for p in it['photos']] or [ABS(nophoto(it['kind'])['big'])]
    props = []
    if it['kind'] == 'tire':
        props = [('Сезон', SEASON_SHORT[it['season']]), ('Размер', it['size']), ('Остаток протектора, мм', it['avg']),
                 ('Год выпуска', it['year']), ('Количество, шт', it['qty'])]
        cat = f'Шины > {SEASON_NAME[it["season"]]} шины'
        brand = it['brand']
    else:
        props = [('Диаметр', f'R{it["d"]}'), ('PCD', it['pcd']), ('Вылет ET', it['et']), ('ЦО, мм', it['co']), ('Количество, шт', it['qty'])]
        cat = 'Диски'
        brand = it['make'] if it['origin'] == 'оригинал' else ''
    p = {'@type': 'Product', '@id': ABS(it['url']) + '#product', 'name': full_title(it) + ' б/у', 'sku': it['sku'], 'mpn': it['sku'],
         'image': imgs, 'description': desc, 'category': cat, 'itemCondition': 'https://schema.org/UsedCondition',
         'additionalProperty': [{'@type': 'PropertyValue', 'name': a, 'value': b} for a, b in props],
         'offers': {'@type': 'Offer', 'url': ABS(it['url']), 'price': it['price'], 'priceCurrency': 'RUB',
                    'availability': f'https://schema.org/{avail}', 'itemCondition': 'https://schema.org/UsedCondition',
                    'priceValidUntil': (TODAY + timedelta(days=30)).isoformat(),
                    'eligibleQuantity': {'@type': 'QuantitativeValue', 'value': it['qty'], 'unitCode': 'H87'},
                    'seller': {'@type': 'TireShop', '@id': ABS() + '#org', 'name': CFG['site_name']}}}
    if brand:
        p['brand'] = {'@type': 'Brand', 'name': brand}
    if it['kind'] == 'tire':
        p['model'] = it['model']
    return p


def product_crumbs(it):
    if it['kind'] == 'tire':
        s = it['season']
        return [('Главная', ''), ('Шины', 'shiny/'), (SEASON_NAME[s], f'shiny/{SEASON_SLUG[s]}/'), (it['size'], tire_landing_path(it)), (it['title'], it['url'])]
    return [('Главная', ''), ('Диски', 'diski/'), (f'R{it["d"]}', f'diski/r{it["d"]}/'), (it['pcd'], wheel_landing_path(it)),
            (it['title'] if not it['wmodel'] else f'{it["title"]}', it['url'])]


def render_product(it):
    sold = it['status'] == 'sold'
    tire = it['kind'] == 'tire'
    photos = it['photos'] or [nophoto(it['kind'])]
    name = full_title(it)
    slides, ths = [], []
    for i, p in enumerate(photos):
        alt = f'{name} - {p["cap"] or "фото " + str(i + 1)}'
        img = img_tag(p, alt, sizes='(max-width: 1023px) 100vw, 720px', lazy=i > 0, big=True, prio=i == 0)
        slides.append(f'<figure class="gal__slide">{img}</figure>')
        cap = f'<span>{E(p["cap"])}</span>' if p['cap'] else ''
        lab = f'Фото {i + 1}' + (f': {p["cap"]}' if p['cap'] else '')
        on = ' is-on' if i == 0 else ''
        ths.append(f'<button class="gal__th{on}" type="button" data-th="{i}" aria-label="{E(lab)}">'
                   f'<img src="{U(p["sm"])}" alt="" width="{p["w"]}" height="{p["h"]}" loading="lazy">{cap}</button>')
    slides = ''.join(slides)
    thumbs = f'<div class="gal__thumbs">{"".join(ths)}</div>' if len(photos) > 1 else ''
    if it.get('demo_photo'):
        note = 'Фото для примера: в рабочем каталоге здесь снимки именно этого комплекта'
    elif it['photos']:
        note = f'Реальные фото этого комплекта, сняты {ddmmyyyy(it["added"])}'
    else:
        note = 'Фото готовим - пришлём в WhatsApp по запросу'
    band = '<span class="sold-band sold-band--big">Продано</span>' if sold else ''
    if tire:
        h1 = f'{E(it["title"])}<br>{E(it["size"])} {E(it["li"] + it["si"])}, {it["qty"]} шт б/у'
        unit = 'за шину'
    else:
        h1 = f'{E(wheel_h1_name(it))}<br>{E(it["spec"])}, {it["qty"]} шт б/у'
        unit = 'за диск'
    if sold:
        avail = f'<p class="avail avail--sold">Продано {ddmmyyyy(it["sold"])}</p>'
        price = f'<p class="pp__price pp__price--sold"><s>{rub(it["price"])}</s> <span>за комплект</span></p>'
        btns = (f'<div class="pp__btns"><a class="btn btn--y btn--lg" href="#similar">Смотреть похожие</a>'
                f'<button class="btn btn--line btn--lg" type="button" data-open="lead">Подобрать под заказ</button></div>')
        perk = f'<p class="pp__soldnote">Этот комплект уже купили. Ниже - похожие в наличии, а <a class="link" href="{U(landing_of(it))}">все комплекты {E(it["size"] if tire else it["pcd"])}</a> - на странице размера.</p>'
    else:
        if it['status'] == 'reserved':
            avail = f'<p class="avail avail--res">В брони · можно встать в очередь</p>'
        else:
            avail = f'<p class="avail avail--ok">{ic("check")}В наличии · склад на {E(CFG["address"].split(",")[0])}</p>'
        each = f'<p class="pp__each">{rub(it["each"])} {unit}</p>' if it['qty'] > 1 else ''
        price = f'<p class="pp__price"><b>{rub(it["price"])}</b> <span>за комплект</span></p>{each}'
        main_btn = (f'<button class="btn btn--y btn--lg" type="button" {bron_attrs(it)}>Забронировать на {CFG["reserve_days"]} дня</button>'
                    if it['status'] == 'stock' else '<button class="btn btn--y btn--lg" type="button" data-open="lead">Узнать, когда освободится</button>')
        btns = (f'<div class="pp__btns">{main_btn}'
                f'<a class="btn btn--line btn--lg" href="{wa_href("Здравствуйте! Интересует " + it["sku"] + ", " + name)}" data-goal="whatsapp" rel="nofollow noopener" target="_blank">{ic("wa")}WhatsApp</a>'
                f'<a class="btn btn--line btn--lg" href="{tel_href()}" data-goal="call">{ic("phone")}Позвонить</a></div>')
        perk = (f'<p class="pp__perk">{ic("wrench")}Шиномонтаж при покупке комплекта - бесплатно</p>' if tire
                else f'<p class="pp__perk">{ic("wrench")}Поможем с подбором: проверим вылет и ЦО под ваш автомобиль</p>')
    boxes = (tire_condition_box(it) + tire_spec_box(it)) if tire else wheel_boxes(it)
    note_html = f'<p class="pp__note"><b>Комментарий продавца:</b> {E(it["note"])}</p>' if it['note'] else ''
    sim = similar_items(it)
    sim_title = f'Похожие комплекты {it["size"]}' if tire else f'Похожие диски R{it["d"]} {it["pcd"]}'
    sim_html = (f'<section class="similar" id="similar"><h2 class="h2">{E(sim_title)}</h2><div class="sim">{"".join(mini_card(x) for x in sim)}</div></section>'
                if sim else '')
    body = f'''<div class="wrap">
{crumbs_html(product_crumbs(it))}
<div class="pp{' pp--sold' if sold else ''}">
 <div class="pp__gal gal" data-gal><div class="gal__main" data-gal-main tabindex="0" role="region" aria-label="Галерея, листайте">{slides}</div>{band}
  {thumbs}<p class="gal__note">{E(note)}</p>{note_html}</div>
 <div class="pp__info">
  <h1 class="pp__t">{h1}</h1>
  <p class="pp__sku">Артикул {E(it['sku'])}</p>
  {avail}{price}{btns}{perk}
  <div class="pp__boxes">{boxes}</div>
 </div>
</div>
{sim_html}
</div>'''
    if tire:
        desc = (f'Б/у {SEASON_NAME[it["season"]].lower()} шины {it["title"]} {it["size"]} {it["li"]}{it["si"]}'
                f'{", " + it["type_name"].lower() if it["type_name"] else ""}, {it["year"]} год, {it["qty"]} шт. '
                f'Протектор {"/".join(mm(v) for v in it["treads"])} мм, грыжи: {it["hernia"]}, ремонты: {it["repairs"]}. ')
        title = f'{it["title"]} {it["size"]} {it["li"]}{it["si"]} б/у, {it["qty"]} шт, протектор {mm(it["avg"])} мм'
    else:
        desc = (f'{wheel_h1_name(it)} {it["spec"]}, {it["qty"]} шт б/у. Состояние: {it["full_state"].lower()}, правка: {it["repair"]}. ')
        title = f'{wheel_h1_name(it)} {it["spec"]} б/у, {it["qty"]} шт'
    if sold:
        desc += f'Продано {ddmmyyyy(it["sold"])} - смотрите похожие комплекты в наличии.'
        title += f' - продано, арт. {it["sku"]} | {CFG["site_name"]}'
    else:
        desc += f'{rub(it["price"])} за комплект {CFG["city_in"]}, бронь на {CFG["reserve_days"]} дня.'
        title += f' - {rub(it["price"])}, арт. {it["sku"]} | {CFG["site_name"]}'
    layout(it['url'], title, desc, body, crumbs=product_crumbs(it), ld=[product_ld(it, desc)], og_type='product',
           og_image=it['photos'][0]['big'] if it['photos'] else None, body_cls='page-product',
           lastmod=it['sold'] or it['added'])


def render_redirect(old, target, reason):
    """Страница-заглушка для GitHub Pages, где нет серверных 301. На обычном хостинге
    те же пары лежат в dist/.htaccess и deploy/nginx-redirects.conf."""
    url = U(target)
    doc = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Страница переехала</title>
<meta name="robots" content="noindex,follow"><link rel="canonical" href="{ABS(target)}">
<meta http-equiv="refresh" content="0; url={url}"><script>location.replace({json.dumps(url)})</script></head>
<body><p>{E(reason)} <a href="{url}">Перейти</a></p></body></html>'''
    write_page(old, doc, 'noindex,follow', sitemap=False)
    REDIRECTS.append((U(old), url))


REDIRECTS = []


# ---------------------------------------------------------------- главная и служебные страницы

def pick_html():
    tl = [t for t in TIRES if in_stock(t)]
    wl = [w for w in WHEELS if in_stock(w)]
    ws = sorted({t['w'] for t in tl}); hs = sorted({t['h'] for t in tl}); ds = sorted({t['d'] for t in tl})
    n = len([t for t in tl if t['size'] == '205/55 R16' and t['season'] == 'zima'])
    sel = lambda name, label, opts, cur: (f'<label class="fld fld--sel"><span>{label}</span><span class="sel"><select name="{name}">'
                                           + ''.join(opt(v, l, cur) for v, l in opts) + f'</select>{ic("chev")}</span></label>')
    tires = (f'<form class="pick__form" action="{U("shiny/")}" method="get" data-pick-form="tire">'
             f'<div class="pick__grid">{sel("w", "Ширина", [("", "любая")] + [(v, v) for v in ws], 205)}{sel("h", "Профиль", [("", "любой")] + [(v, v) for v in hs], 55)}'
             f'{sel("d", "Диаметр", [("", "любой")] + [(v, f"R{v}") for v in ds], 16)}'
             f'{sel("season", "Сезон", [("zima", "Зима"), ("leto", "Лето"), ("vsesezon", "Всесезонные"), ("", "Любой")], "zima")}</div>'
             f'<button class="btn btn--y btn--wide btn--lg" type="submit">Показать <span data-pick-count>{n}</span> <span data-pick-word>{sets_word(n)}</span></button></form>')
    wds = sorted({w['d'] for w in wl}); pcds = sorted({w['pcd'] for w in wl}); cos = sorted({w['co'] for w in wl})
    nw = len([w for w in wl if w['d'] == 17 and w['pcd'] == '5x114,3'])
    wheels = (f'<form class="pick__form" action="{U("diski/")}" method="get" data-pick-form="wheel" hidden>'
              f'<div class="pick__grid">{sel("d", "Диаметр", [("", "любой")] + [(v, f"R{v}") for v in wds], 17)}{sel("pcd", "PCD", [("", "любая")] + [(v, v) for v in pcds], "5x114,3")}'
              f'{sel("et", "Вылет ET", [("", "любой"), ("30-39", "30-39"), ("40-44", "40-44"), ("45-47", "45-47"), ("48-55", "48-55")], "")}'
              f'{sel("co", "ЦО", [("", "любой")] + [(c, comma(c)) for c in cos], "")}</div>'
              f'<button class="btn btn--y btn--wide btn--lg" type="submit">Показать <span data-pick-count>{nw}</span> <span data-pick-word>{sets_word(nw)}</span></button></form>')
    return (f'<div class="pick" data-pick><div class="pick__tabs" role="tablist" aria-label="Что подбираем">'
            f'<button class="pick__tab is-on" type="button" role="tab" aria-selected="true" data-tab="tire">Шины</button>'
            f'<button class="pick__tab" type="button" role="tab" aria-selected="false" data-tab="wheel">Диски</button></div>{tires}{wheels}</div>')


def render_home():
    tl = [t for t in TIRES if in_stock(t)]
    wl = [w for w in WHEELS if in_stock(w)]
    fresh = sort_fresh(tl)[:8]
    fresh_w = sort_fresh(wl)[:4]
    chips = ''.join(f'<a class="chip" href="{U(tire_size_url("zima", z))}">{E(z)}</a>' for z in CFG['popular_tire_sizes'])
    wchips = ''.join(f'<a class="chip" href="{U(wheel_url_by_label(z))}">{E(z)}</a>' for z in CFG['popular_wheels'] if wheel_url_by_label(z) in LANDINGS)
    hero_img = ''
    key = next((t for t in TIRES if t['sku'] == 'Ш-1048' and t['photos']), None) or next((t for t in fresh if t['photos']), None)
    if key:
        hero_img = (f'<figure class="hero__img">{img_tag(key["photos"][0], "Склад б/у шин Протектор, комплект " + key["title"], sizes="(max-width: 1023px) 0px, 560px", lazy=False, big=True, prio=True)}'
                    f'<figcaption>{ic("tread", "i--g")}Протектор замеряем на каждом колесе</figcaption></figure>')
    body = f'''<section class="hero"><div class="wrap hero__in">
 <div class="hero__main"><h1 class="h1 hero__t">Б/у шины и диски с проверкой</h1><p class="hero__sub">Остаток протектора - на каждом фото</p>
 {pick_html()}
 <div class="hero__pop"><p class="hero__pop-t">Популярные размеры</p><nav class="chips chips--sm" aria-label="Популярные размеры">{chips}</nav></div></div>
 {hero_img}
</div></section>
<div class="wrap">
<section class="block"><div class="block__head"><h2 class="h2">Свежие поступления</h2><a class="link" href="{U('shiny/')}">Все шины - {len(tl)} {sets_word(len(tl))}{ic('arrow')}</a></div>
<div class="grid grid--tire grid--4">{''.join(card(t, lazy=i > 1) for i, t in enumerate(fresh))}</div></section>
<section class="block"><div class="block__head"><h2 class="h2">Диски</h2><a class="link" href="{U('diski/')}">Все диски - {len(wl)} {sets_word(len(wl))}{ic('arrow')}</a></div>
<nav class="chips" aria-label="Популярные диски">{wchips}</nav>
<div class="grid grid--wheel grid--4">{''.join(card(w) for w in fresh_w)}</div></section>
{check_block()}
{buyout_block()}
{reviews_block()}
<section class="block seo"><h2 class="h2">Б/у шины и диски {CFG['city_in']}</h2><div class="seo__cols">
<p>«{CFG['site_name']}» - склад б/у шин и дисков на {E(CFG['address'])}. В наличии {len(tl)} {sets_word(len(tl))} шин и {len(wl)} {sets_word(len(wl))} дисков: зимние шипованные и липучка, летние, литые оригинальные диски и штампованные. Ассортимент обновляется каждый день - всё, что на сайте, лежит на складе.</p>
<p>У каждого комплекта замер протектора по каждому колесу, год выпуска по DOT, грыжи и ремонты, если есть, и реальные фото без фильтров. Понравившийся комплект можно забронировать на {CFG['reserve_days']} дня без предоплаты, а при покупке комплекта шиномонтаж бесплатно.</p></div></section>
</div>'''
    title = f'Б/у шины и диски {CFG["city_in"]} с проверкой протектора | {CFG["site_name"]}'
    desc = (f'Склад б/у шин и дисков {CFG["city_in"]}: {len(tl)} {sets_word(len(tl))} шин и {len(wl)} дисков. '
            f'Замер протектора по каждому колесу, год выпуска, реальные фото. Подбор по размеру, бронь на {CFG["reserve_days"]} дня.')
    ld = [org_ld(), {'@type': 'WebSite', '@id': ABS() + '#site', 'url': ABS(), 'name': CFG['site_name'], 'inLanguage': 'ru'}]
    layout('', title, desc, body, ld=ld, body_cls='page-home')


def simple_page(path, h1, title, desc, content, crumbs_name=None, ld=None, robots='index,follow', extra=''):
    crumbs = [('Главная', ''), (crumbs_name or h1, path)]
    body = f'<div class="wrap">{crumbs_html(crumbs)}<h1 class="h1 page-t">{E(h1)}</h1><div class="prose">{content}</div>{extra}</div>'
    layout(path, title, desc, body, crumbs=crumbs if robots.startswith('index') else None, ld=ld, robots=robots,
           sitemap=robots.startswith('index'), body_cls='page-simple')


def render_static():
    city = CFG['city_in']
    simple_page('vykup/', 'Выкуп б/у шин и дисков', f'Выкуп б/у шин и дисков {city} - оценка по фото за 15 минут | {CFG["site_name"]}',
                f'Выкупаем б/у шины и диски {city}: пришлите фото и размер, оценим за 15 минут. Деньги сразу при сдаче на {CFG["address"]}.',
                '<ol class="steps"><li><b>Пришлите фото</b><span>Боковина с размером, протектор с монетой или глубиномером, DOT</span></li>'
                '<li><b>Получите оценку</b><span>Оценщик ответит за 15 минут в рабочее время</span></li>'
                f'<li><b>Привезите на склад</b><span>{E(CFG["address"])}, {E(CFG["hours"])}</span></li><li><b>Деньги сразу</b><span>Наличными или переводом после осмотра</span></li></ol>'
                '<h2 class="h3">Что выкупаем</h2><ul><li>Зимние и летние шины R14-R20 с остатком протектора от 5 мм (зима) и от 4 мм (лето), не старше 7 лет.</li>'
                '<li>Литые и штампованные диски без трещин и сварки, комплектом или парой.</li><li>Колёса в сборе - шины на дисках.</li></ul>'
                '<p>Не берём шины с грыжами, боковыми порезами и шины старше 7 лет.</p>', extra=buyout_block(full=True))
    rows = ''.join(f'<tr><td>R{d}</td><td>{rub(p)}</td><td>{rub(p + 400)}</td></tr>' for d, p in ((14, 1600), (15, 1800), (16, 2000), (17, 2400), (18, 2800), (19, 3200), (20, 3600)))
    simple_page('shinomontazh/', 'Шиномонтаж', f'Шиномонтаж {city} - цены за комплект | {CFG["site_name"]}',
                f'Шиномонтаж на {CFG["address"]}: снятие, установка, балансировка. При покупке комплекта б/у шин - бесплатно.',
                f'<p class="lead-p">{ic("wrench")}При покупке комплекта шин у нас шиномонтаж бесплатно.</p>'
                '<div class="table-wrap"><table class="table"><caption class="sr">Цены за комплект из 4 колёс</caption><thead><tr><th>Диаметр</th><th>Легковой</th><th>Кроссовер</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div><p class="muted">Цена за комплект из 4 колёс: снятие, монтаж, балансировка. Запись по телефону {E(CFG["phone"])}.</p>')
    simple_page('dostavka/', 'Доставка и самовывоз', f'Доставка б/у шин и дисков {city} | {CFG["site_name"]}',
                f'Самовывоз со склада на {CFG["address"]}, доставка по городу в день заказа, отправка в регионы транспортными компаниями.',
                f'<h2 class="h3">Самовывоз</h2><p>{E(CFG["city"])}, {E(CFG["address"])}, {E(CFG["hours"])}. Забронированный комплект ждёт вас {CFG["reserve_days"]} дня.</p>'
                '<h2 class="h3">По городу</h2><p>В день заказа, 500 ₽. При покупке от 20 000 ₽ - бесплатно.</p>'
                '<h2 class="h3">В другие города</h2><p>Отправляем СДЭК, ПЭК и Деловыми Линиями. Перед отправкой присылаем видео протектора и упаковки.</p>')
    simple_page('kolesa/', 'Колёса в сборе', f'Б/у колёса в сборе {city} - шины на дисках | {CFG["site_name"]}',
                'Соберём колёса под ваш автомобиль: подберём б/у шины и диски по размеру, смонтируем и отбалансируем.',
                '<p>Подберём шины и диски из наличия под ваш автомобиль, смонтируем и отбалансируем - забираете готовые колёса.</p>'
                f'<p>Напишите марку, модель и год автомобиля - пришлём варианты с фото. <button class="btn btn--y" type="button" data-open="lead">Подобрать колёса</button></p>')
    simple_page('kontakty/', 'Контакты', f'Контакты склада б/у шин {CFG["site_name"]} {city}', f'{CFG["city"]}, {CFG["address"]}, {CFG["hours"]}. Телефон {CFG["phone"]}.',
                f'<div class="contacts"><p>{ic("pin")}{E(CFG["city"])}, {E(CFG["address"])}</p><p>{ic("clock")}{E(CFG["hours"])}</p>'
                f'<p>{ic("phone")}<a href="{tel_href()}" data-goal="call">{E(CFG["phone"])}</a></p>'
                f'<p><a class="btn btn--line" href="{wa_href()}" data-goal="whatsapp" rel="nofollow noopener" target="_blank">{ic("wa")}WhatsApp</a> '
                f'<a class="btn btn--line" href="{tg_href()}" data-goal="telegram" rel="nofollow noopener" target="_blank">{ic("tg")}Telegram</a></p></div>',
                ld=[org_ld()], extra=reviews_block())
    simple_page('politika/', 'Политика конфиденциальности', f'Политика конфиденциальности | {CFG["site_name"]}', 'Как мы обрабатываем персональные данные из форм на сайте.',
                '<p>Мы получаем имя и телефон, которые вы оставляете в формах заявки, брони и выкупа, и используем их только чтобы связаться с вами по этой заявке. '
                'Данные не передаём третьим лицам, кроме случаев, предусмотренных законом. Сайт использует Яндекс.Метрику для подсчёта посещений и целей (звонок, заявка, бронь).</p>'
                '<p>Чтобы отозвать согласие или удалить данные, напишите нам в WhatsApp или позвоните.</p>', robots='noindex,follow')
    simple_page('izbrannoe/', 'Избранное', f'Избранное | {CFG["site_name"]}', 'Отложенные комплекты.',
                '<p class="muted" data-fav-empty>Здесь появятся комплекты, отмеченные сердечком.</p><div class="grid grid--tire" data-fav-grid></div>', robots='noindex,follow')
    simple_page('poisk/', 'Поиск', f'Поиск | {CFG["site_name"]}', 'Поиск по каталогу шин и дисков.',
                '<p class="muted" data-search-info>Ищите по размеру (205/55 R16), бренду, модели или артикулу.</p><div class="grid grid--tire" data-search-grid></div>', robots='noindex,follow')
    chips = ''.join(f'<a class="chip" href="{U(tire_size_url("zima", z))}">{E(z)}</a>' for z in CFG['popular_tire_sizes'])
    body = (f'<div class="wrap nf"><h1 class="h1">Страница не найдена</h1><p>Возможно, комплект уже продан и снят с сайта. Посмотрите похожие:</p>'
            f'<nav class="chips" aria-label="Популярные размеры">{chips}</nav>'
            f'<p><a class="btn btn--y" href="{U("shiny/")}">Все шины</a> <a class="btn btn--line" href="{U("diski/")}">Все диски</a></p></div>')
    layout('404.html', f'Страница не найдена | {CFG["site_name"]}', 'Страница не найдена.', body, robots='noindex,follow', sitemap=False)


# ---------------------------------------------------------------- данные для JS, sitemap, robots, редиректы

def write_json():
    out = DIST / 'assets' / 'data'
    out.mkdir(parents=True, exist_ok=True)
    for kind, items in (('tires', TIRES), ('wheels', WHEELS)):
        land = sorted(p for p, L in LANDINGS.items() if L['kind'] == ('tire' if kind == 'tires' else 'wheel'))
        data = {'items': [item_json(i) for i in items if is_live(i)], 'landings': land, 'today': TODAY.toordinal()}
        (out / f'{kind}.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def fallback_chain(path):
    """Куда вести, если страницы больше нет: размер в другом сезоне -> сезон -> раздел."""
    m = re.match(r'shiny/(zimnie|letnie|vsesezonnye)/([^/]+)/$', path)
    if m:
        return [path, f'shiny/{m.group(2)}/', f'shiny/{m.group(1)}/', 'shiny/']
    m = re.match(r'shiny/([^/]+)/$', path)
    if m:
        return [path, 'shiny/']
    m = re.match(r'diski/(r\d+)-[^/]+/$', path)
    if m:
        return [path, f'diski/{m.group(1)}/', 'diski/']
    m = re.match(r'diski/(r\d+)/$', path)
    if m:
        return [path, 'diski/']
    return [path, 'shiny/' if path.startswith('shiny') else 'diski/' if path.startswith('diski') else '']


def best_existing(path):
    for p in fallback_chain(path):
        if p in LANDINGS and LANDINGS[p]['stock']:
            return p
    return 'shiny/' if path.startswith('shiny') else 'diski/' if path.startswith('diski') else ''


def handle_gone_and_history():
    hist_file = ROOT / 'data' / 'published_urls.json'
    hist = json.loads(hist_file.read_text(encoding='utf-8')) if hist_file.exists() else {}
    live = {i['url']: i for i in TIRES + WHEELS if is_live(i)}
    by_sku = {i['sku']: i for i in TIRES + WHEELS}
    done = set()
    for it in TIRES + WHEELS:
        if not is_live(it):
            target = best_existing(landing_of(it))
            render_redirect(it['url'], target, f'Комплект {it["sku"]} продан {ddmmyyyy(it["sold"])}.')
            done.add(it['url'])
            hist[it['url']] = {'sku': it['sku'], 'fallback': landing_of(it)}
    for path, info in sorted(hist.items()):
        if path in live or path in LANDINGS or path in done:
            continue
        it = by_sku.get(info.get('sku', ''))
        if it and is_live(it):
            target, why = it['url'], 'Адрес комплекта изменился.'
        else:
            target, why = best_existing(info.get('fallback') or path), 'Страницы больше нет.'
        render_redirect(path, target, why)
    for url, it in live.items():
        hist[url] = {'sku': it['sku'], 'fallback': landing_of(it)}
    for p in LANDINGS:
        hist.setdefault(p, {'fallback': p})
    hist_file.write_text(json.dumps(dict(sorted(hist.items())), ensure_ascii=False, indent=1), encoding='utf-8')


def write_seo_files():
    imgs = {}
    for it in TIRES + WHEELS:
        if is_live(it) and it['photos'] and not it.get('demo_photo'):
            imgs[it['url']] = [(ABS(p['big']), p['cap'] or full_title(it)) for p in it['photos'][:6]]
    urls = []
    for path, meta in sorted(PAGES.items(), key=lambda kv: (kv[0].count('/'), kv[0])):
        if not meta['sitemap']:
            continue
        pr = '1.0' if path == '' else '0.8' if path in LANDINGS else '0.6'
        im = ''.join(f'<image:image><image:loc>{E(u)}</image:loc><image:title>{E(t)}</image:title></image:image>' for u, t in imgs.get(path, []))
        urls.append(f'<url><loc>{E(ABS(path))}</loc><lastmod>{meta["lastmod"].isoformat()}</lastmod><priority>{pr}</priority>{im}</url>')
    (DIST / 'sitemap.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n' + '\n'.join(urls) + '\n</urlset>\n', encoding='utf-8')
    params = 'w&h&d&season&type&brand&tread&year&qty&pmin&pmax&stock&sort&view&page&pcd&etmin&etmax&et&co&width&kind&origin'
    utm = 'utm_source&utm_medium&utm_campaign&utm_content&utm_term&yclid&gclid&ysclid&from'
    b = BASE
    robots = f'''# Фильтры каталога работают через GET-параметры (?brand=...&tread=...).
# Посадочные страницы размеров - отдельные чистые адреса, параметры в индекс не пускаем.
User-agent: *
Disallow: {b}*?
Disallow: {b}poisk/
Disallow: {b}izbrannoe/
Allow: {b}assets/

User-agent: Yandex
Disallow: {b}poisk/
Disallow: {b}izbrannoe/
Clean-param: {params} {b}shiny/
Clean-param: {params} {b}diski/
Clean-param: {utm}
Allow: {b}assets/

Sitemap: {ABS('sitemap.xml')}
'''
    (DIST / 'robots.txt').write_text(robots, encoding='utf-8')
    # серверные 301 для обычного хостинга (Apache .htaccess и nginx), на GitHub Pages работают страницы-заглушки
    ht = ['# Сгенерировано build.py - не правьте руками', f'ErrorDocument 404 {U("404.html")}', 'Options -Indexes']
    ht += [f'Redirect 301 {a} {c}' for a, c in REDIRECTS]
    (DIST / '.htaccess').write_text('\n'.join(ht) + '\n', encoding='utf-8')
    (ROOT / 'deploy').mkdir(exist_ok=True)
    ng = ['# include в server { } - сгенерировано build.py'] + [f'location = {a} {{ return 301 {c}; }}' for a, c in REDIRECTS]
    (ROOT / 'deploy' / 'nginx-redirects.conf').write_text('\n'.join(ng) + '\n', encoding='utf-8')


def copy_assets():
    dst = DIST / 'assets'
    for sub in ('css', 'js', 'img'):
        if (SRC / sub).exists():
            shutil.copytree(SRC / sub, dst / sub, dirs_exist_ok=True)
    for f in ('showcase.html',):
        if (SRC / f).exists():
            shutil.copy2(SRC / f, DIST / f)
    (DIST / '.nojekyll').write_text('', encoding='utf-8')


def clean_dist():
    """Удаляет всё, кроме кеша ужатых фото (dist/assets/p), чтобы пересборка была быстрой."""
    if not DIST.exists():
        return
    for p in DIST.iterdir():
        if p.name == 'assets':
            for q in p.iterdir():
                if q.name != 'p':
                    shutil.rmtree(q) if q.is_dir() else q.unlink()
        else:
            shutil.rmtree(p) if p.is_dir() else p.unlink()


def serve(port):
    import functools, http.server, socketserver

    class H(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            p = path.split('?', 1)[0].split('#', 1)[0]
            if p.startswith(BASE):
                p = '/' + p[len(BASE):]
            return super().translate_path(p)

        def do_GET(self):
            if self.path in ('/robots.txt', '/sitemap.xml') and BASE != '/':
                self.path = BASE + self.path.lstrip('/')
            if not self.path.startswith(BASE.rstrip('/')):
                self.send_response(302)
                self.send_header('Location', BASE)
                self.end_headers()
                return
            fs = Path(self.translate_path(self.path))
            if fs.is_dir() and not (fs / 'index.html').exists() or not fs.exists():
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write((DIST / '404.html').read_bytes())
                return
            super().do_GET()

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('127.0.0.1', port), functools.partial(H, directory=str(DIST))) as srv:
        print(f'Сайт: http://localhost:{port}{BASE}  (Ctrl+C - остановить)')
        srv.serve_forever()


def main():
    global CFG, TODAY, BASE, ORIGIN, TIRES, WHEELS, LANDINGS, VERSION
    ap = argparse.ArgumentParser(description='Сборка сайта Протектор из CSV')
    ap.add_argument('--serve', action='store_true', help='после сборки запустить локальный сервер')
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--today', help='дата «сегодня» в формате 2026-10-15')
    ap.add_argument('--site-url', help='адрес сайта, например https://protektor-ekb.ru')
    ap.add_argument('--base', help='путь сайта от корня домена, например / или /protektor-demo/')
    a = ap.parse_args()
    CFG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    site_url = (a.site_url or CFG['site_url']).rstrip('/')
    m = re.match(r'(https?://[^/]+)', site_url)
    ORIGIN = m.group(1)
    BASE = a.base or CFG.get('base_path') or '/'
    BASE = '/' + BASE.strip('/') + '/' if BASE.strip('/') else '/'
    TODAY = date.fromisoformat(a.today or CFG.get('today') or date.today().isoformat())
    import hashlib
    h = hashlib.md5()
    for f in sorted((SRC).rglob('*.*')):
        if f.suffix in ('.css', '.js'):
            h.update(f.read_bytes())
    VERSION = h.hexdigest()[:8]

    fit = load_fitment()
    TIRES = load_tires(fit)
    WHEELS = load_wheels(fit)
    seen = {}
    for it in TIRES + WHEELS:
        if it['sku'] in seen:
            warn(f'{it["line"]}: артикул {it["sku"]} повторяется (первый раз - {seen[it["sku"]]})')
        seen[it['sku']] = it['line']
    clean_dist()
    DIST.mkdir(exist_ok=True)
    attach_photos(TIRES + WHEELS)
    LANDINGS = build_landings()
    copy_assets()
    render_home()
    for L in LANDINGS.values():
        render_landing(L)
    for it in TIRES + WHEELS:
        if is_live(it):
            render_product(it)
    render_static()
    handle_gone_and_history()
    write_json()
    write_seo_files()

    st_t = sum(1 for t in TIRES if in_stock(t))
    st_w = sum(1 for w in WHEELS if in_stock(w))
    print(f'Готово: {len(PAGES)} страниц в dist/ - шин в наличии {st_t}, дисков {st_w}, посадочных {len(LANDINGS)}, '
          f'редиректов {len(REDIRECTS)}. Сегодня = {TODAY.isoformat()}')
    if problems:
        print(f'\nЗамечания по таблицам ({len(problems)}):')
        for p in problems:
            print(' -', p)
    if a.serve:
        serve(a.port)


if __name__ == '__main__':
    main()
