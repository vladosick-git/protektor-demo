# Одноразовый генератор демо-ассортимента: data/tires.csv и data/wheels.csv.
# Ключевые позиции взяты из макетов, остальное досоздано правдоподобно (seed фиксирован).
# После первого запуска источник правды - сами CSV, этот скрипт больше не нужен.
#   python tools/make_demo_data.py          # не перезапишет существующие CSV
#   python tools/make_demo_data.py --force
import csv, random, sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = random.Random(1048)
TODAY = date(2026, 10, 15)

TIRE_COLS = ['артикул', 'статус', 'сезон', 'шипы', 'бренд', 'модель', 'ширина', 'профиль', 'диаметр',
             'индекс_нагрузки', 'индекс_скорости', 'год', 'dot', 'кол_во', 'протектор_мм', 'цена_комплект',
             'грыжи_порезы', 'ремонты', 'выпавшие_шипы', 'состояние', 'дата_поступления', 'дата_продажи', 'примечание']
WHEEL_COLS = ['артикул', 'статус', 'тип', 'происхождение', 'марка', 'модель_диска', 'диаметр', 'ширина', 'pcd', 'et', 'цо',
              'кол_во', 'цвет', 'состояние', 'дефекты', 'ремонт', 'цена_комплект', 'дата_поступления', 'дата_продажи', 'примечание']

WINTER = {
    'Michelin': [('X-Ice North 4', 1), ('X-Ice North 3', 1), ('X-Ice Snow', 0), ('Alpin 6', 0)],
    'Nokian Tyres': [('Hakkapeliitta 10', 1), ('Hakkapeliitta 9', 1), ('Hakkapeliitta R3', 0), ('Hakkapeliitta R5', 0), ('Nordman 7', 1)],
    'Continental': [('IceContact 3', 1), ('IceContact 2', 1), ('VikingContact 7', 0)],
    'Bridgestone': [('Blizzak Ice', 0), ('Blizzak Spike-02', 1), ('Blizzak VRX', 0)],
    'Hankook': [('Winter i*cept IZ2', 0), ('Winter i*Pike RS2', 1), ('Winter i*cept IZ3', 0)],
    'Pirelli': [('Ice Zero 2', 1), ('Ice Zero FR', 0), ('Ice Zero', 1)],
    'Yokohama': [('iceGuard Stud iG65', 1), ('iceGuard iG60', 0), ('iceGuard iG55', 1), ('iceGuard iG70', 0)],
}
SUMMER = {
    'Michelin': ['Primacy 4', 'Energy Saver+', 'Pilot Sport 4'],
    'Nokian Tyres': ['Hakka Green 3', 'Nordman SX3'],
    'Continental': ['PremiumContact 6', 'EcoContact 6'],
    'Bridgestone': ['Turanza T005', 'Ecopia EP150'],
    'Hankook': ['Ventus Prime 3', 'Kinergy Eco 2'],
    'Pirelli': ['Cinturato P7', 'Powergy'],
    'Yokohama': ['BluEarth-A AE50', 'Advan dB V552'],
    'Toyo': ['Proxes CF2'],
}
ALLSEASON = {'Michelin': ['CrossClimate+'], 'Nokian Tyres': ['Seasonproof'], 'Hankook': ['Kinergy 4S2']}
TIER = {'Michelin': 9600, 'Nokian Tyres': 9200, 'Continental': 9000, 'Pirelli': 8800, 'Bridgestone': 8400,
        'Yokohama': 7600, 'Hankook': 7000, 'Toyo': 6600}
SIZE_LI = {(195, 65, 15): ['91T', '95T'], (205, 55, 16): ['91T', '94T'], (205, 60, 16): ['92T', '96T'],
           (215, 60, 16): ['95T', '99T'], (215, 55, 17): ['94T', '98T'], (225, 45, 18): ['91T', '95T'],
           (215, 65, 16): ['98T', '102T']}
SIZE_K = {15: 0.75, 16: 1.0, 17: 1.25, 18: 1.5}

rows_t, rows_w = [], []
seq = iter(range(1100, 1400))


def d(n):
    return (TODAY - timedelta(days=n)).isoformat()


def tread_row(avg, qty):
    vals = [round(avg + R.choice([-0.2, -0.1, 0, 0, 0.1, 0.2]), 1) for _ in range(qty)]
    return '/'.join(f'{v:.1f}'.replace('.', ',') for v in vals)


def tire_price(brand, size, avg, year, qty, season):
    k = SIZE_K[size[2]] * (1.0 if season == 'зима' else 0.85)
    wear = max(0.35, (avg - 2.5) / (7.5 if season == 'зима' else 5.5))
    age = 1 - 0.06 * max(0, 2023 - year)
    per = TIER[brand] * k * wear * age * 1.0
    per = int(round(per / 100) * 100)
    return int(round(per * qty / 200) * 200)


def add_tire(sku, status, season, spikes, brand, model, size, li, year, qty, treads, price,
             hernia='нет', repairs='нет', studs='', state='', added=10, sold='', note='', dot=''):
    if not dot:
        dot = f'{R.randint(5, 48):02d}{year % 100:02d}'
    rows_t.append({
        'артикул': sku, 'статус': status, 'сезон': season, 'шипы': spikes, 'бренд': brand, 'модель': model,
        'ширина': size[0], 'профиль': size[1], 'диаметр': size[2], 'индекс_нагрузки': li[:-1], 'индекс_скорости': li[-1],
        'год': year, 'dot': dot, 'кол_во': qty, 'протектор_мм': treads, 'цена_комплект': price, 'грыжи_порезы': hernia,
        'ремонты': repairs, 'выпавшие_шипы': studs, 'состояние': state, 'дата_поступления': d(added),
        'дата_продажи': sold, 'примечание': note})


# --- ключевые позиции из макетов (205/55 R16 зима) ---
S = (205, 55, 16)
add_tire('Ш-1048', 'в наличии', 'зима', 'да', 'Nokian Tyres', 'Hakkapeliitta 10', S, '94T', 2022, 4, '8,6/8,5/8,4/8,5', 28400, studs='0', added=1, dot='1422',
         note='Шипы все на месте, хранились на дисках в тёплом гараже')
add_tire('Ш-1047', 'в наличии', 'зима', 'да', 'Michelin', 'X-Ice North 4', S, '94T', 2021, 4, '7,1/7,0/6,9/7,0', 22000, studs='2', added=1, dot='3821')
add_tire('Ш-1046', 'в наличии', 'зима', 'да', 'Continental', 'IceContact 3', S, '94T', 2020, 4, '6,6/6,5/6,4/6,5', 18800, studs='3', added=2, dot='4120')
add_tire('Ш-1045', 'в наличии', 'зима', 'нет', 'Hankook', 'Winter i*cept IZ2', S, '94T', 2022, 4, '7,6/7,5/7,5/7,4', 19600, added=2, dot='2622')
add_tire('Ш-1044', 'в наличии', 'зима', 'нет', 'Bridgestone', 'Blizzak Ice', S, '91T', 2021, 2, '6,0/6,0', 8400, added=3, dot='1721',
         note='Пара, удобно на одну ось')
add_tire('Ш-1043', 'продано', 'зима', 'да', 'Pirelli', 'Ice Zero 2', S, '94T', 2022, 4, '8,1/8,0/8,0/7,9', 24000, studs='0', added=3, sold=d(3), dot='0922')

# --- остальные 205/55 R16 зима: бренды Michelin 6, Nokian 8, Continental 5, Bridgestone 4, Hankook 7, Pirelli 3, Yokohama 5 в наличии ---
need = {'Michelin': 5, 'Nokian Tyres': 7, 'Continental': 4, 'Bridgestone': 3, 'Hankook': 6, 'Pirelli': 3, 'Yokohama': 5}


def gen_winter(size, brand, status='в наличии', added=None, sold=''):
    model, stud = R.choice(WINTER[brand])
    year = R.choice([2017, 2018, 2019, 2019, 2020, 2020, 2021, 2021, 2022, 2023])
    avg = round(R.uniform(5.0, 9.2) - max(0, 2021 - year) * 0.4, 1)
    avg = max(4.6, avg)
    qty = R.choice([4, 4, 4, 4, 4, 2, 2, 1])
    li = R.choice(SIZE_LI[size])
    hernia = 'нет'
    repairs = R.choice(['нет'] * 6 + ['1 латка', 'жгут на 1 колесе'])
    studs = str(R.choice([0, 0, 1, 2, 3, 5, 8])) if stud else ''
    price = tire_price(brand, size, avg, year, qty, 'зима')
    if repairs != 'нет':
        price = int(round(price * 0.9 / 200) * 200)
    add_tire(f'Ш-{next(seq)}', status, 'зима', 'да' if stud else 'нет', brand, model, size, li, year, qty,
             tread_row(avg, qty), price, hernia, repairs, studs, added=added if added is not None else R.randint(4, 60), sold=sold)


for brand, n in need.items():
    for _ in range(n):
        gen_winter(S, brand)
# недавно проданные (остаются в индексе с плашкой) и давно проданные (уходят в 301 на размер)
gen_winter(S, 'Nokian Tyres', 'продано', added=30, sold=d(8))
gen_winter(S, 'Michelin', 'продано', added=40, sold=d(21))
gen_winter(S, 'Continental', 'продано', added=120, sold=d(75))
gen_winter(S, 'Hankook', 'продано', added=150, sold=d(96))


def gen_summer(size, status='в наличии', season='лето', added=None, sold=''):
    pool = SUMMER if season == 'лето' else ALLSEASON
    brand = R.choice(list(pool))
    model = R.choice(pool[brand])
    year = R.choice([2018, 2019, 2020, 2021, 2021, 2022, 2023])
    avg = max(3.6, round(R.uniform(4.0, 7.4) - max(0, 2021 - year) * 0.3, 1))
    qty = R.choice([4, 4, 4, 2, 2])
    li = R.choice(SIZE_LI[size])
    price = tire_price(brand, size, avg, year, qty, 'лето')
    add_tire(f'Ш-{next(seq)}', status, season, '', brand, model, size, li, year, qty, tread_row(avg, qty), price,
             repairs=R.choice(['нет'] * 5 + ['1 латка']), added=added if added is not None else R.randint(4, 90), sold=sold)


plan = [((195, 65, 15), 9, 6), ((205, 60, 16), 6, 4), ((215, 60, 16), 5, 3), ((215, 55, 17), 6, 5),
        ((225, 45, 18), 4, 4), ((215, 65, 16), 5, 2), ((205, 55, 16), 0, 8)]
for size, nw, ns in plan:
    for _ in range(nw):
        gen_winter(size, R.choice(list(WINTER)))
    for _ in range(ns):
        gen_summer(size)
for _ in range(2):
    gen_summer((205, 55, 16), season='всесезон')
gen_summer((215, 65, 16), season='всесезон')
gen_winter((195, 65, 15), 'Yokohama', 'продано', added=25, sold=d(6))
gen_winter((215, 55, 17), 'Pirelli', 'бронь', added=5)

# --- диски ---
wseq = iter(range(2042, 2200))


def add_wheel(sku, status, kind, origin, make, model, dia, width, pcd, et, co, qty, color, state, defects, repair, price,
              added=10, sold='', note=''):
    rows_w.append({'артикул': sku, 'статус': status, 'тип': kind, 'происхождение': origin, 'марка': make,
                   'модель_диска': model, 'диаметр': dia, 'ширина': str(width).replace('.', ','), 'pcd': pcd,
                   'et': et, 'цо': str(co).replace('.', ','), 'кол_во': qty, 'цвет': color, 'состояние': state,
                   'дефекты': defects, 'ремонт': repair, 'цена_комплект': price, 'дата_поступления': d(added),
                   'дата_продажи': sold, 'примечание': note})


add_wheel('Д-2041', 'в наличии', 'литые', 'оригинал', 'Hyundai/Kia', 'Sportage 4', 17, 7, '5x114,3', 47, 67.1, 4, 'серебристый',
          'хорошее', 'мелкие сколы на одном диске', 'нет', 24000, added=1, note='Сняты с Kia Sportage 2019, без правки')
add_wheel('Д-2040', 'в наличии', 'литые', 'реплика', 'Hyundai/Kia', 'реплика Tucson', 17, 7, '5x114,3', 45, 67.1, 4, 'тёмный графит',
          'отличное', '', 'нет', 16000, added=2)
add_wheel('Д-2039', 'продано', 'штампованные', '', 'Hyundai/Kia', '', 17, 6.5, '5x114,3', 46, 67.1, 4, 'чёрный',
          'хорошее', 'следы коррозии по ободу', 'нет', 7200, added=12, sold=d(4))

COLORS = ['серебристый', 'тёмный графит', 'чёрный матовый', 'чёрный с проточкой', 'серебристый']
WHEEL_PLAN = [  # диаметр, ширина, pcd, et, цо, марка для оригинала, кол-во позиций
    (17, 7, '5x114,3', 47, 67.1, 'Hyundai/Kia', 6),
    (17, 6.5, '5x114,3', 50, 67.1, 'Hyundai/Kia', 1),
    (17, 7, '5x114,3', 45, 60.1, 'Toyota', 2),
    (17, 7, '5x114,3', 40, 66.1, 'Nissan', 1),
    (17, 7.5, '5x112', 49, 57.1, 'Volkswagen', 3),
    (16, 6.5, '5x114,3', 46, 67.1, 'Hyundai/Kia', 4),
    (16, 6.5, '5x112', 46, 57.1, 'Skoda', 4),
    (16, 6, '4x100', 50, 60.1, 'Lada', 3),
    (15, 6, '4x100', 46, 54.1, 'Hyundai/Kia', 5),
    (18, 7.5, '5x114,3', 45, 60.1, 'Toyota', 3),
    (18, 8, '5x112', 44, 57.1, 'Volkswagen', 2),
]
for dia, width, pcd, et, co, make, n in WHEEL_PLAN:
    for _ in range(n):
        kind = R.choice(['литые', 'литые', 'литые', 'штампованные'])
        if dia >= 18:
            kind = 'литые'
        origin = '' if kind == 'штампованные' else R.choice(['оригинал', 'оригинал', 'реплика'])
        et_v = et + R.choice([0, 0, -1, -2]) if dia == 17 and pcd == '5x114,3' and co == 67.1 else et
        state = R.choice(['отличное', 'хорошее', 'хорошее', 'среднее'])
        defects = {'отличное': '', 'хорошее': R.choice(['мелкие сколы лака', 'лёгкая бордюрка на одном диске', 'потёртости']),
                   'среднее': R.choice(['бордюрка на двух дисках', 'коррозия по ободу', 'сколы по спицам'])}[state]
        repair = R.choice(['нет'] * 5 + ['правка одного диска'])
        qty = R.choice([4, 4, 4, 4, 2])
        if kind == 'штампованные':
            base = 400 * (dia - 12)
        else:
            base = {15: 2600, 16: 3200, 17: 4200, 18: 5600}[dia] * (1.4 if origin == 'оригинал' else 1.0)
        base *= {'отличное': 1.1, 'хорошее': 1.0, 'среднее': 0.8}[state]
        price = int(round(base * qty / 200) * 200)
        model = f'{make.split("/")[0]} {R.choice(["", "", "Style", "Sport"])}'.strip() if origin == 'оригинал' else ''
        add_wheel(f'Д-{next(wseq)}', 'в наличии', kind, origin, make, model, dia, width, pcd, et_v, co, qty,
                  'чёрный' if kind == 'штампованные' else R.choice(COLORS), state, defects, repair, price, added=R.randint(3, 70))
add_wheel(f'Д-{next(wseq)}', 'продано', 'литые', 'оригинал', 'Toyota', 'Toyota', 17, 7, '5x114,3', 45, 60.1, 4, 'серебристый',
          'хорошее', 'потёртости', 'нет', 21000, added=110, sold=d(80))


def write(path, cols, rows):
    if path.exists() and '--force' not in sys.argv:
        print('skip (exists):', path.relative_to(ROOT))
        return
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, cols, delimiter=';')
        w.writeheader()
        w.writerows(rows)
    print('wrote', path.relative_to(ROOT), len(rows), 'rows')


write(ROOT / 'data' / 'tires.csv', TIRE_COLS, rows_t)
write(ROOT / 'data' / 'wheels.csv', WHEEL_COLS, rows_w)
