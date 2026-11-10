/* Кама.Работа — клиентская логика. Чистый JS, без сборки и зависимостей. */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var PAGE = 24;
  var LS = { fav: 'kama.favorites', viewed: 'kama.viewed', theme: 'kama.theme' };

  var CATS = [
    { id: 'hands',   emoji: '🛠', label: 'Руками',    color: 'var(--cat-hands)' },
    { id: 'head',    emoji: '🧠', label: 'Головой',   color: 'var(--cat-head)' },
    { id: 'service', emoji: '🛎', label: 'Сервис',    color: 'var(--cat-service)' },
    { id: 'remote',  emoji: '🌍', label: 'Удалённо',  color: 'var(--cat-remote)' },
    { id: 'part',    emoji: '⚡', label: 'Подработка', color: 'var(--cat-part)' },
    { id: 'other',   emoji: '❔', label: 'Другое',    color: 'var(--cat-other)' }
  ];
  var CAT_BY_ID = {};
  CATS.forEach(function (c) { CAT_BY_ID[c.id] = c; });

  var EMPLOYMENT = { full: 'Полная занятость', part: 'Частичная занятость', project: 'Проектная работа', probation: 'Стажировка', volunteer: 'Волонтёрство', flyInFlyOut: 'Вахтовый метод' };
  var EMPLOYMENT_SHORT = { full: 'Полная', part: 'Частичная', project: 'Проект', probation: 'Стажировка', volunteer: 'Волонтёрство', flyInFlyOut: 'Вахта' };
  var SCHEDULE = { fullDay: 'Полный день', shift: 'Сменный график', flexible: 'Гибкий график', remote: 'Удалённо', flyInFlyOut: 'Вахта' };
  var EXPERIENCE = { noExperience: 'Без опыта', between1And3: 'Опыт 1–3 года', between3And6: 'Опыт 3–6 лет', moreThan6: 'Опыт от 6 лет' };
  var SALARY_UNIT = { MONTH: 'в месяц', SHIFT: 'за смену', HOUR: 'за час', FLY_IN_FLY_OUT: 'за вахту', DAY: 'за день', WEEK: 'за неделю' };
  var REJ_COLORS = [
    ['var(--ember)', 'var(--amber)'], ['var(--magenta)', 'var(--violet)'],
    ['var(--teal)', 'var(--info)'], ['var(--warn)', 'var(--ember)'],
    ['var(--info)', 'var(--violet)'], ['var(--ok)', 'var(--teal)'],
    ['var(--violet)', 'var(--magenta)'], ['var(--danger)', 'var(--ember)']
  ];

  var nf = new Intl.NumberFormat('ru-RU');
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- утилиты ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function norm(s) {
    return String(s == null ? '' : s).toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();
  }
  function safeUrl(u, id) {
    var fallback = 'https://perm.hh.ru/vacancy/' + encodeURIComponent(id || '');
    try {
      var p = new URL(u, location.href);
      if ((p.protocol === 'https:' || p.protocol === 'http:') && /(^|\.)hh\.ru$/.test(p.hostname)) return p.href;
    } catch (e) {}
    return fallback;
  }
  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
    return many;
  }
  function money(n) { return nf.format(Math.round(n)); }
  function monthly(v) { return v.salary_from || v.salary_to || 0; }
  function readSet(key) {
    try { return new Set(JSON.parse(localStorage.getItem(key) || '[]')); } catch (e) { return new Set(); }
  }
  function writeSet(key, set) {
    try { localStorage.setItem(key, JSON.stringify(Array.from(set))); } catch (e) {}
  }
  function hoursSince(iso) {
    var t = Date.parse(iso);
    if (isNaN(t)) return Infinity;
    return (Date.now() - t) / 36e5;
  }
  function agoText(iso) {
    var h = hoursSince(iso);
    if (!isFinite(h)) return { short: '—', long: 'дата неизвестна' };
    if (h < 1) return { short: 'только что', long: 'меньше часа назад' };
    if (h < 24) return { short: 'сегодня', long: Math.floor(h) + ' ' + plural(Math.floor(h), 'час', 'часа', 'часов') + ' назад' };
    var d = Math.floor(h / 24);
    if (d === 1) return { short: 'вчера', long: 'вчера' };
    return { short: d + ' ' + plural(d, 'день', 'дня', 'дней') + ' назад', long: d + ' ' + plural(d, 'день', 'дня', 'дней') + ' назад' };
  }
  function updatedText(iso) {
    var h = hoursSince(iso);
    if (!isFinite(h)) return '—';
    if (h < 1) return 'только что';
    if (h < 24) return Math.floor(h) + ' ' + plural(Math.floor(h), 'час', 'часа', 'часов') + ' назад';
    var d = Math.floor(h / 24);
    return d + ' ' + plural(d, 'день', 'дня', 'дней') + ' назад';
  }
  function fullDate(iso) {
    var t = Date.parse(iso);
    if (isNaN(t)) return '—';
    return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }).format(new Date(t));
  }
  function trustColor(n) { return n >= 80 ? 'var(--ok)' : n >= 55 ? 'var(--warn)' : 'var(--danger)'; }
  function salaryText(v) {
    var mode = v.salary_mode || 'MONTH';
    var unit = SALARY_UNIT[mode] || 'в месяц';
    if (mode !== 'MONTH' && (v.salary_unit_from || v.salary_unit_to)) {
      var vfrom = v.salary_unit_from, vto = v.salary_unit_to;
      var main = vfrom && vto && vfrom !== vto ? money(vfrom) + '–' + money(vto) + ' ₽'
        : vfrom ? 'от ' + money(vfrom) + ' ₽' : 'до ' + money(vto) + ' ₽';
      return { main: main, unit: unit, monthly: monthly(v) };
    }
    var f = v.salary_from, t = v.salary_to;
    if (f && t && f !== t) return { main: money(f) + '–' + money(t) + ' ₽', unit: unit, monthly: 0 };
    if (f) return { main: 'от ' + money(f) + ' ₽', unit: unit, monthly: 0 };
    if (t) return { main: 'до ' + money(t) + ' ₽', unit: unit, monthly: 0 };
    return { main: 'Зарплата не указана', unit: '', monthly: 0 };
  }
  function placeText(v) {
    if (v.schedule === 'remote' || (v.categories || []).indexOf('remote') >= 0) return 'Удалённо · найм по РФ';
    var a = v.address || {};
    var parts = [];
    if (a.district) parts.push(a.district + ' район');
    if (a.street) parts.push(a.street);
    if (a.metro) parts.push('м. ' + a.metro);
    if (!parts.length) parts.push(a.city || 'Пермь');
    return parts.join(' · ');
  }
  function initials(name) {
    var words = String(name || '?').replace(/[«»"']/g, '').split(/[\s,.-]+/).filter(Boolean);
    if (!words.length) return '?';
    if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
    return (words[0][0] + words[1][0]).toUpperCase();
  }

  /* ---------- состояние ---------- */
  var S = {
    all: [], meta: null, filtered: [], shown: PAGE, rendered: 0,
    tab: 'all', q: '', cats: new Set(), salary: 50000, trust: 55,
    employment: '', schedule: '', district: '', sort: 'new',
    noExp: true, remote: true, trusted: false,
    fav: readSet(LS.fav), viewed: readSet(LS.viewed),
    loading: true, failed: false
  };

  var el = {};
  function cacheDom() {
    ['q', 'qClear', 'chips', 'salary', 'salaryOut', 'trust', 'trustOut', 'employment', 'schedule',
      'district', 'sort', 'onlyNoExp', 'showRemote', 'onlyTrusted', 'resetBtn', 'grid', 'skeletons',
      'emptyState', 'emptyText', 'emptyReset', 'errorState', 'retryBtn', 'moreWrap', 'loadMore',
      'moreN', 'shownNote', 'resultsCount', 'tabAll', 'tabFav', 'tabAllN', 'tabFavN', 'favPill',
      'favCountTop', 'histogram', 'staleNotice', 'statTotal', 'statNew', 'statUpdated',
      'statUpdatedLabel', 'panelSource', 'themeToggle', 'accordion', 'rejList', 'rejTotal',
      'howTrust', 'footerUpdated', 'shareBtn', 'toasts', 'drawer', 'drawerBody', 'scrim',
      'openSheet', 'closeSheet', 'applySheet', 'resetSheet', 'sheetCount', 'filterCount',
      'fabFilters', 'fabCount', 'topbar', 'filters', 'vacancies', 'how', 'ctaWatch', 'ghLink', 'ghLinkFoot'
    ].forEach(function (id) { el[id] = document.getElementById(id); });
  }

  /* ---------- тосты ---------- */
  var ICONS = {
    ok: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8"/><path d="m8 12.4 2.6 2.6L16 9.6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    fav: '<svg viewBox="0 0 24 24"><path d="M12 20s-7.5-4.6-7.5-9.4A4.1 4.1 0 0 1 12 8a4.1 4.1 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z" fill="currentColor"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8"/><path d="M12 11v5.4M12 7.8v.2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
  };
  function toast(msg, kind, action) {
    var t = document.createElement('div');
    t.className = 'toast toast--' + (kind || 'info');
    t.innerHTML = (ICONS[kind] || ICONS.info) + '<span>' + esc(msg) + '</span>';
    if (action) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'toast__undo'; b.textContent = action.label;
      b.addEventListener('click', function () { action.fn(); dismiss(); });
      t.appendChild(b);
    }
    el.toasts.appendChild(t);
    var timer = setTimeout(dismiss, action ? 6000 : 3200);
    function dismiss() {
      clearTimeout(timer);
      if (!t.parentNode) return;
      t.classList.add('is-out');
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 300);
    }
    while (el.toasts.children.length > 3) el.toasts.removeChild(el.toasts.firstChild);
  }

  /* ---------- URL ---------- */
  function readUrl() {
    var p = new URLSearchParams(location.search);
    if (p.get('q')) S.q = p.get('q');
    if (p.get('cat')) p.get('cat').split(',').forEach(function (c) { if (CAT_BY_ID[c]) S.cats.add(c); });
    if (p.get('salary')) S.salary = clamp(parseInt(p.get('salary'), 10) || 50000, 50000, 150000);
    if (p.get('trust')) S.trust = clamp(parseInt(p.get('trust'), 10) || 55, 55, 100);
    if (p.get('emp')) S.employment = p.get('emp');
    if (p.get('sch')) S.schedule = p.get('sch');
    if (p.get('dist')) S.district = p.get('dist');
    if (p.get('sort')) S.sort = ['new', 'salary', 'trust'].indexOf(p.get('sort')) >= 0 ? p.get('sort') : 'new';
    if (p.get('noexp') === '0') S.noExp = false;
    if (p.get('remote') === '0') S.remote = false;
    if (p.get('trusted') === '1') S.trusted = true;
    if (p.get('tab') === 'fav') S.tab = 'fav';
  }
  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }
  function writeUrl() {
    var p = new URLSearchParams();
    if (S.q) p.set('q', S.q);
    if (S.cats.size) p.set('cat', Array.from(S.cats).join(','));
    if (S.salary !== 50000) p.set('salary', S.salary);
    if (S.trust !== 55) p.set('trust', S.trust);
    if (S.employment) p.set('emp', S.employment);
    if (S.schedule) p.set('sch', S.schedule);
    if (S.district) p.set('dist', S.district);
    if (S.sort !== 'new') p.set('sort', S.sort);
    if (!S.noExp) p.set('noexp', '0');
    if (!S.remote) p.set('remote', '0');
    if (S.trusted) p.set('trusted', '1');
    if (S.tab === 'fav') p.set('tab', 'fav');
    var qs = p.toString();
    try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash); } catch (e) {}
  }
  function activeFilterCount() {
    var n = 0;
    if (S.q) n++;
    n += S.cats.size;
    if (S.salary !== 50000) n++;
    if (S.trust !== 55) n++;
    if (S.employment) n++;
    if (S.schedule) n++;
    if (S.district) n++;
    if (!S.noExp) n++;
    if (!S.remote) n++;
    if (S.trusted) n++;
    return n;
  }

  /* ---------- фильтрация ---------- */
  function matches(v, ignore) {
    if (S.tab === 'fav' && !S.fav.has(String(v.id))) return false;
    if (ignore !== 'cats' && S.cats.size) {
      var vc = v.categories || [v.category];
      var hit = false;
      S.cats.forEach(function (c) { if (vc.indexOf(c) >= 0) hit = true; });
      if (!hit) return false;
    }
    if (ignore !== 'q' && S.q) {
      var hay = norm(v.title) + ' ' + norm((v.employer || {}).name);
      var words = norm(S.q).split(' ');
      for (var i = 0; i < words.length; i++) if (words[i] && hay.indexOf(words[i]) < 0) return false;
    }
    if (ignore !== 'salary' && monthly(v) < S.salary) return false;
    if ((v.trust_score || 0) < S.trust) return false;
    if (S.employment && v.employment !== S.employment) return false;
    if (S.schedule && v.schedule !== S.schedule) return false;
    if (S.district && norm((v.address || {}).district) !== norm(S.district)) return false;
    if (S.noExp && v.experience !== 'noExperience') return false;
    if (!S.remote && ((v.categories || []).indexOf('remote') >= 0 || v.schedule === 'remote')) return false;
    if (S.trusted && !(v.employer || {}).trusted) return false;
    return true;
  }
  function sortList(list) {
    var arr = list.slice();
    if (S.sort === 'salary') {
      arr.sort(function (a, b) { return monthly(b) - monthly(a) || (b.trust_score - a.trust_score); });
    } else if (S.sort === 'trust') {
      arr.sort(function (a, b) { return (b.trust_score - a.trust_score) || monthly(b) - monthly(a); });
    } else {
      arr.sort(function (a, b) {
        var ea = a.experience === 'noExperience' ? 0 : 1;
        var eb = b.experience === 'noExperience' ? 0 : 1;
        return ea - eb || (Date.parse(b.published_at) || 0) - (Date.parse(a.published_at) || 0);
      });
    }
    return arr;
  }

  /* ---------- отрисовка фильтров ---------- */
  function renderChips() {
    var counts = {};
    CATS.forEach(function (c) { counts[c.id] = 0; });
    S.all.forEach(function (v) {
      if (!matches(v, 'cats')) return;
      (v.categories || [v.category]).forEach(function (c) { if (counts[c] != null) counts[c]++; });
    });
    el.chips.innerHTML = CATS.map(function (c) {
      var on = S.cats.has(c.id);
      return '<button type="button" class="chip' + (on ? ' is-active' : '') + '" data-cat="' + c.id + '" aria-pressed="' + on + '">' +
        '<span class="chip__emoji" aria-hidden="true">' + c.emoji + '</span>' + esc(c.label) +
        '<span class="chip__n">' + counts[c.id] + '</span></button>';
    }).join('');
  }

  function renderHistogram() {
    var BINS = 20, MIN = 50000, MAX = 150000, step = (MAX - MIN) / BINS;
    var bins = new Array(BINS).fill(0);
    S.all.forEach(function (v) {
      if (!matches(v, 'salary')) return;
      var m = monthly(v);
      var i = m >= MAX ? BINS - 1 : Math.floor((m - MIN) / step);
      if (i >= 0 && i < BINS) bins[i]++;
    });
    var max = Math.max.apply(null, bins.concat([1]));
    el.histogram.innerHTML = bins.map(function (n, i) {
      var h = Math.max(8, Math.round(n / max * 100));
      var inRange = MIN + i * step >= S.salary - 1;
      return '<i class="' + (inRange ? 'is-in' : '') + '" style="height:' + h + '%"></i>';
    }).join('');
  }

  function renderDistricts() {
    var set = {};
    S.all.forEach(function (v) {
      var d = (v.address || {}).district;
      if (d) set[d] = (set[d] || 0) + 1;
    });
    var names = Object.keys(set).sort(function (a, b) { return set[b] - set[a] || a.localeCompare(b, 'ru'); });
    var cur = S.district;
    el.district.innerHTML = '<option value="">Любой район</option>' + names.map(function (n) {
      return '<option value="' + esc(n) + '"' + (norm(n) === norm(cur) ? ' selected' : '') + '>' + esc(n) + ' (' + set[n] + ')</option>';
    }).join('');
    if (cur && names.indexOf(cur) < 0) S.district = '';
  }

  function syncControls() {
    el.q.value = S.q;
    el.qClear.hidden = !S.q;
    el.salary.value = S.salary;
    el.salaryOut.textContent = money(S.salary) + ' ₽';
    el.trust.value = S.trust;
    el.trustOut.textContent = S.trust;
    el.employment.value = S.employment;
    el.schedule.value = S.schedule;
    el.sort.value = S.sort;
    el.onlyNoExp.checked = S.noExp;
    el.showRemote.checked = S.remote;
    el.onlyTrusted.checked = S.trusted;
    paintRange(el.salary);
    paintRange(el.trust);
    var n = activeFilterCount();
    [el.filterCount, el.fabCount].forEach(function (b) {
      if (!b) return;
      b.textContent = n;
      b.classList.toggle('is-zero', n === 0);
    });
    el.tabAll.classList.toggle('is-active', S.tab === 'all');
    el.tabFav.classList.toggle('is-active', S.tab === 'fav');
    el.tabAll.setAttribute('aria-selected', S.tab === 'all');
    el.tabFav.setAttribute('aria-selected', S.tab === 'fav');
    el.favPill.classList.toggle('is-active', S.tab === 'fav');
    el.tabAllN.textContent = S.all.length;
    el.tabFavN.textContent = S.fav.size;
    el.favCountTop.textContent = S.fav.size;
    el.favCountTop.classList.toggle('is-zero', S.fav.size === 0);
    el.sheetCount.textContent = S.filtered.length;
  }
  function paintRange(input) {
    var min = parseFloat(input.min), max = parseFloat(input.max), val = parseFloat(input.value);
    input.style.setProperty('--fill', ((val - min) / (max - min) * 100) + '%');
  }

  /* ---------- карточки ---------- */
  var observer = null;
  function ensureObserver() {
    if (observer || !('IntersectionObserver' in window)) return;
    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('is-in'); observer.unobserve(en.target); }
      });
    }, { rootMargin: '80px 0px', threshold: 0.04 });
  }

  function ringHtml(score, big) {
    var r = 20, circ = 2 * Math.PI * r;
    var off = circ * (1 - clamp(score, 0, 100) / 100);
    return '<span class="ring" style="--rc:' + trustColor(score) + ';--circ:' + circ.toFixed(2) + ';--off:' + off.toFixed(2) + '" title="Рейтинг доверия ' + score + ' из 100">' +
      '<svg viewBox="0 0 48 48" aria-hidden="true">' +
      '<circle class="ring__bg" cx="24" cy="24" r="' + r + '" fill="none" stroke-width="4"/>' +
      '<circle class="ring__fg" cx="24" cy="24" r="' + r + '" fill="none" stroke-width="4"/>' +
      '</svg><span class="ring__n">' + score + '</span></span>';
  }

  function avatarHtml(emp, cls) {
    var name = (emp || {}).name || '?';
    var logo = (emp || {}).logo;
    var inner = logo && /^https:\/\//.test(logo)
      ? '<img src="' + esc(logo) + '" alt="" loading="lazy" onerror="this.parentNode.textContent=\'' + esc(initials(name)).replace(/'/g, '') + '\'">'
      : esc(initials(name));
    return '<span class="avatar ' + (cls || '') + '" aria-hidden="true">' + inner + '</span>';
  }

  function badgesHtml(v) {
    var out = [];
    var cat = CAT_BY_ID[v.category] || CAT_BY_ID.other;
    if (v.is_hot) out.push('<span class="badge badge--hot">🔥 Новая</span>');
    else if (v.is_new) out.push('<span class="badge badge--hot">Свежая</span>');
    out.push('<span class="badge badge--cat">' + cat.emoji + ' ' + esc(cat.label) + '</span>');
    if (v.employment) out.push('<span class="badge">' + esc(EMPLOYMENT_SHORT[v.employment] || v.employment) + '</span>');
    if (v.schedule) out.push('<span class="badge' + (v.schedule === 'remote' ? ' badge--remote' : '') + '">' + esc(SCHEDULE[v.schedule] || v.schedule) + '</span>');
    if (v.experience && v.experience !== 'noExperience') out.push('<span class="badge badge--exp">Нужен ' + esc((EXPERIENCE[v.experience] || v.experience).toLowerCase()) + '</span>');
    else out.push('<span class="badge badge--part">Без опыта</span>');
    if ((v.categories || []).indexOf('part') >= 0 && v.employment === 'full' && v.schedule !== 'flexible') out.push('<span class="badge badge--part">Подработка</span>');
    if (v.similar_count) out.push('<span class="badge badge--similar">+' + v.similar_count + ' похожих</span>');
    return out.join('');
  }

  function cardHtml(v) {
    var sal = salaryText(v);
    var cat = CAT_BY_ID[v.category] || CAT_BY_ID.other;
    var ago = agoText(v.published_at);
    var emp = v.employer || {};
    var id = String(v.id);
    var isFav = S.fav.has(id);
    var viewed = S.viewed.has(id);
    return '<article class="card' + (viewed ? ' is-viewed' : '') + '" data-id="' + esc(id) + '" style="--cat:' + cat.color + '" tabindex="0" aria-label="' + esc(v.title) + ', ' + esc(sal.main) + '">' +
      '<div class="card__top">' +
        '<h3 class="card__title">' + esc(v.title) + '</h3>' +
        '<button type="button" class="card__fav' + (isFav ? ' is-on' : '') + '" data-fav="' + esc(id) + '" aria-pressed="' + isFav + '" aria-label="' + (isFav ? 'Убрать из избранного' : 'В избранное') + '">' +
          '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20s-7.5-4.6-7.5-9.4A4.1 4.1 0 0 1 12 8a4.1 4.1 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>' +
        '</button>' +
      '</div>' +
      '<div class="card__employer">' + avatarHtml(emp) +
        '<span class="card__emp-name">' + esc(emp.name || 'Работодатель не указан') + '</span>' +
        (emp.trusted ? '<span class="verified" title="Работодатель проверен на hh.ru"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="currentColor" opacity=".18"/><path d="m8 12.3 2.6 2.6L16 9.5" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/></svg>Проверенный</span>' : '') +
      '</div>' +
      '<div class="card__salary"><span class="salary__n">' + esc(sal.main) + '</span>' +
        '<span class="salary__u">' + esc(sal.unit) + '</span>' +
        (v.salary_gross ? '<span class="salary__gross">до вычета</span>' : '') +
        (sal.monthly ? '<span class="salary__gross">≈ ' + money(sal.monthly) + ' ₽/мес</span>' : '') +
      '</div>' +
      '<div class="badges">' + badgesHtml(v) + '</div>' +
      '<p class="card__place"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 21s7-6.1 7-11a7 7 0 1 0-14 0c0 4.9 7 11 7 11z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><circle cx="12" cy="10" r="2.4" stroke="currentColor" stroke-width="1.7"/></svg><span>' + esc(placeText(v)) + '</span></p>' +
      (v.snippet ? '<p class="card__snippet">' + esc(v.snippet) + '</p>' : '') +
      '<div class="card__foot">' + ringHtml(v.trust_score || 0) +
        '<span class="card__date"><b>' + esc(ago.short) + '</b><span>' + esc(ago.long === ago.short ? 'опубликована' : ago.long) + '</span></span>' +
        '<a class="card__open" href="' + esc(safeUrl(v.url, v.id)) + '" target="_blank" rel="noopener noreferrer" data-open="' + esc(id) + '">Открыть<span> на hh.ru</span><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg></a>' +
      '</div>' +
    '</article>';
  }

  function appendCards(list) {
    if (!list.length) return;
    var frag = document.createElement('div');
    frag.innerHTML = list.map(cardHtml).join('');
    var nodes = Array.prototype.slice.call(frag.children);
    nodes.forEach(function (n, i) {
      n.style.transitionDelay = reduced ? '0ms' : Math.min(i, 12) * 30 + 'ms';
      el.grid.appendChild(n);
      if (observer) observer.observe(n); else n.classList.add('is-in');
    });
    S.rendered += nodes.length;
  }

  function renderSkeletons(on) {
    if (on) {
      el.skeletons.innerHTML = new Array(6).fill(0).map(function () {
        return '<div class="sk"><i class="sk__t"></i><i class="sk__t2"></i><i class="sk__e"></i><i class="sk__s"></i><i class="sk__b"></i><i class="sk__p"></i><i class="sk__p2"></i><i class="sk__f"></i></div>';
      }).join('');
      el.skeletons.hidden = false;
    } else {
      el.skeletons.hidden = true;
      el.skeletons.innerHTML = '';
    }
  }

  function render(opts) {
    opts = opts || {};
    S.filtered = sortList(S.all.filter(function (v) { return matches(v); }));
    if (!opts.keepShown) S.shown = PAGE;
    S.rendered = 0;
    el.grid.innerHTML = '';
    ensureObserver();
    appendCards(S.filtered.slice(0, S.shown));

    var total = S.filtered.length;
    el.resultsCount.innerHTML = total
      ? 'Найдено <b>' + total + '</b> ' + plural(total, 'вакансия', 'вакансии', 'вакансий') +
        (S.tab === 'fav' ? ' в избранном' : '') + ' · показано ' + Math.min(S.shown, total)
      : (S.tab === 'fav' ? 'В избранном пока пусто' : 'Ничего не найдено');

    var isEmpty = total === 0 && !S.loading && !S.failed;
    el.emptyState.hidden = !isEmpty;
    if (isEmpty) {
      if (S.tab === 'fav') {
        el.emptyText.textContent = S.fav.size
          ? 'Избранные вакансии не прошли текущие фильтры. Сбросьте их или переключитесь на «Все вакансии».'
          : 'Нажимайте ♡ на карточке, чтобы сохранить вакансию. Список хранится в этом браузере.';
        el.emptyReset.textContent = 'Показать все вакансии';
      } else {
        el.emptyText.textContent = 'Попробуйте снизить зарплату или убрать фильтр категории — в Перми точно есть работа.';
        el.emptyReset.textContent = 'Сбросить фильтры';
      }
    }
    el.errorState.hidden = !S.failed;
    el.moreWrap.hidden = total <= S.shown || S.failed;
    el.moreN.textContent = Math.min(PAGE, total - S.shown);
    el.shownNote.textContent = total > S.shown
      ? 'Показано ' + S.rendered + ' из ' + total + ' ' + plural(total, 'вакансии', 'вакансий', 'вакансий')
      : '';
    el.grid.hidden = S.failed;
    renderChips();
    renderHistogram();
    syncControls();
    writeUrl();
  }

  function loadMore() {
    var next = S.filtered.slice(S.rendered, S.shown + PAGE);
    S.shown += PAGE;
    appendCards(next);
    el.moreWrap.hidden = S.rendered >= S.filtered.length;
    el.moreN.textContent = Math.min(PAGE, S.filtered.length - S.rendered);
    el.shownNote.textContent = 'Показано ' + S.rendered + ' из ' + S.filtered.length;
    el.resultsCount.innerHTML = 'Найдено <b>' + S.filtered.length + '</b> ' + plural(S.filtered.length, 'вакансия', 'вакансии', 'вакансий') +
      (S.tab === 'fav' ? ' в избранном' : '') + ' · показано ' + S.rendered;
  }

  /* ---------- избранное и просмотрено ---------- */
  function toggleFav(id, btn) {
    id = String(id);
    var on = !S.fav.has(id);
    if (on) S.fav.add(id); else S.fav.delete(id);
    writeSet(LS.fav, S.fav);
    $$('[data-fav="' + id + '"]').forEach(function (b) {
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-pressed', on);
      b.setAttribute('aria-label', on ? 'Убрать из избранного' : 'В избранное');
    });
    if (btn && on && !reduced) {
      btn.classList.remove('is-pop');
      void btn.offsetWidth;
      btn.classList.add('is-pop');
      for (var i = 0; i < 8; i++) {
        var s = document.createElement('span');
        s.className = 'spark';
        var ang = (Math.PI * 2 * i) / 8;
        s.style.setProperty('--dx', (Math.cos(ang) * 26).toFixed(1) + 'px');
        s.style.setProperty('--dy', (Math.sin(ang) * 26).toFixed(1) + 'px');
        s.style.background = i % 2 ? 'var(--amber)' : 'var(--magenta)';
        btn.appendChild(s);
        (function (node) { setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 650); })(s);
      }
    }
    syncControls();
    var v = findVacancy(id);
    if (on) {
      toast('Добавлено в избранное: ' + (v ? v.title : id), 'fav', {
        label: 'Отменить', fn: function () { toggleFav(id, null); }
      });
    } else {
      toast('Убрано из избранного', 'info', { label: 'Вернуть', fn: function () { toggleFav(id, null); } });
    }
    if (S.tab === 'fav') render();
  }
  function findVacancy(id) {
    for (var i = 0; i < S.all.length; i++) if (String(S.all[i].id) === String(id)) return S.all[i];
    return null;
  }
  function markViewed(id) {
    id = String(id);
    if (S.viewed.has(id)) return;
    S.viewed.add(id);
    writeSet(LS.viewed, S.viewed);
    var card = el.grid.querySelector('.card[data-id="' + id + '"]');
    if (card) card.classList.add('is-viewed');
  }

  /* ---------- drawer ---------- */
  var lastFocus = null;
  function openDrawer(id) {
    var v = findVacancy(id);
    if (!v) return;
    markViewed(id);
    lastFocus = document.activeElement;
    var cat = CAT_BY_ID[v.category] || CAT_BY_ID.other;
    var sal = salaryText(v);
    var emp = v.employer || {};
    var a = v.address || {};
    var isFav = S.fav.has(String(v.id));
    var signals = (v.trust_signals || []).map(function (s) {
      var pos = s.delta > 0;
      return '<li class="signal" style="--sc:' + (pos ? 'var(--ok)' : 'var(--danger)') + '">' +
        '<span class="signal__d">' + (pos ? '+' : '') + s.delta + '</span><span>' + esc(s.label) + '</span></li>';
    }).join('');
    var stars = emp.rating ? '★'.repeat(Math.round(emp.rating)) + '☆'.repeat(Math.max(0, 5 - Math.round(emp.rating))) : '';

    el.drawerBody.innerHTML =
      '<p class="d-cat" style="--cat:' + cat.color + '">' + cat.emoji + ' ' + esc(cat.label) +
        (v.is_hot ? ' · 🔥 новая' : '') + '</p>' +
      '<h2 class="d-title" id="drawerTitle">' + esc(v.title) + '</h2>' +
      '<div class="d-emp">' + avatarHtml(emp) +
        '<div><p class="d-emp__n">' + esc(emp.name || 'Работодатель не указан') +
          (emp.trusted ? ' <span class="verified">✓ проверенный</span>' : '') + '</p>' +
          '<p class="d-emp__meta">' + (stars ? '<span class="stars">' + stars + '</span><span>' + esc(String(emp.rating)) + ' · ' + emp.reviews + ' ' + plural(emp.reviews || 0, 'отзыв', 'отзыва', 'отзывов') + '</span>' : '<span>отзывов пока нет</span>') +
          (emp.category === 'AGENCY' ? '<span>· кадровое агентство</span>' : '') + '</p>' +
        '</div>' +
      '</div>' +
      '<div class="d-salary"><span class="salary__n">' + esc(sal.main) + '</span><span class="salary__u">' + esc(sal.unit) + '</span>' +
        (v.salary_gross ? '<span class="salary__gross">до вычета налогов</span>' : '<span class="salary__gross">на руки</span>') +
        (sal.monthly ? '<span class="salary__u">≈ ' + money(sal.monthly) + ' ₽ в месяц</span>' : '') +
        (v.salary_frequency === 'DAILY' ? '<span class="salary__u">· выплаты каждый день</span>' : '') +
        (v.salary_frequency === 'TWICE_PER_MONTH' ? '<span class="salary__u">· выплаты 2 раза в месяц</span>' : '') +
      '</div>' +
      '<div class="d-sec"><p class="d-sec__h">Условия</p><dl class="d-kv">' +
        '<div><dt>Занятость</dt><dd>' + esc(EMPLOYMENT[v.employment] || '—') + '</dd></div>' +
        '<div><dt>График</dt><dd>' + esc(SCHEDULE[v.schedule] || '—') + '</dd></div>' +
        '<div><dt>Опыт</dt><dd>' + esc(EXPERIENCE[v.experience] || '—') + '</dd></div>' +
        '<div><dt>Опубликована</dt><dd>' + esc(fullDate(v.published_at)) + '</dd></div>' +
        '<div><dt>Адрес</dt><dd>' + esc([a.street, a.district ? a.district + ' район' : '', a.city].filter(Boolean).join(', ') || 'Пермь') + '</dd></div>' +
        '<div><dt>Откликов на hh</dt><dd>' + (v.responses || 0) + '</dd></div>' +
      '</dl></div>' +
      (v.snippet ? '<div class="d-sec"><p class="d-sec__h">Коротко о работе</p><p>' + esc(v.snippet) + '</p></div>' : '') +
      ((v.key_skills || []).length ? '<div class="d-sec"><p class="d-sec__h">Ключевые навыки</p><div class="d-skills">' +
        v.key_skills.map(function (s) { return '<span>' + esc(s) + '</span>'; }).join('') + '</div></div>' : '') +
      ((v.tags || []).length ? '<div class="d-sec"><p class="d-sec__h">Метки</p><div class="d-skills">' +
        v.tags.map(function (s) { return '<span>' + esc(s) + '</span>'; }).join('') + '</div></div>' : '') +
      '<div class="d-sec"><p class="d-sec__h">Почему такой рейтинг доверия</p>' +
        '<div class="d-trust">' + ringHtml(v.trust_score || 0, true) +
          '<div><p class="d-trust__t">' + (v.trust_score >= 80 ? 'Высокое доверие' : v.trust_score >= 55 ? 'Нормальное доверие' : 'Низкое доверие') + '</p>' +
          '<p class="d-trust__s">' + (v.trust_score || 0) + ' из 100 · база 40 + сигналы проверки</p></div>' +
        '</div>' +
        (signals ? '<ul class="signals">' + signals + '</ul>' : '<p>Сигналы не рассчитаны для этой вакансии.</p>') +
      '</div>' +
      (v.similar_count ? '<div class="d-sec"><p class="d-sec__h">Похожие вакансии</p><p>У этого работодателя ещё ' + v.similar_count + ' ' + plural(v.similar_count, 'похожая вакансия', 'похожие вакансии', 'похожих вакансий') + ' — показываем самую свежую, чтобы не засорять выдачу.</p></div>' : '') +
      '<div class="d-actions">' +
        '<a class="btn btn--primary" href="' + esc(safeUrl(v.url, v.id)) + '" target="_blank" rel="noopener noreferrer" data-open="' + esc(v.id) + '">Открыть на hh.ru' +
          '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg></a>' +
        '<button type="button" class="btn btn--ghost" data-fav="' + esc(v.id) + '" aria-pressed="' + isFav + '">' +
          (isFav ? '♥ В избранном' : '♡ В избранное') + '</button>' +
      '</div>';

    el.drawer.hidden = false;
    document.body.classList.add('is-locked');
    var ring = el.drawerBody.querySelector('.ring');
    if (ring) requestAnimationFrame(function () { ring.parentNode.classList.add('is-in'); });
    var closeBtn = el.drawer.querySelector('.drawer__close');
    if (closeBtn) closeBtn.focus();
  }
  function closeDrawer() {
    if (el.drawer.hidden) return;
    el.drawer.hidden = true;
    document.body.classList.remove('is-locked');
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    if (S.tab === 'fav') render();
  }

  /* ---------- шторка фильтров ---------- */
  function openSheet() {
    document.body.classList.add('sheet-open', 'is-locked');
    el.scrim.hidden = false;
    requestAnimationFrame(function () { el.scrim.classList.add('is-on'); });
    el.openSheet.setAttribute('aria-expanded', 'true');
    el.fabFilters.classList.add('is-hidden');
    el.sheetCount.textContent = S.filtered.length;
    setTimeout(function () { el.closeSheet.focus(); }, 60);
  }
  function closeSheet() {
    if (!document.body.classList.contains('sheet-open')) return;
    document.body.classList.remove('sheet-open', 'is-locked');
    el.scrim.classList.remove('is-on');
    setTimeout(function () { if (!document.body.classList.contains('sheet-open')) el.scrim.hidden = true; }, 300);
    el.openSheet.setAttribute('aria-expanded', 'false');
    el.fabFilters.classList.remove('is-hidden');
  }

  /* ---------- герой и мета ---------- */
  function countUp(node, to) {
    if (!node) return;
    if (reduced) { node.textContent = nf.format(to); return; }
    var start = performance.now(), dur = 1100, from = 0;
    function step(t) {
      var p = Math.min(1, (t - start) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      node.textContent = nf.format(Math.round(from + (to - from) * e));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function renderMeta() {
    var m = S.meta || {};
    countUp(el.statTotal, m.total_published != null ? m.total_published : S.all.length);
    countUp(el.statNew, m.new_today || 0);
    refreshUpdated();
    if (m.source) {
      el.panelSource.textContent = 'источник: hh.ru · ' + (m.source === 'api' ? 'официальный API' : m.source === 'html' ? 'выдача hh.ru' : 'кэш');
    }
    el.howTrust.textContent = m.trust_min || 55;
    el.footerUpdated.textContent = m.updated_at ? fullDate(m.updated_at) : '—';
    el.footerUpdated.setAttribute('datetime', m.updated_at || '');
    if (m.repo_url) { el.ghLink.href = m.repo_url; el.ghLinkFoot.href = m.repo_url; }
    var stale = hoursSince(m.updated_at) > (m.stale_after_hours || 24);
    el.staleNotice.hidden = !stale || S.failed;
    renderRejects(m);
  }
  function refreshUpdated() {
    var m = S.meta || {};
    el.statUpdated.textContent = updatedText(m.updated_at);
    el.statUpdatedLabel.textContent = m.updated_at ? 'обновлено · ' + (m.source === 'api' ? 'API hh.ru' : 'hh.ru') : 'обновлено';
  }

  var ACCORDION = [
    {
      ac: 'var(--ok)', title: 'Проверяем работодателя',
      sub: 'Аккредитация hh, история компании, несколько вакансий',
      icon: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3 5 6v5.5c0 4.3 3 8.1 7 9.5 4-1.4 7-5.2 7-9.5V6z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="m9 12 2.2 2.2L15.5 10" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      body: '<p>Работодатель с пометкой <b>«проверенный»</b> на hh.ru получает +25 баллов. Ещё +15 — если это известная компания со страницей, сайтом и несколькими вакансиями, а не однодневка.</p>' +
            '<p>Частное лицо без названия компании получает <b>−25</b>. Кадровые агентства не считаются «известной компанией»: в карточке это видно, решение за вами.</p>' +
            '<div class="acc__tags"><span>+25 trusted</span><span>+15 история</span><span>−25 частное лицо</span></div>'
    },
    {
      ac: 'var(--info)', title: 'Читаем описание',
      sub: 'Обязанности, требования, адрес, оформление по ТК',
      icon: '<svg viewBox="0 0 24 24" fill="none"><path d="M6 3.5h8.5L19 8v12.5H6z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14 3.5V8h5M9 12h7M9 15.5h7M9 8.5h2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
      body: '<p>Подробное описание от <b>400 символов</b> с чёткими обязанностями и требованиями — +15. Конкретный адрес или район — +10. Оформление по ТК РФ, ДМС, спецодежда, компенсация питания — +10.</p>' +
            '<p>Пустое описание короче 150 символов — <b>−20</b>: нормальная компания всегда пишет, что предстоит делать.</p>' +
            '<div class="acc__tags"><span>+15 описание</span><span>+10 адрес</span><span>+10 соцпакет</span><span>−20 пусто</span></div>'
    },
    {
      ac: 'var(--ember)', title: 'Режем по стоп-словам',
      sub: 'Скам, МЛМ, дропы, платное трудоустройство и мусор',
      icon: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.6" stroke="currentColor" stroke-width="1.8"/><path d="m6.2 6.2 11.6 11.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
      body: '<p>Вакансия удаляется целиком, если в названии или описании есть маркеры развода: <b>сетевой маркетинг, МЛМ, «доход не ограничен», быстрые деньги, дроп, обнал, закладки, платное обучение, вступительный взнос, депозит</b>, отзывы и лайки за деньги.</p>' +
            '<p>Отдельно режем «от 5000 в день» без обязанностей, СПЛОШНОЙ КАПС и названия с восклицательными знаками. Гео-обманки тоже мимо: вакансия числится в Перми, а работать зовут в другой город.</p>' +
            '<div class="acc__tags"><span>МЛМ</span><span>дропы</span><span>платный вход</span><span>капс</span><span>другой город</span></div>'
    },
    {
      ac: 'var(--amber)', title: 'Считаем рейтинг доверия',
      sub: 'База 40, сигналы ±, в выдачу только от 55 баллов',
      icon: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 19V9M9.3 19V5M14.7 19v-8M20 19v-5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
      body: '<p>Каждая вакансия получает баллы от 0 до 100. База — <b>40</b>, дальше плюсы и минусы за сигналы. В выдачу попадает только то, что набрало <b>≥ 55</b>. Ползунок «Рейтинг доверия от» поднимает порог ещё выше.</p>' +
            '<p>Зарплата выше <b>2.5× медианы</b> по похожим вакансиям при «без опыта» — минус 30. Одинаковый текст у пяти и более разных «компаний» — минус 40. Связь только через Telegram или WhatsApp — минус 20.</p>' +
            '<p>В карточке видно кольцо рейтинга, а по клику — полная расшифровка: за что начислены и сняты баллы.</p>' +
            '<div class="acc__tags"><span>−30 завышенная ЗП</span><span>−40 клоны</span><span>−20 мессенджер</span></div>'
    }
  ];

  function renderAccordion() {
    el.accordion.innerHTML = ACCORDION.map(function (a, i) {
      return '<div class="acc' + (i === 0 ? ' is-open' : '') + '" style="--ac:' + a.ac + '">' +
        '<button type="button" class="acc__btn" aria-expanded="' + (i === 0) + '" aria-controls="acc-body-' + i + '" id="acc-btn-' + i + '">' +
          '<span class="acc__ico" aria-hidden="true">' + a.icon + '</span>' +
          '<span class="acc__txt"><h3>' + esc(a.title) + '</h3><p>' + esc(a.sub) + '</p></span>' +
          '<svg class="acc__chev" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 9 6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
        '</button>' +
        '<div class="acc__body" id="acc-body-' + i + '" role="region" aria-labelledby="acc-btn-' + i + '"><div class="acc__inner"><div class="acc__content">' + a.body + '</div></div></div>' +
      '</div>';
    }).join('');
    el.accordion.addEventListener('click', function (e) {
      var btn = e.target.closest('.acc__btn');
      if (!btn) return;
      var acc = btn.parentNode;
      var open = acc.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', open);
    });
  }

  function renderRejects(m) {
    var reasons = m.rejected_reasons || {};
    var entries = Object.keys(reasons).map(function (k) { return [k, reasons[k]]; })
      .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 7);
    el.rejTotal.textContent = nf.format(m.total_rejected || 0);
    if (!entries.length) {
      el.rejList.innerHTML = '<li class="rej"><span class="rej__name">Статистика появится после первого обновления</span></li>';
      return;
    }
    var max = entries[0][1] || 1;
    el.rejList.innerHTML = entries.map(function (e, i) {
      var c = REJ_COLORS[i % REJ_COLORS.length];
      return '<li class="rej"><div class="rej__top"><span class="rej__name">' + esc(e[0]) + '</span><span class="rej__n">' + e[1] + '</span></div>' +
        '<div class="rej__bar"><div class="rej__fill" style="--c1:' + c[0] + ';--c2:' + c[1] + '" data-w="' + Math.max(4, Math.round(e[1] / max * 100)) + '"></div></div></li>';
    }).join('');
    requestAnimationFrame(function () {
      $$('.rej__fill', el.rejList).forEach(function (n) { n.style.width = n.dataset.w + '%'; });
    });
  }

  /* ---------- события ---------- */
  function resetFilters(keepTab) {
    S.q = ''; S.cats = new Set(); S.salary = 50000; S.trust = 55;
    S.employment = ''; S.schedule = ''; S.district = ''; S.sort = 'new';
    S.noExp = true; S.remote = true; S.trusted = false;
    if (!keepTab) S.tab = 'all';
    el.district.value = '';
    render();
    toast('Фильтры сброшены', 'ok');
  }

  function bind() {
    var qTimer = null;
    el.q.addEventListener('input', function () {
      S.q = el.q.value;
      el.qClear.hidden = !S.q;
      clearTimeout(qTimer);
      qTimer = setTimeout(function () { render(); }, 160);
    });
    el.qClear.addEventListener('click', function () {
      S.q = ''; el.q.value = ''; el.qClear.hidden = true; render(); el.q.focus();
    });

    el.chips.addEventListener('click', function (e) {
      var b = e.target.closest('[data-cat]');
      if (!b) return;
      var c = b.dataset.cat;
      if (S.cats.has(c)) S.cats.delete(c); else S.cats.add(c);
      render();
    });

    el.salary.addEventListener('input', function () {
      S.salary = parseInt(el.salary.value, 10);
      el.salaryOut.textContent = money(S.salary) + ' ₽';
      paintRange(el.salary);
      render();
    });
    el.trust.addEventListener('input', function () {
      S.trust = parseInt(el.trust.value, 10);
      el.trustOut.textContent = S.trust;
      paintRange(el.trust);
      render();
    });

    [['employment', 'employment'], ['schedule', 'schedule'], ['district', 'district'], ['sort', 'sort']].forEach(function (pair) {
      el[pair[0]].addEventListener('change', function () { S[pair[1]] = el[pair[0]].value; render(); });
    });
    [['onlyNoExp', 'noExp'], ['showRemote', 'remote'], ['onlyTrusted', 'trusted']].forEach(function (pair) {
      el[pair[0]].addEventListener('change', function () { S[pair[1]] = el[pair[0]].checked; render(); });
    });

    el.resetBtn.addEventListener('click', function () { resetFilters(); });
    el.resetSheet.addEventListener('click', function () { resetFilters(); closeSheet(); });
    el.emptyReset.addEventListener('click', function () {
      if (S.tab === 'fav') { S.tab = 'all'; render(); } else resetFilters();
    });
    el.retryBtn.addEventListener('click', function () { location.reload(); });
    el.loadMore.addEventListener('click', loadMore);

    el.tabAll.addEventListener('click', function () { S.tab = 'all'; render(); });
    el.tabFav.addEventListener('click', function () { S.tab = 'fav'; render(); });
    el.favPill.addEventListener('click', function () {
      S.tab = S.tab === 'fav' ? 'all' : 'fav';
      render();
      document.getElementById('vacancies').scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    });

    el.grid.addEventListener('click', function (e) {
      var fav = e.target.closest('[data-fav]');
      if (fav) { e.preventDefault(); e.stopPropagation(); toggleFav(fav.dataset.fav, fav); return; }
      var open = e.target.closest('[data-open]');
      if (open) { markViewed(open.dataset.open); return; }
      var card = e.target.closest('.card');
      if (card) openDrawer(card.dataset.id);
    });
    el.grid.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var card = e.target.closest('.card');
      if (card && e.target === card) { e.preventDefault(); openDrawer(card.dataset.id); }
    });

    el.drawer.addEventListener('click', function (e) {
      if (e.target.closest('[data-close]')) { closeDrawer(); return; }
      var fav = e.target.closest('[data-fav]');
      if (fav) {
        toggleFav(fav.dataset.fav, null);
        var on = S.fav.has(String(fav.dataset.fav));
        fav.textContent = on ? '♥ В избранном' : '♡ В избранное';
        fav.setAttribute('aria-pressed', on);
        return;
      }
      var open = e.target.closest('[data-open]');
      if (open) markViewed(open.dataset.open);
    });

    el.openSheet.addEventListener('click', openSheet);
    el.fabFilters.addEventListener('click', openSheet);
    el.closeSheet.addEventListener('click', closeSheet);
    el.scrim.addEventListener('click', closeSheet);
    el.applySheet.addEventListener('click', function () {
      closeSheet();
      toast('Показано ' + S.filtered.length + ' ' + plural(S.filtered.length, 'вакансия', 'вакансии', 'вакансий'), 'ok');
    });

    el.themeToggle.addEventListener('click', function () {
      var next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
      document.documentElement.dataset.theme = next;
      el.themeToggle.setAttribute('aria-pressed', next === 'light');
      var meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.content = next === 'light' ? '#F5F1E8' : '#0B1210';
      try { localStorage.setItem(LS.theme, next); } catch (e) {}
    });

    el.shareBtn.addEventListener('click', function () {
      writeUrl();
      var url = location.href;
      function done() { toast('Ссылка на эти фильтры скопирована', 'ok'); }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done, function () { fallbackCopy(url, done); });
      } else fallbackCopy(url, done);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closeDrawer(); closeSheet(); }
      if (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
        e.preventDefault(); el.q.focus(); el.q.select();
      }
    });

    window.addEventListener('scroll', function () {
      el.topbar.classList.toggle('is-stuck', window.scrollY > 8);
    }, { passive: true });

    if ('ResizeObserver' in window) {
      new ResizeObserver(function () {
        var h = el.filters.getBoundingClientRect().height;
        var bar = $('.controls__bar').getBoundingClientRect().height;
        var mobile = window.matchMedia('(max-width: 900px)').matches;
        document.documentElement.style.setProperty('--controls-h', Math.round(mobile ? bar + 26 : bar + h + 30) + 'px');
      }).observe(el.filters);
    }

    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', function (e) {
      try { if (localStorage.getItem(LS.theme)) return; } catch (err) {}
      document.documentElement.dataset.theme = e.matches ? 'light' : 'dark';
    });
  }

  function fallbackCopy(text, done) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); done(); } catch (e) { toast('Не удалось скопировать ссылку', 'info'); }
    document.body.removeChild(ta);
  }

  function watchSections() {
    if (!('IntersectionObserver' in window)) return;
    var links = $$('[data-nav]');
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        links.forEach(function (l) { l.classList.toggle('is-current', l.dataset.nav === en.target.id); });
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    ['vacancies', 'how'].forEach(function (id) { var n = document.getElementById(id); if (n) io.observe(n); });
  }

  /* ---------- загрузка ---------- */
  function loadData() {
    renderSkeletons(true);
    S.loading = true;
    var base = new URL('data/', document.baseURI).href;
    Promise.all([
      fetch(base + 'vacancies.json', { cache: 'no-cache' }).then(function (r) {
        if (!r.ok) throw new Error('vacancies ' + r.status); return r.json();
      }),
      fetch(base + 'meta.json', { cache: 'no-cache' }).then(function (r) {
        if (!r.ok) throw new Error('meta ' + r.status); return r.json();
      }).catch(function () { return {}; })
    ]).then(function (res) {
      var list = Array.isArray(res[0]) ? res[0] : (res[0].items || []);
      S.all = list.filter(function (v) { return v && v.id && v.title; }).map(function (v) {
        v.categories = v.categories || [v.category || 'other'];
        v.trust_score = Number(v.trust_score) || 0;
        return v;
      });
      S.meta = res[1] || {};
      S.loading = false;
      renderSkeletons(false);
      renderDistricts();
      renderMeta();
      render();
      watchSections();
      setInterval(refreshUpdated, 60000);
      if (!S.all.length) {
        el.resultsCount.textContent = 'Данные пусты — скрипт ещё не собрал вакансии';
      }
    }).catch(function (err) {
      S.loading = false; S.failed = true;
      renderSkeletons(false);
      el.grid.hidden = true;
      el.moreWrap.hidden = true;
      el.errorState.hidden = false;
      el.emptyState.hidden = true;
      el.resultsCount.textContent = 'Ошибка загрузки данных';
      if (window.console) console.error('Кама.Работа:', err);
    });
  }

  function init() {
    cacheDom();
    readUrl();
    renderAccordion();
    bind();
    syncControls();
    el.themeToggle.setAttribute('aria-pressed', document.documentElement.dataset.theme === 'light');
    el.topbar.classList.toggle('is-stuck', window.scrollY > 8);
    loadData();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();