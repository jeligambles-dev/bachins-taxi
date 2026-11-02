// Live address search for From / To fields.
// Provider: our server's Google Places proxy (/api/places/*). If the server has
// no Google key (local preview) it answers 503 not_configured and we fall back
// to OpenStreetMap Photon for the rest of the visit. Any other failure (502,
// 429, timeout) just closes the list: typed text still submits.
// Any <input data-places> becomes an ARIA combobox. Picking a suggestion fills
// the input and hidden <name>_lat/_lon/_postcode/_locality/... fields.
(function () {
  const API = '/api/places/';
  const PHOTON = 'https://photon.komoot.io/api/';
  const BBOX = '-10.8,51.3,-5.3,55.5';           // the island of Ireland
  const MIN_CHARS = 3, DEBOUNCE_MS = 300, TIMEOUT_MS = 4000;
  const EXTRA = ['lat', 'lon', 'postcode', 'locality', 'sublocality', 'county', 'is_airport', 'city', 'district', 'type'];
  const cache = new Map();
  let provider = 'google';                        // 'google' or 'osm' (fallback)
  const PINNED = [
    { label: 'Dublin Airport, Terminal 1', main: 'Dublin Airport, Terminal 1', sub: 'Collinstown, Co. Dublin, K67', lat: 53.4273, lon: -6.2441, county: 'County Dublin', postcode: 'K67', is_airport: 'true', pinned: true },
    { label: 'Dublin Airport, Terminal 2', main: 'Dublin Airport, Terminal 2', sub: 'Collinstown, Co. Dublin, K67', lat: 53.4264, lon: -6.2390, county: 'County Dublin', postcode: 'K67', is_airport: 'true', pinned: true },
  ];
  const wantsAirport = (q) => !q || /air|dub|termin/i.test(q);
  const newSession = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '')
    : Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join(''));

  function withTimeout(signal) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    if (signal) signal.addEventListener('abort', () => ctrl.abort());
    return { signal: ctrl.signal, done: () => clearTimeout(t) };
  }

  // ── Google, through our server ──────────────────────────────────────────
  class Fallback extends Error {}
  async function googleSearch(q, session, signal) {
    const res = await fetch(API + 'autocomplete?q=' + encodeURIComponent(q) + '&session=' + session,
      { signal, headers: { Accept: 'application/json' }, credentials: 'same-origin' });
    if (res.status === 503) {
      const body = await res.json().catch(() => ({}));
      if (body.error === 'not_configured') { provider = 'osm'; throw new Fallback(); }
    }
    if (!res.ok) throw new Error('places ' + res.status);
    return (await res.json()).map((s) => ({
      id: s.id, main: s.main, sub: s.secondary, label: [s.main, s.secondary].filter(Boolean).join(', '), source: 'google',
    }));
  }
  async function googleDetails(id, session) {
    const t = withTimeout();
    try {
      const res = await fetch(API + 'details?id=' + encodeURIComponent(id) + '&session=' + session,
        { signal: t.signal, headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      if (!res.ok) throw new Error('details ' + res.status);
      const d = await res.json();
      return { label: d.label, lat: d.lat, lon: d.lon, postcode: d.postcode, locality: d.locality,
               sublocality: d.sublocality, county: d.county, is_airport: String(!!d.is_airport),
               type: (d.types || []).join(' ') };
    } finally { t.done(); }
  }

  // ── OpenStreetMap Photon (fallback) ─────────────────────────────────────
  // "name, house-number street, district / locality / city, county, postcode"
  function toPlace(f) {
    const p = f.properties || {}, c = (f.geometry && f.geometry.coordinates) || [];
    const street = [p.housenumber, p.street].filter(Boolean).join(' ');
    const parts = [p.name, street, p.district, p.locality, p.city, p.county, p.postcode];
    const seen = new Set(), out = [];
    const noise = /\b(DED|ED)\b|\bParish \d{4}\b/;   // "Airport ED", "Lucan-St. Helens DED 1986"
    parts.forEach((x) => {
      const t = (x || '').trim();
      if (t && !noise.test(t) && !seen.has(t.toLowerCase())) { seen.add(t.toLowerCase()); out.push(t); }
    });
    return {
      label: out.join(', '), main: out[0] || '', sub: out.slice(1).join(', '), source: 'osm',
      lat: c[1], lon: c[0], city: p.city || '', district: p.district || p.locality || '',
      county: p.county || '', postcode: p.postcode || '', type: p.type || '', name: p.name || '',
    };
  }
  async function osmSearch(q, signal) {
    const res = await fetch(PHOTON + '?q=' + encodeURIComponent(q) + '&limit=6&lang=en&bbox=' + BBOX, { signal });
    if (!res.ok) throw new Error('Photon ' + res.status);
    const data = await res.json();
    const labels = new Set();
    return (data.features || []).map(toPlace)
      .filter((p) => p.label && !labels.has(p.label.toLowerCase()) && labels.add(p.label.toLowerCase()));
  }

  async function search(q, session, signal) {
    const key = provider + ':' + q.toLowerCase();
    if (cache.has(key)) return cache.get(key);
    let found;
    if (provider === 'google') {
      try { found = await googleSearch(q, session, signal); }
      catch (e) { if (!(e instanceof Fallback)) throw e; found = await osmSearch(q, signal); }
    } else {
      found = await osmSearch(q, signal);
    }
    cache.set(provider + ':' + q.toLowerCase(), found);
    if (cache.size > 60) cache.delete(cache.keys().next().value);
    return found;
  }

  let uid = 0;
  function attach(input) {
    const form = input.form, name = input.name, id = 'places-' + (++uid);
    const host = input.closest('.field-row') || input.closest('.quote-bar-fields') || input.closest('.field') || input.parentElement;
    if (getComputedStyle(host).position === 'static') host.style.position = 'relative';

    // Hidden structured fields, kept next to the input (and sent with GET forms).
    const hidden = {};
    EXTRA.forEach((k) => {
      let h = form && form.querySelector(`input[type="hidden"][name="${name}_${k}"]`);
      if (!h) {
        h = document.createElement('input');
        h.type = 'hidden'; h.name = name + '_' + k;
        input.insertAdjacentElement('afterend', h);
      }
      hidden[k] = h;
    });

    // GET forms (the business quote bar): don't send empty place fields.
    if (form && form.method === 'get' && !form.dataset.placesTidy) {
      form.dataset.placesTidy = '1';
      form.addEventListener('submit', () => form.querySelectorAll('input[type="hidden"]').forEach((h) => { if (!h.value) h.disabled = true; }));
    }

    const pop = document.createElement('div');
    pop.className = 'places-pop';
    pop.hidden = true;
    pop.innerHTML = `<ul class="places-list" role="listbox" id="${id}" aria-label="Address suggestions"></ul><p class="places-attr"></p>`;
    host.appendChild(pop);
    const list = pop.querySelector('ul'), attr = pop.querySelector('.places-attr');

    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', id);
    input.setAttribute('autocomplete', 'off');

    let items = [], active = -1, timer = null, ctrl = null;
    let session = '';                                   // Google billing session for this field

    function setHidden(p) { EXTRA.forEach((k) => { hidden[k].value = p && p[k] !== undefined && p[k] !== null ? p[k] : ''; }); }
    function close() {
      pop.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant');
      active = -1;
    }
    function render(list_) {
      items = list_;
      active = -1;
      // Only ever open under the field the visitor is in (a late search result
      // must not pop up after they have moved on).
      if (!items.length || document.activeElement !== input) { close(); return; }
      list.innerHTML = '';
      items.forEach((p, i) => {
        const li = document.createElement('li');
        li.id = id + '-' + i; li.setAttribute('role', 'option'); li.setAttribute('aria-selected', 'false');
        li.className = 'places-opt' + (p.pinned ? ' is-pinned' : '');
        const a = document.createElement('span'); a.className = 'places-main'; a.textContent = p.main || p.label;
        li.appendChild(a);
        if (p.sub) { const b = document.createElement('span'); b.className = 'places-sub'; b.textContent = p.sub; li.appendChild(b); }
        li.addEventListener('mousedown', (e) => e.preventDefault());   // keep focus in the input
        li.addEventListener('click', () => pick(i));
        list.appendChild(li);
      });
      const google = items.some((p) => p.source === 'google') || (provider === 'google' && items.every((p) => p.pinned));
      attr.innerHTML = google ? 'Powered by Google'
        : 'Address search © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';
      attr.classList.toggle('is-google', google);
      pop.hidden = false; input.setAttribute('aria-expanded', 'true');
    }
    function highlight(i) {
      const opts = list.querySelectorAll('[role="option"]');
      if (!opts.length) return;
      active = (i + opts.length) % opts.length;
      opts.forEach((o, n) => o.setAttribute('aria-selected', String(n === active)));
      input.setAttribute('aria-activedescendant', opts[active].id);
      opts[active].scrollIntoView({ block: 'nearest' });
    }
    function done(p) {
      input.classList.remove('invalid');
      input.dispatchEvent(new CustomEvent('placechange', { bubbles: true, detail: p }));
    }
    async function pick(i) {
      const p = items[i];
      if (!p) return;
      input.value = p.label;
      setHidden(p.source === 'google' ? null : p);
      close();
      if (p.source === 'google' && p.id) {
        const s = session;
        session = '';                                   // the pick ends this billing session
        try {
          const d = await googleDetails(p.id, s);
          if (input.value === p.label) { input.value = d.label || p.label; setHidden(d); }
        } catch (e) { /* keep the typed label; no pin */ }
      }
      done(p);
    }

    function update() {
      const q = input.value.trim();
      const pinned = wantsAirport(q) ? PINNED : [];
      if (ctrl) ctrl.abort();
      if (q.length < MIN_CHARS) { render(document.activeElement === input ? pinned : []); return; }
      render(pinned);
      if (!session) session = newSession();
      ctrl = new AbortController();
      const mine = ctrl, t = withTimeout(mine.signal);
      search(q, session, t.signal)
        .then((found) => {
          if (mine !== ctrl || input.value.trim() !== q) return;
          const seen = new Set(pinned.map((p) => p.label.toLowerCase()));
          render([...pinned, ...found.filter((p) => !seen.has(p.label.toLowerCase()))].slice(0, 8));
        })
        .catch(() => { if (mine === ctrl) close(); })        // fail quietly; typing still works
        .finally(() => t.done());
    }

    input.addEventListener('input', () => {
      setHidden(null);                     // typed text no longer matches a picked place
      // Drop suggestions that no longer fit what is typed while the search waits.
      const q = input.value.trim();
      if (!pop.hidden) render(items.filter((p) => (p.pinned ? wantsAirport(q)
        : p.label.toLowerCase().includes(q.toLowerCase().slice(0, 3)))));
      clearTimeout(timer);
      timer = setTimeout(update, DEBOUNCE_MS);
    });
    input.addEventListener('focus', () => {
      if (!session) session = newSession();
      if (!input.value.trim()) render(PINNED);
    });
    input.addEventListener('blur', () => setTimeout(close, 120));
    input.addEventListener('keydown', (e) => {
      const open = !pop.hidden;
      if (e.key === 'ArrowDown') { e.preventDefault(); if (!open) update(); else highlight(active + 1); }
      else if (e.key === 'ArrowUp' && open) { e.preventDefault(); highlight(active - 1); }
      else if (e.key === 'Enter' && open && active >= 0) { e.preventDefault(); pick(active); }
      else if (e.key === 'Escape' && open) { e.preventDefault(); close(); }
    });
  }

  // The place stored for an input: picked structure if any, else just the typed label.
  function placeOf(input) {
    if (!input) return null;
    const f = input.form, n = input.name, get = (k) => (f && f.querySelector(`input[type="hidden"][name="${n}_${k}"]`) || {}).value || '';
    const p = { label: input.value.trim() };
    EXTRA.forEach((k) => { p[k] = get(k); });
    p.name = p.lat && p.type && !/\b(house|street|route|premise|street_address)\b/.test(p.type) ? input.value.split(',')[0].trim() : '';
    return p;
  }
  function mapLink(input) {
    const p = placeOf(input);
    return p && p.lat && p.lon ? 'https://www.google.com/maps?q=' + p.lat + ',' + p.lon : '';
  }

  window.BCHPlaces = { attach, placeOf, mapLink, toPlace, provider: () => provider };
  document.querySelectorAll('input[data-places]').forEach(attach);
})();
