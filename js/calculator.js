// Price calculator. Prices come from build/data.py via the #calc-data JSON block.
(() => {
  const calc = document.getElementById('calc-form');
  if (!calc) return;

  const DATA = JSON.parse(document.getElementById('calc-data').textContent);
  const $ = (id) => document.getElementById(id);
  const tourSel = $('calc-tour');
  const multiSel = $('calc-multi');
  const daysWrap = calc.querySelector('.calc-days');
  const airSel = $('calc-air');
  const dirSel = $('calc-dir');
  const statusEl = $('calc-status');
  const eur = (n) => '€' + n.toLocaleString('en-IE');
  const DIR_LABEL = { to: 'to Dublin Airport', from: 'from Dublin Airport', both: 'to & from Dublin Airport' };

  // Line items for the current selection: [label, amount]
  function lines() {
    const out = [];
    const tour = DATA.tours.find(t => t.slug === tourSel.value);
    if (tour) out.push([tour.name + ' day tour', tour.price]);

    if (multiSel.value === 'custom') {
      const days = Number($('calc-days').value);
      out.push([`Custom multi-day tour, ${days} days × ${eur(DATA.dayRate)}`, days * DATA.dayRate]);
    } else if (multiSel.value) {
      const m = DATA.multi.find(x => x.slug === multiSel.value);
      out.push([`${m.name}, ${m.days} days × ${eur(DATA.dayRate)}`, m.days * DATA.dayRate]);
    }

    if (airSel.value !== '') {
      const a = DATA.airport[Number(airSel.value)];
      const dir = dirSel.value;
      const price = dir === 'to' ? a.to : dir === 'from' ? a.from : a.to + a.from;
      out.push([`Airport transfer, ${a.area} ${DIR_LABEL[dir]}`, price]);
    }

    const hours = Number($('calc-hours').value);
    if (hours) out.push([`Extra hours, ${hours} × ${eur(DATA.hourRate)}`, hours * DATA.hourRate]);
    return out;
  }

  function render() {
    daysWrap.hidden = multiSel.value !== 'custom';
    dirSel.hidden = airSel.value === '';
    const items = lines();
    const total = items.reduce((n, [, p]) => n + p, 0);
    const pax = Number($('calc-pax').value);
    const list = $('calc-lines');
    list.innerHTML = '';
    if (!items.length) {
      list.innerHTML = '<li class="calc-empty">Choose a tour, trip or transfer to see your price.</li>';
    }
    items.forEach(([label, price]) => {
      const li = document.createElement('li');
      li.innerHTML = '<span></span><strong></strong>';
      li.firstChild.textContent = label;
      li.lastChild.textContent = eur(price);
      list.appendChild(li);
    });
    $('calc-total').textContent = eur(total);
    $('calc-pp').textContent = total
      ? `${pax} ${pax === 1 ? 'passenger' : 'passengers'} · about ${eur(Math.round(total / pax))} per person`
      : '';
    return { items, total, pax };
  }

  calc.addEventListener('change', render);
  calc.addEventListener('paxchange', render);
  calc.addEventListener('reset', () => setTimeout(render));

  // Arriving from a tour page: ?tour=cliffs-of-moher
  const pre = new URLSearchParams(location.search).get('tour');
  if (pre && DATA.tours.some(t => t.slug === pre)) tourSel.value = pre;
  render();

  function quoteRows() {
    const { items, total, pax } = render();
    return [
      ...items.map(([label, price]) => [label, eur(price)]),
      ['Passengers', String(pax)],
      ['Estimated total', eur(total)],
    ];
  }

  function hasSelection() {
    if (render().items.length) return true;
    setStatus(statusEl, 'Choose at least one tour, trip or transfer first.', 'err');
    return false;
  }

  calc.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!hasSelection()) return;
    sendEmail(calc, statusEl, $('calc-send'),
      () => `Quote request (${eur(render().total)}) from ${calc.name.value.trim()}`, quoteRows());
  });

  $('calc-wa').addEventListener('click', () => {
    if (!hasSelection()) return;
    sendWhatsApp(calc, statusEl, "Hi BCH Taxi, I'd like a fixed quote for:", quoteRows());
  });
})();
