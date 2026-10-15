// Прогон сценариев в настоящем Chrome: фильтры, переходы на посадочные, бронь, избранное, поиск, цели Метрики.
// Сначала: python build.py --serve --port 8091, потом: node tools/test_site.js
const puppeteer = require('puppeteer-core');
const HOST = process.env.HOST || 'http://localhost:8091/protektor-demo/';
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
let fails = 0;
const ok = (cond, msg) => { console.log((cond ? '  ok   ' : '  FAIL ') + msg); if (!cond) fails++; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' });
  const page = await browser.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  await page.setViewport({ width: 1440, height: 900 });
  const go = async (u) => { await page.goto(HOST + u, { waitUntil: 'networkidle0' }); await wait(200); };
  const cards = () => page.$$eval('[data-grid] .card', (a) => a.length);
  const count = () => page.$eval('[data-flt-apply] [data-count]', (e) => +e.textContent);

  console.log('Каталог шин 205/55 R16 зима');
  await go('shiny/zimnie/205-55-r16/');
  ok(await count() === 38, 'в наличии 38 комплектов, на кнопке «Показать 38»');
  ok(await cards() === 12, 'на первой странице 12 карточек');
  const brands = await page.$$eval('.flt__brands .ck', (a) => a.map((l) => l.textContent.trim()));
  ok(brands.join('|').startsWith('Nokian Tyres8|Hankook7|Michelin6|Continental5|Yokohama5|Bridgestone4|Pirelli3'), 'счётчики брендов как на макете: ' + brands.join(', '));
  await page.click('input[name=brand][value="Nokian Tyres"] + .ck__box');
  await wait(150);
  ok(await count() === 8, 'фильтр Nokian Tyres: 8');
  ok(page.url().includes('brand=Nokian'), 'фильтр попал в адрес: ' + page.url().replace(HOST, ''));
  await page.$eval('input[name=tread]', (r) => { r.value = '8'; r.dispatchEvent(new Event('input', { bubbles: true })); r.dispatchEvent(new Event('change', { bubbles: true })); });
  await wait(150);
  const treads = await page.$$eval('[data-grid] .card', (a) => a.map((c) => parseFloat(c.querySelector('.card__row').textContent.replace(/[^\d,]/g, '').replace(',', '.'))));
  ok(treads.length > 0 && treads.every((t) => t >= 8), 'протектор от 8 мм: ' + treads.join(', '));
  await page.click('.flt__foot [data-flt-reset]'); await wait(150);
  ok(await count() === 38, 'сброс фильтров: снова 38');
  await page.click('input[name=stock] + .tgl__s'); await wait(150);
  ok(await page.$$eval('[data-grid] .card.is-sold', (a) => a.length) >= 1, 'без «Только в наличии» видны проданные с плашкой');
  await page.click('input[name=stock] + .tgl__s'); await wait(150);
  await page.click('[data-more]'); await wait(150);
  ok(await cards() === 24, '«Показать ещё» добавляет вторую страницу (24 карточки)');
  await page.click('input[name=brand][value="Michelin"] + .ck__box'); await wait(100);
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('input[name=season][value=leto] + .ck__box')]);
  ok(page.url().includes('shiny/205-55-r16/?') && page.url().includes('season=zima%2Cleto') && page.url().includes('brand=Michelin'),
    'зима + лето ведёт на общую посадочную 205/55 R16 с сохранением бренда: ' + page.url().replace(HOST, ''));
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('input[name=season][value=zima] + .ck__box')]);
  ok(page.url().includes('shiny/letnie/205-55-r16/') && page.url().includes('brand=Michelin'), 'оставили только лето - посадочная летних 205/55 R16: ' + page.url().replace(HOST, ''));
  await go('shiny/zimnie/205-55-r16/');
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.select('select[name=d]', '15')]);
  ok(page.url().includes('shiny/zimnie/?w=205&h=55&d=15'), 'размера 205/55 R15 нет - остаёмся в зимних с параметрами: ' + page.url().replace(HOST, ''));
  ok(!(await page.$eval('[data-empty]', (e) => e.hidden)), 'пустая выдача показывает «Подобрать под заказ»');

  console.log('Диски R17 5x114,3');
  await go('diski/r17-5x114-3/?etmin=45&etmax=47&co=67.1');
  const chips = await page.$$eval('.active__c', (a) => a.map((c) => c.textContent.trim()));
  ok(chips.join('|') === 'R17|PCD 5x114,3|ЦО 67,1|ET 45-47', 'активные фильтры как на макете: ' + chips.join(', '));
  ok(await count() === 8, 'найдено 8 в наличии (плюс 1 проданный в блоке «Недавно продано»)');
  ok(await page.$$eval('[data-sold-recent] .card', (a) => a.length) >= 1, 'блок «Недавно продано» есть');

  console.log('Главная, подбор по размеру');
  await go('');
  ok((await page.$eval('[data-pick-form=tire] button', (b) => b.textContent)).includes('38'), 'кнопка «Показать 38 комплектов»');
  await page.select('[data-pick-form=tire] select[name=w]', '195');
  await page.select('[data-pick-form=tire] select[name=h]', '65');
  await page.select('[data-pick-form=tire] select[name=d]', '15');
  await wait(150);
  const btn = await page.$eval('[data-pick-form=tire] button', (b) => b.textContent.replace(/\s+/g, ' '));
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('[data-pick-form=tire] button')]);
  ok(page.url().endsWith('shiny/zimnie/195-65-r15/'), `«${btn.trim()}» ведёт на /shiny/zimnie/195-65-r15/`);
  await go('');
  await page.click('[data-tab=wheel]');
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('[data-pick-form=wheel] button')]);
  ok(page.url().endsWith('diski/r17-5x114-3/'), 'подбор дисков R17 5x114,3 ведёт на посадочную');

  console.log('Бронь, заявка, цели Метрики');
  await go('shiny/nokian-hakkapeliitta-10-205-55-r16-sh-1048/');
  await page.click('.pp__btns [data-bron]');
  await wait(200);
  ok(await page.$eval('#dlg-bron', (d) => d.open), 'окно брони открылось');
  ok((await page.$eval('[data-bron-title]', (e) => e.textContent)).includes('Hakkapeliitta 10'), 'в окне название комплекта');
  await page.click('#dlg-bron button[type=submit]'); await wait(100);
  ok(await page.$eval('#dlg-bron [data-phone]', (e) => e.classList.contains('is-err')), 'без телефона не отправляется');
  await page.type('#dlg-bron [data-phone]', '9221234567');
  ok((await page.$eval('#dlg-bron [data-phone]', (e) => e.value)) === '+7 (922) 123-45-67', 'маска телефона');
  await page.click('#dlg-bron .consent input');
  await page.click('#dlg-bron button[type=submit]'); await wait(150);
  ok((await page.$eval('[data-bron-ok]', (e) => e.textContent)).includes('Ш-1048'), 'бронь принята: ' + (await page.$eval('[data-bron-ok]', (e) => e.textContent)).slice(0, 60));
  await page.click('#dlg-bron .form__ok [data-close]');
  await page.click('.pp__btns [data-goal=whatsapp]'); await wait(100);
  await page.click('.header__lead'); await wait(100);
  await page.type('#dlg-lead [data-phone]', '89001112233');
  await page.click('#dlg-lead .consent input');
  await page.click('#dlg-lead button[type=submit]'); await wait(100);
  const goals = await page.evaluate(() => (window.pkGoalLog || []).map((g) => g.goal));
  ok(['form_bron', 'click_whatsapp', 'form_lead'].every((g) => goals.includes(g)), 'цели reachGoal: ' + goals.join(', '));
  const ld = await page.$eval('script[type="application/ld+json"]', (s) => JSON.parse(s.textContent));
  ok(ld['@graph'][0].offers.availability.endsWith('InStock'), 'schema: InStock');

  console.log('Проданный товар');
  await go('shiny/pirelli-ice-zero-2-205-55-r16-sh-1043/');
  const ld2 = await page.$eval('script[type="application/ld+json"]', (s) => JSON.parse(s.textContent));
  ok(ld2['@graph'][0].offers.availability.endsWith('SoldOut'), 'schema: SoldOut');
  ok(await page.$('.sold-band') !== null && await page.$$eval('#similar .mini', (a) => a.length) === 3, 'плашка «Продано» и 3 похожих');
  ok((await page.$eval('meta[name=robots]', (m) => m.content)) === 'index,follow', 'проданный остаётся в индексе');
  const r = await page.goto(HOST + 'shiny/continental-vikingcontact-7-205-55-r16-sh-1135/', { waitUntil: 'networkidle0' });
  ok(page.url().endsWith('shiny/zimnie/205-55-r16/'), 'давно проданный (75 дней) уводит на размер');

  console.log('Избранное и поиск');
  await go('shiny/zimnie/205-55-r16/');
  await page.click('[data-grid] .card [data-fav]'); await wait(100);
  ok((await page.$eval('.fav-count', (e) => e.textContent)) === '1', 'счётчик избранного в шапке');
  await go('izbrannoe/');
  ok(await page.$$eval('[data-fav-grid] .card', (a) => a.length) === 1, 'страница избранного показывает комплект');
  await page.type('#q', '205/55 r16');
  await wait(600);
  ok(await page.$$eval('.search__drop a', (a) => a.length) > 0, 'подсказки поиска по размеру');
  await go('poisk/?q=Ш-1048');
  ok(await page.$$eval('[data-search-grid] .card', (a) => a.length) === 1, 'поиск по артикулу Ш-1048');

  console.log('Мобильный: шторка фильтров');
  await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await go('shiny/zimnie/205-55-r16/');
  ok(await page.$eval('.mbar', (e) => getComputedStyle(e).position === 'fixed'), 'нижняя панель «Позвонить / WhatsApp / Заявка» закреплена');
  await page.click('[data-flt-open]'); await wait(350);
  ok(await page.$eval('#flt', (e) => e.classList.contains('is-open')), 'шторка открылась');
  await page.click('input[name=type][value=ship]'); await wait(100);
  const n = await count();
  await page.click('[data-flt-apply]'); await wait(300);
  ok(!(await page.$eval('#flt', (e) => e.classList.contains('is-open'))) && (await page.$eval('[data-fn]', (e) => e.textContent)) === '1', `«Показать ${n}» закрывает шторку, на кнопке «Фильтры» 1`);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  ok(!overflow, 'нет горизонтальной прокрутки на 390 px');

  ok(errs.length === 0, 'ошибок JS нет' + (errs.length ? ': ' + errs.join('; ') : ''));
  await browser.close();
  console.log(fails ? `\nПровалено: ${fails}` : '\nВсе проверки прошли');
  process.exit(fails ? 1 : 0);
})();
