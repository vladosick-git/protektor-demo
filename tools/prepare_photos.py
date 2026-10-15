# Раскладывает фото из incoming_gpt/ (имена из ТЗ_фото_для_GPT.md) по папкам товаров в photos/.
# Запуск: python tools/prepare_photos.py, потом python build.py
import re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'incoming_gpt'
DST = ROOT / 'photos'

CAPS = {
    '1048': {'01': 'Комплект', '02': 'Колесо 1', '03': 'Колесо 2', '04': 'Колесо 3', '05': 'Колесо 4', '06': 'DOT 1422'},
    '1047': {'01': 'Комплект', '02': 'Глубиномер', '03': 'DOT 3821'},
    '1046': {'01': 'Комплект', '02': 'Шипы', '03': 'Глубиномер'},
    '1045': {'01': 'Комплект', '02': 'Глубиномер'},
    '1044': {'01': 'Пара', '02': 'Глубиномер'},
    '1043': {'01': 'Комплект'},
    '2041': {'01': 'Комплект', '02': 'Скол на ободе', '03': 'Маркировка'},
    '2040': {'01': 'Комплект', '02': 'Спицы крупно'},
    '2039': {'01': 'Комплект'},
}
POOL = {'zima': 'зима', 'leto': 'лето', 'litye': 'литые', 'shtamp': 'штампованные'}

done = 0
for f in sorted(SRC.glob('*')):
    if f.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
        continue
    stem = f.stem.lower()
    m = re.match(r'(\d{4})-(\d{2})', stem)
    if m and m.group(1) in CAPS:
        num, idx = m.groups()
        sku = ('Ш-' if num.startswith('1') else 'Д-') + num
        cap = CAPS[num].get(idx, 'Фото')
        folder = DST / sku
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob(f'{idx} *'):  # заменяем вырезку из макета
            old.unlink()
        shutil.copy2(f, folder / f'{idx} {cap}{f.suffix.lower()}')
        done += 1
        continue
    m = re.match(r'pool-(zima|leto|litye|shtamp)-(\d+)', stem)
    if m:
        folder = DST / '_pool' / POOL[m.group(1)]
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, folder / f'{m.group(2)}{f.suffix.lower()}')
        done += 1
        continue
    if stem == 'og':
        from PIL import Image
        Image.open(f).convert('RGB').resize((1200, 800)).crop((0, 85, 1200, 715)).save(ROOT / 'src' / 'img' / 'og-photo.jpg', quality=85)
        done += 1
        continue
    print('не понял, куда положить:', f.name)
print('разложено файлов:', done)
