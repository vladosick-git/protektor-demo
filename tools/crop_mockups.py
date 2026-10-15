# Вырезает фото товаров и аватарки из макетов ChatGPT (ref/) как временные заглушки,
# пока нет чистых фото по ТЗ_фото_для_GPT.md. Запуск: python tools/crop_mockups.py
from pathlib import Path
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / 'ref'
cat = Image.open(REF / '01-protektor-catalog.png').convert('RGB')
mob = Image.open(REF / '02-protektor-mobile-corrected.png').convert('RGB')
prd = Image.open(REF / '03-protektor-product.png').convert('RGB')


def save(im, box, dst, scale=2, ratio=None):
    c = im.crop(box)
    if ratio:  # подрезать по центру до нужных пропорций
        w, h = c.size
        if w / h > ratio:
            nw = int(h * ratio); c = c.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / ratio); c = c.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2))
    dst.parent.mkdir(parents=True, exist_ok=True)
    c.save(dst, quality=92)
    print(dst.relative_to(ROOT), c.size)


P = ROOT / 'photos'
# Nokian Ш-1048: большое фото и 5 миниатюр со страницы товара
save(prd, (88, 218, 789, 605), P / 'Ш-1048' / '01 Комплект.jpg', 2)
caps = ['Колесо 1', 'Колесо 2', 'Колесо 3', 'Колесо 4', 'DOT 1422']
xs = [(206, 316), (324, 433), (442, 552), (561, 670), (679, 790)]
for i, ((a, b), cap) in enumerate(zip(xs, caps), start=2):
    save(prd, (a + 1, 619, b - 1, 719), P / 'Ш-1048' / f'0{i} {cap}.jpg', 6)
# каталог: Michelin, Continental, Hankook, Bridgestone, Pirelli
# справа в плитках нарисовано сердечко - отрезаем полосу 46 px
tiles = {'Ш-1047': (491, 290, 690, 446), 'Ш-1046': (748, 290, 949, 446), 'Ш-1045': (241, 620, 434, 783),
         'Ш-1044': (491, 620, 690, 783)}
for sku, box in tiles.items():
    save(cat, box, P / sku / '01 Комплект.jpg', 4)
# Pirelli (продано): в плитке каталога плашка нарисована прямо на фото, а стопка с мобильного макета подписана мелом «195» -
# не берём ни то ни другое, ждём фото по ТЗ_фото_для_GPT.md
# похожие на странице товара - вторые ракурсы
save(prd, (88, 877, 246, 968), P / 'Ш-1047' / '02 Комплект сбоку.jpg', 6)
save(prd, (562, 877, 720, 968), P / 'Ш-1045' / '02 Комплект сбоку.jpg', 6)
save(prd, (1044, 877, 1208, 968), P / 'Ш-1046' / '02 Комплект сбоку.jpg', 6)
# диски с мобильного макета
for sku, box in {'Д-2041': (1058, 301, 1226, 477), 'Д-2040': (1058, 500, 1226, 672), 'Д-2039': (1058, 695, 1226, 869)}.items():
    save(mob, box, P / sku / '01 Комплект.jpg', 6, ratio=3 / 2)
# аватарки отзывов
IMG = ROOT / 'src' / 'img'
for name, box in {'andrey': (43, 1246, 89, 1293), 'marina': (360, 1246, 406, 1293), 'oleg': (686, 1246, 732, 1293)}.items():
    c = cat.crop(box).resize((112, 112), Image.LANCZOS)
    c.save(IMG / f'ava-{name}.webp', quality=88)
