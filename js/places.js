// Live address search for From / To fields (OpenStreetMap Photon, no key).
// Any <input data-places> becomes an ARIA combobox. Picking a suggestion fills
// the input and hidden <name>_lat/_lon/_city/_district/_county/_postcode/_type
// fields; typing freely still works and never blocks a submit.
(function () {
  const ENDPOINT = 'https://photon.komoot.io/api/';
  const BBOX = '-10.8,51.3,-5.3,55.5';           // the island of Ireland
  const MIN_CHARS = 3, DEBOUNCE_MS = 300, TIMEOUT_MS = 4000;
  const EXTRA = ['lat', 'lon', 'city', 'district', 'county', 'postcode', 'type'];
  const cache = new Map();
  const PINNED = [
    { label: 'Dublin Airport, Terminal 1', main: 'Dublin Airport, Terminal 1', sub: 'Collinstown, County Dublin, K67', lat: 53.4273, lon: -6.2440, city: 'Dublin Airport', county: 'County Dublin', postcode: 'K67', type: 'other' },
    { label: 'Dublin Airport, Terminal 2', main: 'Dublin Airport, Terminal 2', sub: 'Collinstown, County Dublin, K67', lat: 53.4268, lon: -6.2393, city: 'Dublin Airport', county: 'County Dublin', postcode: 'K67', type: 'other' },
  ];
  const wantsAirport = (q) => !q || /air|dub|termin/i.test(q);

  // "name, house-number street, district / locality / city, county, postcode"
  function toPlace(f) {
    const p = f.properties || {}, c = (f.geometry && f.geometry.coordinates) || [];
    const street = [p.housenumber, p.street].filter(Boolean).join(' ');
    const parts = [p.name, street, p.district, p.locality, p.city, p.county, p.postcode];
    const seen = new Set(), out = [];
    // Skip administrative noise such as "Airport ED" or "Lucan-St. Helens DED 1986".
    const noise = /\b(DED|ED)\b|\bParish \d{4}\b/;
    parts.forEach((x) => {
      const t = (x || '').trim();
      if (t && !noise.test(t) && !seen.has(t.toLowerCase())) { seen.add(t.toLowerCase()); out.push(t); }
    });
    return {
      label: out.join(', '), main: out[0] || '', sub: out.slice(1).join(', '),
      lat: c[1], lon: c[0], city: p.city || '', district: p.district || p.locality || '',
      county: p.county || '', postcode: p.postcode || '', type: p.type || '', name: p.name || '',
    };
  }

  async function search(q, signal) {
    const key = q.toLowerCase();
    if (cache.has(key)) return cache.get(key);
    const url = ENDPOINT + '?q=' + encodeURIComponent(q) + '&limit=6&lang=en&bbox=' + BBOX;
    const res = await fetch(url, { signal });
    if (!res.ok) throw new Error('Photon ' + res.status);
    const data = await res.json();
    const labels = new Set();
    const places = (data.features || []).map(toPlace)
      .filter((p) => p.label && !labels.has(p.label.toLowerCase()) && labels.add(p.label.toLowerCase()));
    cache.set(key, places);
    if (cache.size > 50) cache.delete(cache.keys().next().value);
    return places;
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
    pop.innerHTML = `<ul class="places-list" role="listbox" id="${id}" aria-label="Address suggestions"></ul>`
      + '<p class="places-attr">Address search © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a></p>';
    host.appendChild(pop);
    const list = pop.querySelector('ul');

    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', id);
    input.setAttribute('autocomplete', 'off');

    let items = [], active = -1, timer = null, ctrl = null;

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
        li.className = 'places-opt';
        const a = document.createElement('span'); a.className = 'places-main'; a.textContent = p.main || p.label;
        li.appendChild(a);
        if (p.sub) { const b = document.createElement('span'); b.className = 'places-sub'; b.textContent = p.sub; li.appendChild(b); }
        li.addEventListener('mousedown', (e) => e.preventDefault());   // keep focus in the input
        li.addEventListener('click', () => pick(i));
        list.appendChild(li);
      });
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
    function pick(i) {
      const p = items[i];
      if (!p) return;
      input.value = p.label;
      setHidden(p);
      close();
      input.classList.remove('invalid');
      input.dispatchEvent(new CustomEvent('placechange', { bubbles: true, detail: p }));
    }

    function update() {
      const q = input.value.trim();
      const pinned = wantsAirport(q) ? PINNED.filter((p) => !q || /air|dub|termin/i.test(q)) : [];
      if (ctrl) ctrl.abort();
      if (q.length < MIN_CHARS) { render(document.activeElement === input ? pinned : []); return; }
      render(pinned);
      ctrl = new AbortController();
      const mine = ctrl, timeout = setTimeout(() => mine.abort(), TIMEOUT_MS);
      search(q, mine.signal)
        .then((found) => {
          if (mine !== ctrl || input.value.trim() !== q) return;
          const seen = new Set(pinned.map((p) => p.label.toLowerCase()));
          render([...pinned, ...found.filter((p) => !seen.has(p.label.toLowerCase()))].slice(0, 8));
        })
        .catch(() => { if (mine === ctrl) close(); })        // fail quietly; typing still works
        .finally(() => clearTimeout(timeout));
    }

    input.addEventListener('input', () => {
      setHidden(null);                     // typed text no longer matches a picked place
      // Drop suggestions that no longer fit what is typed while the search waits.
      const q = input.value.trim();
      if (!pop.hidden) render(items.filter((p) => (p.lat === PINNED[0].lat || p.lat === PINNED[1].lat) ? wantsAirport(q)
        : p.label.toLowerCase().includes(q.toLowerCase().slice(0, 3))));
      clearTimeout(timer);
      timer = setTimeout(update, DEBOUNCE_MS);
    });
    input.addEventListener('focus', () => { if (!input.value.trim()) render(PINNED); });
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
    return { label: input.value.trim(), lat: get('lat'), lon: get('lon'), city: get('city'), district: get('district'),
             county: get('county'), postcode: get('postcode'), type: get('type'), name: get('lat') ? input.value.split(',')[0].trim() : '' };
  }
  function mapLink(input) {
    const p = placeOf(input);
    return p && p.lat && p.lon ? 'https://www.google.com/maps?q=' + p.lat + ',' + p.lon : '';
  }

  window.BCHPlaces = { attach, placeOf, mapLink, toPlace };
  document.querySelectorAll('input[data-places]').forEach(attach);
})();
