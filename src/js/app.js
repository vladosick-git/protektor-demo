/* Протектор - вся логика страницы: фильтры каталога, формы, бронь, избранное, поиск, галерея.
   Без зависимостей. Данные каталога лежат в assets/data/tires.json и wheels.json (их пишет build.py). */
(function () {
  'use strict';
  var PK = window.PK || { base: '/' };
  var BASE = PK.base;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var goal = function (n, p) { if (window.pkGoal) window.pkGoal(n, p); };
  var SEASON_SLUG = { zima: 'zimnie', leto: 'letnie', vsesezon: 'vsesezonnye' };
  var SEASON_NAME = { zima: 'Зима', leto: 'Лето', vsesezon: 'Всесезонные' };

  function rub(n) { return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' ₽'; }
  function plural(n, a, b, c) { n = Math.abs(n) % 100; var m = n % 10; if (n > 10 && n < 20) return c; if (m > 1 && m < 5) return b; if (m === 1) return a; return c; }
  function sets(n) { return plural(n, 'комплект', 'комплекта', 'комплектов'); }
  function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
  function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k)); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }

  var cache = {};
  function data(kind) {
    if (!cache[kind]) cache[kind] = fetch(BASE + 'assets/data/' + kind + '.json').then(function (r) { return r.json(); });
    return cache[kind];
  }

  /* ---------- тост ---------- */
  var toastT;
  function toast(msg) {
    var t = $('.toast'); if (!t) return;
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(function () { t.hidden = true; }, 3200);
  }

  /* ---------- звонок, WhatsApp, Telegram: цель Метрики; в демо ничего не открываем ---------- */
  document.addEventListener('click', function (e) {
    var a = e.target.closest('[data-goal]');
    if (!a) return;
    var g = a.getAttribute('data-goal');
    goal(g, { page: location.pathname });
    if (PK.demo) {
      e.preventDefault();
      var what = { call: 'звонок на ' + PK.phone, whatsapp: 'чат в WhatsApp', telegram: 'чат в Telegram' }[g] || g;
      toast('Демо: здесь откроется ' + what + '. Цель Метрики отправлена.');
    }
  });

  /* ---------- модальные окна и формы ---------- */
  function openDlg(id) {
    var d = document.getElementById(id); if (!d) return;
    var f = $('form', d); resetForm(f);
    if (d.showModal) d.showModal(); else d.setAttribute('open', '');
    var first = $('input:not([type=hidden])', d); if (first && window.innerWidth > 1023) first.focus();
  }
  function resetForm(f) {
    if (!f) return;
    var b = $('.form__body', f), ok = $('.form__ok', f);
    if (b) b.hidden = false; if (ok) ok.hidden = true;
  }
  document.addEventListener('click', function (e) {
    var o = e.target.closest('[data-open]');
    if (o) { e.preventDefault(); openDlg('dlg-' + o.getAttribute('data-open')); return; }
    var b = e.target.closest('[data-bron]');
    if (b) {
      e.preventDefault();
      var d = $('#dlg-bron');
      $('[data-bron-title]', d).textContent = b.getAttribute('data-title');
      $('[data-bron-price]', d).textContent = b.getAttribute('data-price');
      $('input[name=sku]', d).value = b.getAttribute('data-bron');
      openDlg('dlg-bron');
      return;
    }
    var c = e.target.closest('[data-close]');
    if (c && c.closest('dialog')) { c.closest('dialog').close(); return; }
    if (e.target.tagName === 'DIALOG') e.target.close();
  });

  function digits(v) { return (v || '').replace(/\D/g, ''); }
  function maskPhone(inp) {
    var d = digits(inp.value);
    if (!d) { inp.value = ''; return; }
    if (d[0] === '8') d = '7' + d.slice(1);
    if (d[0] !== '7') d = '7' + d;
    d = d.slice(0, 11);
    var r = '+7';
    if (d.length > 1) r += ' (' + d.slice(1, 4);
    if (d.length >= 4) r += ')';
    if (d.length > 4) r += ' ' + d.slice(4, 7);
    if (d.length > 7) r += '-' + d.slice(7, 9);
    if (d.length > 9) r += '-' + d.slice(9, 11);
    inp.value = r;
  }
  document.addEventListener('input', function (e) {
    if (e.target.matches('[data-phone]')) { maskPhone(e.target); e.target.classList.remove('is-err'); }
  });
  document.addEventListener('change', function (e) {
    if (e.target.matches('.buy__drop input')) {
      var l = e.target.closest('.buy__drop'), n = e.target.files.length;
      l.classList.toggle('is-on', n > 0);
      $('b', l).textContent = n ? 'Выбрано фото: ' + n : 'Загрузить фото';
    }
    if (e.target.matches('.consent input')) e.target.closest('.consent').classList.remove('is-err');
  });
  document.addEventListener('submit', function (e) {
    var f = e.target.closest('[data-form]');
    if (!f) return;
    e.preventDefault();
    var ph = $('[data-phone]', f), ok = true;
    if (ph && digits(ph.value).length !== 11) { ph.classList.add('is-err'); ok = false; }
    var agree = $('input[name=agree]', f);
    if (agree && !agree.checked) { agree.closest('.consent').classList.add('is-err'); ok = false; }
    if (!ok) { toast('Проверьте телефон' + (agree && !agree.checked ? ' и согласие на обработку данных' : '')); return; }
    var kind = f.getAttribute('data-form');
    var params = { page: location.pathname };
    if (kind === 'bron') {
      params.sku = $('input[name=sku]', f).value;
      var until = new Date(PK.today); until.setDate(until.getDate() + (PK.reserveDays || 2));
      $('[data-bron-ok]', f).textContent = 'Комплект ' + params.sku + ' ждёт вас до ' + until.toLocaleDateString('ru-RU') +
        '. Менеджер позвонит, чтобы подтвердить время. Это демо - заявка никуда не ушла.';
    }
    goal(kind, params);
    $('.form__body', f).hidden = true;
    $('.form__ok', f).hidden = false;
    f.reset && f.reset();
    $$('.buy__drop', f).forEach(function (l) { l.classList.remove('is-on'); $('b', l).textContent = 'Загрузить фото'; });
  });

  /* ---------- меню ---------- */
  var burger = $('.burger');
  if (burger) burger.addEventListener('click', function () {
    var m = $('#mmenu'), open = m.hidden;
    m.hidden = !open; burger.setAttribute('aria-expanded', open);
  });

  /* ---------- избранное ---------- */
  function favs() { return store('pk-fav') || []; }
  function syncFav() {
    var f = favs();
    $$('[data-fav]').forEach(function (b) { b.setAttribute('aria-pressed', f.indexOf(b.getAttribute('data-fav')) >= 0); });
    var c = $('.fav-count'); if (c) { c.hidden = !f.length; c.textContent = f.length; }
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fav]'); if (!b) return;
    e.preventDefault();
    var f = favs(), s = b.getAttribute('data-fav'), i = f.indexOf(s);
    if (i >= 0) f.splice(i, 1); else f.push(s);
    store('pk-fav', f); syncFav();
    toast(i >= 0 ? 'Убрали из избранного' : 'Добавили в избранное');
  });
  syncFav();
  var favGrid = $('[data-fav-grid]');
  if (favGrid) Promise.all([data('tires'), data('wheels')]).then(function (r) {
    var f = favs(), items = r[0].items.concat(r[1].items).filter(function (i) { return f.indexOf(i.sku) >= 0; });
    favGrid.innerHTML = items.map(function (i) { return i.html; }).join('');
    $('[data-fav-empty]').hidden = items.length > 0;
    syncFav();
  });

  /* ---------- поиск ---------- */
  function searchItems(q, all) {
    q = q.trim().toLowerCase();
    if (q.length < 2) return [];
    var m = q.match(/(\d{3})\s*[\/\s-]?\s*(\d{2})\s*[\sr\/-]*(\d{2})/);
    var sku = q.replace(/\s/g, '').replace(/^sh/, 'ш').replace(/^d(?=-?\d)/, 'д');
    return all.filter(function (i) {
      if (m && i.w) return i.w == m[1] && i.h == m[2] && i.d == m[3];
      if (/^[шд]-?\d+$/.test(sku)) return i.sku.toLowerCase().replace('-', '') === sku.replace('-', '');
      var hay = (i.title + ' ' + i.sku + ' ' + (i.brand || '') + ' ' + (i.pcd || '')).toLowerCase();
      return q.split(/\s+/).every(function (w) { return hay.indexOf(w) >= 0; });
    }).sort(function (a, b) { return (a.st === 'sold') - (b.st === 'sold') || b.added - a.added; });
  }
  function allItems() { return Promise.all([data('tires'), data('wheels')]).then(function (r) { return r[0].items.concat(r[1].items); }); }
  $$('[data-search]').forEach(function (form) {
    var inp = $('input', form), drop = $('.search__drop', form), t;
    inp.addEventListener('input', function () {
      clearTimeout(t);
      t = setTimeout(function () {
        if (inp.value.trim().length < 2) { drop.hidden = true; return; }
        allItems().then(function (all) {
          var res = searchItems(inp.value, all).slice(0, 6);
          drop.innerHTML = res.length ? res.map(function (i) {
            return '<a href="' + i.url + '"><img src="' + i.img + '" alt=""><span><b>' + i.name + '</b><br>' + i.title.replace(i.name, '').trim() + ' · ' + rub(i.price) + (i.st === 'sold' ? ' · продано' : '') + '</span></a>';
          }).join('') : '<a href="' + BASE + 'poisk/?q=' + encodeURIComponent(inp.value) + '">Ничего не нашли - открыть поиск</a>';
          drop.hidden = false;
        });
      }, 150);
    });
    inp.addEventListener('blur', function () { setTimeout(function () { drop.hidden = true; }, 200); });
  });
  var sGrid = $('[data-search-grid]');
  if (sGrid) {
    var q = new URLSearchParams(location.search).get('q') || '';
    $$('input[name=q]').forEach(function (i) { i.value = q; });
    allItems().then(function (all) {
      var res = searchItems(q, all);
      $('[data-search-info]').textContent = q ? 'По запросу «' + q + '» найдено: ' + res.length : 'Введите размер, бренд или артикул.';
      sGrid.innerHTML = res.slice(0, 48).map(function (i) { return i.html; }).join('');
      syncFav();
    });
  }

  /* ---------- галерея товара ---------- */
  $$('[data-gal]').forEach(function (g) {
    var main = $('[data-gal-main]', g), th = $$('[data-th]', g);
    th.forEach(function (b, i) {
      b.addEventListener('click', function () { main.scrollTo({ left: main.clientWidth * i, behavior: 'smooth' }); });
    });
    var t;
    main.addEventListener('scroll', function () {
      clearTimeout(t);
      t = setTimeout(function () {
        var i = Math.round(main.scrollLeft / main.clientWidth);
        th.forEach(function (b, j) { b.classList.toggle('is-on', i === j); });
      }, 60);
    });
  });

  /* ---------- выбор посадочной страницы по фильтрам ---------- */
  function tireTarget(st, landings) {
    var size = st.w && st.h && st.d ? st.w + '-' + st.h + '-r' + st.d : '';
    var one = st.season.length === 1 ? SEASON_SLUG[st.season[0]] : '';
    var c = [];
    if (size && one) c.push({ p: 'shiny/' + one + '/' + size + '/', size: 1, season: 1 });
    if (size) c.push({ p: 'shiny/' + size + '/', size: 1 });
    if (one) c.push({ p: 'shiny/' + one + '/', season: 1 });
    c.push({ p: 'shiny/' });
    for (var i = 0; i < c.length; i++) if (landings.has(c[i].p)) return c[i];
    return c[c.length - 1];
  }
  function wheelTarget(st, landings) {
    var c = [];
    if (st.d && st.pcd) c.push({ p: 'diski/r' + st.d + '-' + slug(st.pcd) + '/', d: 1, pcd: 1 });
    if (st.d) c.push({ p: 'diski/r' + st.d + '/', d: 1 });
    c.push({ p: 'diski/' });
    for (var i = 0; i < c.length; i++) if (landings.has(c[i].p)) return c[i];
    return c[c.length - 1];
  }

  /* ---------- подбор на главной ---------- */
  var pick = $('[data-pick]');
  if (pick) {
    $$('[data-tab]', pick).forEach(function (t) {
      t.addEventListener('click', function () {
        $$('[data-tab]', pick).forEach(function (x) { x.classList.toggle('is-on', x === t); x.setAttribute('aria-selected', x === t); });
        $$('[data-pick-form]', pick).forEach(function (f) { f.hidden = f.getAttribute('data-pick-form') !== t.getAttribute('data-tab'); });
      });
    });
    $$('[data-pick-form]', pick).forEach(function (f) {
      var kind = f.getAttribute('data-pick-form');
      function st() {
        var v = function (n) { var e = f.elements[n]; return e ? e.value : ''; };
        if (kind === 'tire') return { w: v('w'), h: v('h'), d: v('d'), season: v('season') ? [v('season')] : [] };
        var et = v('et').split('-');
        return { d: v('d'), pcd: v('pcd'), etmin: et[0] || '', etmax: et[1] || '', co: v('co') };
      }
      function match(i, s) {
        if (i.st === 'sold') return false;
        if (kind === 'tire') return (!s.w || i.w == s.w) && (!s.h || i.h == s.h) && (!s.d || i.d == s.d) && (!s.season.length || i.season === s.season[0]);
        return (!s.d || i.d == s.d) && (!s.pcd || i.pcd === s.pcd) && (!s.etmin || i.et >= +s.etmin) && (!s.etmax || i.et <= +s.etmax) && (!s.co || i.co == s.co);
      }
      function upd() {
        data(kind === 'tire' ? 'tires' : 'wheels').then(function (d) {
          var s = st(), n = d.items.filter(function (i) { return match(i, s); }).length;
          $('[data-pick-count]', f).textContent = n;
          $('[data-pick-word]', f).textContent = sets(n);
        });
      }
      f.addEventListener('change', upd);
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        data(kind === 'tire' ? 'tires' : 'wheels').then(function (d) {
          var s = st(), L = new Set(d.landings), t = kind === 'tire' ? tireTarget(s, L) : wheelTarget(s, L), q = new URLSearchParams();
          if (kind === 'tire') {
            if (!t.size) ['w', 'h', 'd'].forEach(function (k) { if (s[k]) q.set(k, s[k]); });
            if (!t.season && s.season.length) q.set('season', s.season.join(','));
          } else {
            if (!t.d && s.d) q.set('d', s.d);
            if (!t.pcd && s.pcd) q.set('pcd', s.pcd);
            ['etmin', 'etmax', 'co'].forEach(function (k) { if (s[k]) q.set(k, s[k]); });
          }
          location.href = BASE + t.p + (q.toString() ? '?' + q : '');
        });
      });
    });
  }

  /* ---------- каталог с фильтрами ---------- */
  var root = $('[data-catalog]');
  if (root) initCatalog(root);

  function initCatalog(root) {
    var cfg = JSON.parse(root.getAttribute('data-catalog'));
    var tire = cfg.kind === 'tire';
    var form = $('[data-flt]', root), grid = $('[data-grid]', root), pager = $('[data-pager]', root), empty = $('[data-empty]', root);
    var activeBox = $('[data-active]', root), soldBox = $('[data-sold-recent]', root), sortSel = $('[data-sort]', root);
    var flt = $('#flt'), shade = $('.flt-shade', root), countText = $('[data-count-text]'), fn = $('[data-fn]', root);
    var origCount = countText ? countText.textContent : '';
    var preset = cfg.preset || {};
    var pageTo = 1, pageFrom = 1, items = [], landings = new Set();
    if (!tire) { var o = $('option[value=tread]', sortSel); if (o) o.remove(); }

    var MULTI = tire ? ['season', 'type', 'brand', 'qty'] : ['co', 'width', 'kind', 'origin', 'qty'];
    var SINGLE = tire ? ['w', 'h', 'd', 'tread', 'year', 'pmin', 'pmax'] : ['d', 'pcd', 'etmin', 'etmax', 'pmin', 'pmax'];

    function read() {
      var s = {};
      SINGLE.forEach(function (n) { var e = form.elements[n]; s[n] = e ? e.value : ''; });
      MULTI.forEach(function (n) { s[n] = $$('input[name=' + n + ']:checked', form).map(function (e) { return e.value; }); });
      s.stock = form.elements.stock.checked;
      if (s.tread === '0') s.tread = '';
      return s;
    }
    function write(s) {
      SINGLE.forEach(function (n) { var e = form.elements[n]; if (e) e.value = s[n] || (n === 'tread' ? '0' : ''); });
      MULTI.forEach(function (n) { $$('input[name=' + n + ']', form).forEach(function (e) { e.checked = (s[n] || []).indexOf(e.value) >= 0; }); });
      form.elements.stock.checked = s.stock !== false;
      syncRange();
    }
    function presetState() {
      var s = { stock: true };
      SINGLE.concat(MULTI).forEach(function (n) { s[n] = MULTI.indexOf(n) >= 0 ? [] : ''; });
      Object.keys(preset).forEach(function (k) { s[k] = Array.isArray(preset[k]) ? preset[k].slice() : String(preset[k]); });
      return s;
    }
    function fromQuery() {
      var s = presetState(), q = new URLSearchParams(location.search);
      SINGLE.forEach(function (n) { if (q.has(n)) s[n] = q.get(n); });
      MULTI.forEach(function (n) { if (q.has(n)) s[n] = q.get(n).split(',').filter(Boolean); });
      if (q.get('stock') === '0') s.stock = false;
      if (q.has('sort')) sortSel.value = q.get('sort');
      pageTo = pageFrom = Math.max(1, parseInt(q.get('page'), 10) || 1);
      return s;
    }

    function match(i, s, skip) {
      if (s.stock && i.st === 'sold') return false;
      if (tire) {
        if (s.w && i.w != s.w) return false;
        if (s.h && i.h != s.h) return false;
        if (s.d && i.d != s.d) return false;
        if (s.season.length && s.season.indexOf(i.season) < 0) return false;
        if (s.type.length && s.type.indexOf(i.type) < 0) return false;
        if (skip !== 'brand' && s.brand.length && s.brand.indexOf(i.brand) < 0) return false;
        if (s.tread && i.tread < +s.tread) return false;
        if (s.year && i.year < +s.year) return false;
      } else {
        if (s.d && i.d != s.d) return false;
        if (s.pcd && i.pcd !== s.pcd) return false;
        if (s.etmin && i.et < +s.etmin) return false;
        if (s.etmax && i.et > +s.etmax) return false;
        if (s.co.length && s.co.indexOf(String(i.co)) < 0) return false;
        if (s.width.length && s.width.indexOf(String(i.width)) < 0) return false;
        if (s.kind.length && s.kind.indexOf(i.kind) < 0) return false;
        if (s.origin.length && s.origin.indexOf(i.origin) < 0) return false;
      }
      if (s.qty.length && s.qty.indexOf(String(i.qty)) < 0) return false;
      if (s.pmin && i.price < +s.pmin) return false;
      if (s.pmax && i.price > +s.pmax) return false;
      return true;
    }
    var SORT = {
      'new': function (a, b) { return b.added - a.added || (a.sku < b.sku ? 1 : -1); },
      cheap: function (a, b) { return a.price - b.price; },
      exp: function (a, b) { return b.price - a.price; },
      tread: function (a, b) { return (b.tread || 0) - (a.tread || 0); }
    };

    /* что из фильтров уже «зашито» в адрес посадочной */
    function covered(t) {
      return tire ? { w: !!t.size, h: !!t.size, d: !!t.size, season: !!t.season } : { d: !!t.d, pcd: !!t.pcd };
    }
    function query(s, t) {
      var q = new URLSearchParams(), cov = covered(t);
      SINGLE.forEach(function (n) { if (s[n] && !cov[n]) q.set(n, s[n]); });
      MULTI.forEach(function (n) { if (s[n].length && !cov[n]) q.set(n, s[n].join(',')); });
      if (!s.stock) q.set('stock', '0');
      if (sortSel.value !== 'new') q.set('sort', sortSel.value);
      return q;
    }

    function chips(s) {
      var out = [];
      var add = function (label, clear) { out.push({ label: label, clear: clear }); };
      if (tire) {
        s.type.forEach(function (v) { add(v === 'ship' ? 'Шипы' : 'Липучка', function (x) { x.type = x.type.filter(function (y) { return y !== v; }); }); });
        s.brand.forEach(function (v) { add(v, function (x) { x.brand = x.brand.filter(function (y) { return y !== v; }); }); });
        if (s.tread) add('Протектор от ' + String(s.tread).replace('.', ',') + ' мм', function (x) { x.tread = ''; });
        if (s.year) add('Год от ' + s.year, function (x) { x.year = ''; });
        if (!cfg.preset.w && s.w && s.h && s.d) add(s.w + '/' + s.h + ' R' + s.d, function (x) { x.w = x.h = x.d = ''; });
        if (!cfg.preset.season && s.season.length) s.season.forEach(function (v) { add(SEASON_NAME[v], function (x) { x.season = x.season.filter(function (y) { return y !== v; }); }); });
      } else {
        if (s.d) add('R' + s.d, function (x) { x.d = ''; x.pcd = x.pcd; });
        if (s.pcd) add('PCD ' + s.pcd, function (x) { x.pcd = ''; });
        s.co.forEach(function (v) { add('ЦО ' + v.replace('.', ','), function (x) { x.co = x.co.filter(function (y) { return y !== v; }); }); });
        if (s.etmin || s.etmax) add('ET ' + (s.etmin || '…') + '-' + (s.etmax || '…'), function (x) { x.etmin = x.etmax = ''; });
        s.width.forEach(function (v) { add(v.replace('.', ',') + 'J', function (x) { x.width = x.width.filter(function (y) { return y !== v; }); }); });
        s.kind.concat(s.origin).forEach(function (v) { add(v[0].toUpperCase() + v.slice(1), function (x) { x.kind = x.kind.filter(function (y) { return y !== v; }); x.origin = x.origin.filter(function (y) { return y !== v; }); }); });
      }
      s.qty.forEach(function (v) { add(v + ' шт', function (x) { x.qty = x.qty.filter(function (y) { return y !== v; }); }); });
      if (s.pmin || s.pmax) add((s.pmin ? 'от ' + rub(s.pmin) : '') + (s.pmax ? ' до ' + rub(s.pmax) : ''), function (x) { x.pmin = x.pmax = ''; });
      return out;
    }

    var lastChips = [];
    function render(opts) {
      opts = opts || {};
      var s = read(), t = tire ? tireTarget(s, landings) : wheelTarget(s, landings);
      if (t.p !== cfg.path && opts.nav !== false) { location.href = BASE + t.p + (query(s, t).toString() ? '?' + query(s, t) : ''); return; }
      var list = items.filter(function (i) { return match(i, s); }).sort(SORT[sortSel.value] || SORT['new']);
      var per = cfg.per, pages = Math.max(1, Math.ceil(list.length / per));
      if (pageTo > pages) pageTo = pages;
      if (pageFrom > pageTo) pageFrom = pageTo;
      if (!opts.keep) grid.innerHTML = list.slice((pageFrom - 1) * per, pageTo * per).map(function (i) { return i.html; }).join('');
      empty.hidden = list.length > 0;
      var stockN = items.filter(function (i) { return match(i, s) && i.st !== 'sold'; }).length;
      $$('[data-count]', root).forEach(function (e) { e.textContent = list.length; });
      if (soldBox) soldBox.hidden = !s.stock;
      // счётчики брендов: сколько будет, если отметить бренд
      if (tire) $$('.ck__n', form).forEach(function (n) {
        var b = n.getAttribute('data-n'), c = items.filter(function (i) { return i.brand === b && match(i, s, 'brand'); }).length;
        n.textContent = c; n.closest('.ck').classList.toggle('is-zero', !c);
      });
      // активные фильтры
      lastChips = chips(s);
      activeBox.innerHTML = lastChips.map(function (c, i) {
        return '<button class="active__c" type="button" data-chip="' + i + '">' + c.label + '<svg class="i" aria-hidden="true"><use href="#i-close"/></svg></button>';
      }).join('') + (lastChips.length ? '<span class="active__n">найдено ' + list.length + '</span>' : '');
      if (fn) { fn.hidden = !lastChips.length; fn.textContent = lastChips.length; }
      if (countText) countText.textContent = lastChips.length || !s.stock ? 'Найдено ' + list.length + ' ' + sets(list.length) + (s.stock ? ' в наличии' : '') : origCount;
      // страницы
      if (pages <= 1) pager.innerHTML = '';
      else {
        var nums = [], show = function (p) { return p === 1 || p === pages || Math.abs(p - pageTo) <= 1 || (pageTo <= 2 && p <= 3); };
        for (var p = 1, gap = false; p <= pages; p++) {
          if (show(p)) { nums.push('<a class="pager__n' + (p >= pageFrom && p <= pageTo ? ' is-on' : '') + '" href="?page=' + p + '" data-page="' + p + '" rel="nofollow">' + p + '</a>'); gap = false; }
          else if (!gap) { nums.push('<span class="pager__gap">…</span>'); gap = true; }
        }
        if (pageTo < pages) nums.push('<a class="pager__n pager__next" href="?page=' + (pageTo + 1) + '" data-page="' + (pageTo + 1) + '" rel="nofollow" aria-label="Следующая страница"><svg class="i" aria-hidden="true"><use href="#i-chev-r"/></svg></a>');
        pager.innerHTML = '<div class="pager__nums">' + nums.join('') + '</div>' + (pageTo < pages ? '<button class="btn btn--line pager__more" type="button" data-more>Показать ещё</button>' : '');
      }
      var q = query(s, t);
      if (pageTo > 1) q.set('page', pageTo);
      history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q : ''));
      syncFav();
    }

    function syncRange() {
      var r = form.elements.tread; if (!r) return;
      var out = $('[data-tread-out]', form);
      out.textContent = 'от ' + String(r.value).replace('.', ',') + ' мм';
      r.style.setProperty('--p', (r.value / r.max * 100) + '%');
    }

    form.addEventListener('input', function (e) { if (e.target.name === 'tread') syncRange(); });
    form.addEventListener('change', function () { pageFrom = pageTo = 1; render(); });
    sortSel.addEventListener('change', function () { pageFrom = pageTo = 1; render(); });
    root.addEventListener('click', function (e) {
      var c = e.target.closest('[data-chip]');
      if (c) { var s = read(); lastChips[+c.getAttribute('data-chip')].clear(s); write(s); pageFrom = pageTo = 1; render(); return; }
      var pg = e.target.closest('[data-page]');
      if (pg) { e.preventDefault(); pageFrom = pageTo = +pg.getAttribute('data-page'); render(); grid.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
      if (e.target.closest('[data-more]')) { pageTo++; render(); return; }
      if (e.target.closest('[data-flt-reset]')) { write(presetState()); pageFrom = pageTo = 1; render(); return; }
      if (e.target.closest('[data-flt-open]')) { flt.classList.add('is-open'); shade.hidden = false; document.body.classList.add('no-scroll'); return; }
      if (e.target.closest('[data-flt-close]') || e.target.closest('[data-flt-apply]')) {
        var wasOpen = flt.classList.contains('is-open');
        flt.classList.remove('is-open'); shade.hidden = true; document.body.classList.remove('no-scroll');
        if (e.target.closest('[data-flt-apply]') && !wasOpen) grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && flt.classList.contains('is-open')) $('[data-flt-close]', root).click(); });

    // вид: плитка или список
    var view = store('pk-view') || 'grid';
    function setView(v) {
      grid.classList.toggle('is-list', v === 'list');
      $$('[data-view]', root).forEach(function (b) { var on = b.getAttribute('data-view') === v; b.classList.toggle('is-on', on); b.setAttribute('aria-pressed', on); });
    }
    $$('[data-view]', root).forEach(function (b) { b.addEventListener('click', function () { view = b.getAttribute('data-view'); store('pk-view', view); setView(view); }); });
    setView(view);

    // ссылка вида ...#filters сразу открывает фильтры (удобно слать клиенту в мессенджер)
    if (location.hash === '#filters' && window.innerWidth < 1024) { flt.classList.add('is-open'); shade.hidden = false; document.body.classList.add('no-scroll'); }

    var initial = fromQuery();
    write(initial);
    data(tire ? 'tires' : 'wheels').then(function (d) {
      items = d.items.filter(function (i) {
        // на посадочной показываем только её товары по «зашитым» параметрам; остальное - через фильтры
        return true;
      });
      landings = new Set(d.landings);
      render({ nav: false, keep: !location.search });
    });
  }
})();
