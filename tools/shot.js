// Скриншоты сайта. Сначала запустите сервер: python build.py --serve --port 8091
//   node tools/shot.js check   - рабочие скрины для сверки с макетами (tmp/)
//   node tools/shot.js kwork   - картинки 1920x1280 для портфолио Кворка (screens/)
//   node tools/shot.js og      - картинка для соцсетей src/img/og.png и logo.png
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const ROOT = path.resolve(__dirname, '..');
const HOST = process.env.HOST || 'http://localhost:8091/protektor-demo/';
const mode = process.argv[2] || 'check';
const only = process.argv[3];

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--hide-scrollbars'] });
  const page = await browser.newPage();
  const open = async (u, w, h, dsf = 1, mobile = false) => {
    await page.setViewport({ width: w, height: h, deviceScaleFactor: dsf, isMobile: mobile, hasTouch: mobile });
    await page.goto(u.startsWith('http') || u.startsWith('file') ? u : HOST + u, { waitUntil: 'networkidle0', timeout: 60000 });
    await page.evaluate(() => document.fonts.ready);
    // ленивые картинки за экраном сами не грузятся - для полностраничных скринов грузим всё сразу
    await new Promise((r) => setTimeout(r, 500));
    for (const f of page.frames()) {
      await f.evaluate(() => document.fonts.ready).catch(() => {});
      await f.evaluate(() => document.querySelectorAll('img[loading=lazy]').forEach((i) => (i.loading = 'eager'))).catch(() => {});
      await f.evaluate(() => Promise.race([new Promise((r) => setTimeout(r, 8000)),
        Promise.all([...document.images].map((i) => i.complete || new Promise((r) => (i.onload = i.onerror = r))))])).catch(() => {});
    }
    await new Promise((r) => setTimeout(r, 300));
  };
  const save = async (file, opts = {}) => {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await page.screenshot({ path: file, ...opts });
    console.log('saved', path.relative(ROOT, file));
  };

  if (mode === 'check') {
    const out = path.join(ROOT, 'tmp');
    const desk = [['d_home', ''], ['d_cat', 'shiny/zimnie/205-55-r16/?stock=0'], ['d_prod', 'shiny/nokian-hakkapeliitta-10-205-55-r16-sh-1048/'],
      ['d_sold', 'shiny/pirelli-ice-zero-2-205-55-r16-sh-1043/'], ['d_disk', 'diski/r17-5x114-3/'], ['d_wprod', 'diski/litye-original-hyundai-kia-r17-5x114-3-et47-d-2041/']];
    for (const [n, u] of desk) {
      if (only && !n.includes(only)) continue;
      await open(u, 1440, 900); await save(path.join(out, n + '.png'), { fullPage: true });
    }
    const mob = [['m_home', ''], ['m_cat', 'shiny/zimnie/205-55-r16/'], ['m_disk', 'diski/r17-5x114-3/?etmin=45&etmax=47&co=67.1'], ['m_prod', 'shiny/nokian-hakkapeliitta-10-205-55-r16-sh-1048/']];
    for (const [n, u] of mob) {
      if (only && !n.includes(only)) continue;
      await open(u, 390, 844, 2, true); await save(path.join(out, n + '.png'), { fullPage: true });
    }
    if (!only || only === 'm_flt') {
      await open('shiny/zimnie/205-55-r16/', 390, 844, 2, true);
      await page.click('[data-flt-open]'); await new Promise((r) => setTimeout(r, 400));
      await save(path.join(out, 'm_flt.png'));
    }
  }
  if (mode === 'kwork') {
    // холст 1536x1024 css @1.25 = 1920x1280
    const out = path.join(ROOT, 'screens');
    const names = { catalog: '01 - Каталог шин с фильтрами', mobile: '02 - Мобильная версия', product: '03 - Карточка комплекта', sold: '04 - Проданные и SEO', csv: '05 - Обновление из таблицы' };
    for (const [set, name] of Object.entries(names)) {
      if (only && set !== only) continue;
      await open(`showcase.html?set=${set}`, 1536, 1024, 1.25);
      await save(path.join(out, name + '.png'), { clip: { x: 0, y: 0, width: 1536, height: 1024 } });
    }
  }
  if (mode === 'og') {
    await open('showcase.html?set=og', 1200, 630, 1);
    await save(path.join(ROOT, 'src', 'img', 'og.png'), { clip: { x: 0, y: 0, width: 1200, height: 630 } });
    await page.setViewport({ width: 512, height: 512 });
    await page.goto(HOST + 'assets/img/favicon.svg', { waitUntil: 'load' });
    await page.evaluate(() => { const s = document.querySelector('svg'); s.setAttribute('width', 512); s.setAttribute('height', 512); });
    await save(path.join(ROOT, 'src', 'img', 'logo.png'), { clip: { x: 0, y: 0, width: 512, height: 512 }, omitBackground: true });
  }
  await browser.close();
})();
