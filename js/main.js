// Mobile menu
const navToggle = document.querySelector('.nav-toggle');
const navLinks = document.querySelector('.nav-links');
if (navToggle && navLinks) {
  navToggle.addEventListener('click', () => {
    const open = navLinks.classList.toggle('open');
    navToggle.setAttribute('aria-expanded', String(open));
    navToggle.textContent = open ? 'Close' : 'Menu';
  });
  navLinks.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
    navLinks.classList.remove('open');
    navToggle.setAttribute('aria-expanded', 'false');
    navToggle.textContent = 'Menu';
  }));
}

// Homepage tour tabs: show one kind of tour at a time; hide tabs with no tours.
const tabs = [...document.querySelectorAll('.tour-tabs [data-kind]')];
if (tabs.length) {
  const cards = [...document.querySelectorAll('.tours-scroll .tour-card')];
  const show = (kind) => {
    tabs.forEach(t => t.setAttribute('aria-pressed', String(t.dataset.kind === kind)));
    // At most six per kind here; "See all tours" leads to the full lists.
    let n = 0;
    cards.forEach(c => { c.hidden = c.dataset.kind !== kind || ++n > 6; });
    const scroller = document.querySelector('.tours-scroll');
    if (scroller) scroller.scrollLeft = 0;
  };
  tabs.forEach(t => {
    if (!cards.some(c => c.dataset.kind === t.dataset.kind)) t.hidden = true;
    t.addEventListener('click', () => show(t.dataset.kind));
  });
  document.querySelectorAll('[data-tour-tab]').forEach(a => a.addEventListener('click', () => {
    const t = tabs.find(x => x.dataset.kind === a.dataset.tourTab && !x.hidden);
    if (t) show(t.dataset.kind);
  }));
  const first = tabs.find(t => !t.hidden);
  if (first) show(first.dataset.kind);
  if (tabs.filter(t => !t.hidden).length < 2) document.querySelector('.tour-tabs').hidden = true;
}

// ── Booking forms ──
// Contact details come from js/config.js (generated per build); tolerate it missing.
const CFG = window.BCH || {};
const FORM_ENDPOINT = 'https://formsubmit.co/ajax/' + (CFG.email || '');
const WHATSAPP = 'https://wa.me/' + (CFG.waNumber || '') + '?text=';
const MAX_PAX = Number(CFG.maxPax) || 8;
const form = document.getElementById('contact-form');
const today = new Date().toISOString().slice(0, 10);
document.querySelectorAll('input[type="date"]').forEach(el => { el.min = today; });
// Empty date/time fields show "Add date" / "Add time" (CSS) instead of the
// browser's dd/mm/yyyy pattern; the native pickers stay.
function markEmpty(el) { el.classList.toggle('is-empty', !el.value); }
document.querySelectorAll('input[type="date"], input[type="time"]').forEach(el => {
  markEmpty(el);
  ['input', 'change', 'blur'].forEach(ev => el.addEventListener(ev, () => markEmpty(el)));
});
document.addEventListener('reset', (e) => setTimeout(() => e.target.querySelectorAll('input[type="date"], input[type="time"]').forEach(markEmpty)), true);

function setStatus(el, msg, cls) {
  el.textContent = msg;
  el.className = 'form-status' + (cls ? ' ' + cls : '');
}

// Labelled values from the enabled, visible fields of a form, in page order.
function collect(f) {
  const rows = [];
  f.querySelectorAll('[data-label]').forEach(el => {
    if (el.disabled || el.closest('[hidden]') || el.closest('fieldset:disabled')) return;
    let v = el.value.trim();
    if (!v) return;
    if (el.name === 'dial') return;
    if (el.name === 'phone') v = f.querySelector('[name="dial"]').value + ' ' + v;
    if (el.type === 'date') v = new Date(v + 'T00:00').toLocaleDateString('en-IE', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
    if ((el.name === 'children') && v === '0') return;
    rows.push([el.dataset.label, v]);
  });
  return rows;
}

function validate(f, statusEl) {
  let first = null;
  f.querySelectorAll('[required], [type="email"]').forEach(el => {
    const live = !el.disabled && !el.closest('[hidden]') && !el.closest('fieldset:disabled');
    const bad = live && !el.checkValidity();
    el.classList.toggle('invalid', bad);
    if (bad && !first) first = el;
  });
  if (first) {
    setStatus(statusEl, 'Please fill in the highlighted fields.', 'err');
    const det = first.closest('details');
    if (det) det.open = true;
    first.focus();
    return false;
  }
  return true;
}

async function sendEmail(f, statusEl, btn, subject, extra) {
  if (f.querySelector('[name="_honey"]').value) return;
  if (!validate(f, statusEl)) return;
  const label = btn.querySelector('.send-label');
  const original = label.textContent;
  btn.disabled = true;
  label.textContent = 'Sending…';
  setStatus(statusEl, '');
  try {
    const body = Object.fromEntries([...(extra || []), ...collect(f)]);
    Object.assign(body, { _subject: subject(), _template: 'table', _captcha: 'false' });
    const res = await fetch(FORM_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body)
    });
    const out = await res.json().catch(() => ({}));
    if (!res.ok || String(out.success) !== 'true') throw new Error(out.message || 'Request failed');
    f.reset();
    f.querySelectorAll('.stepper').forEach(syncStepper);
    setStatus(statusEl, "Thanks! Your request has been sent. We'll be in touch shortly.", 'ok');
    return true;
  } catch (err) {
    setStatus(statusEl, "Sorry, that didn't send. Please " + (CFG.phoneDisplay ? 'call ' + CFG.phoneDisplay : 'call us') + ' or use WhatsApp.', 'err');
  } finally {
    btn.disabled = false;
    label.textContent = original;
  }
}

function sendWhatsApp(f, statusEl, intro, extra) {
  if (!validate(f, statusEl)) return;
  const lines = [intro, ...[...(extra || []), ...collect(f)].map(([k, v]) => k + ': ' + v)];
  setStatus(statusEl, '');
  window.open(WHATSAPP + encodeURIComponent(lines.join('\n')), '_blank', 'noopener');
}

// Steppers. Passenger counters (adults/children/passengers) share the van's seats (CFG.maxPax).
const PAX_FIELDS = ['adults', 'children', 'passengers'];
function syncStepper(stepper) {
  const f = stepper.closest('form');
  const pax = [...f.querySelectorAll('.stepper input')].filter(el => PAX_FIELDS.includes(el.name));
  const total = pax.reduce((n, el) => n + Number(el.value), 0);
  f.querySelectorAll('.stepper').forEach(st => {
    const input = st.querySelector('input');
    const isPax = PAX_FIELDS.includes(input.name);
    st.querySelector('[data-step="-1"]').disabled = Number(input.value) <= Number(input.min);
    st.querySelector('[data-step="1"]').disabled =
      Number(input.value) >= Number(input.max) || (isPax && total >= MAX_PAX);
  });
  // Full van: point larger groups to extra vehicles.
  f.querySelectorAll('.pax-more').forEach(el => { el.hidden = total < MAX_PAX; });
  f.dispatchEvent(new Event('paxchange'));
}

document.querySelectorAll('.stepper').forEach(st => {
  st.querySelectorAll('[data-step]').forEach(b => b.addEventListener('click', () => {
    const input = st.querySelector('input');
    input.value = Math.min(Number(input.max), Math.max(Number(input.min), Number(input.value) + Number(b.dataset.step)));
    syncStepper(st);
  }));
  syncStepper(st);
});

document.querySelectorAll('[required], [type="email"]').forEach(el => el.addEventListener('input', () => el.classList.remove('invalid')));

const euro = n => '€' + Number(n).toLocaleString('en-IE');

if (form) {
  // Homepage booking card: step 1 (trip) -> step 2 (instant price + contact).
  const statusEl = document.getElementById('cf-status');
  const sendBtn = document.getElementById('cf-send');
  const step1 = form.querySelector('.step-1');
  const tourSel = document.getElementById('cf-tour');
  const areaSel = document.getElementById('cf-area');
  const TOUR_SERVICE = { day: 'Day tour', pub: 'Rural pub tour', golf: 'Golf trip' };
  const vehicleSel = document.getElementById('cf-vehicle');
  const vehicleHint = document.getElementById('cf-vehicle-hint');
  const vehicleOpt = () => (vehicleSel && vehicleSel.value ? vehicleSel.selectedOptions[0] : null);
  // The fixed prices are for the van (data-fixed); other vehicles are quoted by us.
  const otherVehicle = () => { const o = vehicleOpt(); return o && !o.dataset.fixed ? o : null; };
  const mode = () => form.dataset.mode;
  const tourOpt = () => tourSel.selectedOptions[0];

  function syncCard() {
    const tours = mode() === 'tours';
    form.querySelectorAll('.card-tabs [data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === mode())));
    form.querySelectorAll('.only-taxi').forEach(el => { el.hidden = tours; });
    form.querySelectorAll('.only-tours').forEach(el => { el.hidden = !tours; });
    form.querySelectorAll('.only-airport').forEach(el => { el.hidden = tours || form.service.value !== 'Airport transfer'; });
    if (tours && tourOpt()) form.service.value = TOUR_SERVICE[tourOpt().dataset.kind] || 'Day tour';
    // Instant price hint in step 1 (the full quote opens in step 2).
    const q = quote(), hint = document.getElementById('cf-hint');
    hint.textContent = q.price ? q.price + (q.short ? ' ' + q.short : '') : (otherVehicle() ? q.note : '');
    hint.hidden = !hint.textContent;
    // More people than the chosen vehicle takes.
    const v = vehicleOpt(), pax = Number(form.passengers.value);
    if (vehicleHint) {
      vehicleHint.textContent = v && pax > Number(v.dataset.pax)
        ? 'This vehicle takes up to ' + v.dataset.pax + ", so we'll suggest a bigger one or a second vehicle." : '';
      vehicleHint.hidden = !vehicleHint.textContent;
    }
  }
  function setMode(m) { form.dataset.mode = m; syncCard(); }
  function setStep(n) {
    form.dataset.cardStep = String(n);
    setStatus(statusEl, '');
  }
  form.querySelectorAll('.card-tabs [data-mode]').forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));
  // No published tours: drop the Tours tab rather than offer an empty picker.
  if (!tourSel.options.length) form.querySelector('.card-tabs').hidden = true;
  form.service.addEventListener('change', syncCard);
  tourSel.addEventListener('change', syncCard);
  areaSel.addEventListener('change', syncCard);
  if (vehicleSel) vehicleSel.addEventListener('change', syncCard);
  form.addEventListener('paxchange', syncCard);
  form.pickup.addEventListener('input', syncCard);
  form.destination.addEventListener('input', syncCard);

  // The instant price shown at the top of step 2.
  function quote() {
    const q = fareQuote(), o = otherVehicle();
    return o ? { title: q.title + ', ' + o.textContent, price: '', note: "We'll confirm the price for this vehicle." } : q;
  }
  function fareQuote() {
    if (mode() === 'tours') {
      const o = tourOpt();
      if (!o) return { title: 'Your tour', price: '', note: "We'll confirm a fixed price within the hour." };
      return o.dataset.price
        ? { title: o.value, price: euro(o.dataset.price), short: o.dataset.unit, note: 'Fixed price ' + o.dataset.unit + ', up to ' + MAX_PAX + ' people.' }
        : { title: o.value, price: 'Price on request', note: "We'll confirm a fixed price within the hour." };
    }
    const a = areaSel.selectedOptions[0];
    if (form.service.value === 'Airport transfer' && a && a.dataset.to) {
      const to = /airport/i.test(form.destination.value), from = !to && /airport/i.test(form.pickup.value);
      const title = 'Dublin Airport ⇄ ' + a.value;
      if (to) return { title, price: euro(a.dataset.to), short: 'to the airport', note: 'Fixed price to the airport, for the whole vehicle.' };
      if (from) return { title, price: euro(a.dataset.from), short: 'from the airport', note: 'Fixed price from the airport, for the whole vehicle.' };
      return a.dataset.to === a.dataset.from
        ? { title, price: euro(a.dataset.to), short: 'each way', note: 'Fixed price each way, for the whole vehicle.' }
        : { title, price: euro(a.dataset.to) + ' or ' + euro(a.dataset.from), short: 'to or from the airport', note: euro(a.dataset.to) + ' to the airport, ' + euro(a.dataset.from) + ' from it. For the whole vehicle.' };
    }
    return { title: form.service.value, price: '', note: "We'll confirm a fixed price within the hour." };
  }
  const quoteText = () => { const q = quote(); return q.price ? q.price + ' (' + q.title + ')' : 'To be confirmed'; };
  const extra = () => [
    ...(mode() === 'tours' ? [['Service', form.service.value]] : []),
    ...(vehicleOpt() ? [['Vehicle', vehicleOpt().textContent]] : []),
    ['Quoted price', quoteText()],
  ];

  function stepOneValid() {
    let first = null;
    step1.querySelectorAll('[required]').forEach(el => {
      const bad = !el.closest('[hidden]') && !el.checkValidity();
      el.classList.toggle('invalid', bad);
      if (bad && !first) first = el;
    });
    if (first) {
      first.focus();
      return false;
    }
    return true;
  }
  function goNext() {
    if (!stepOneValid()) return;
    const q = quote();
    document.getElementById('cf-quote-title').textContent = q.title;
    document.getElementById('cf-quote-price').textContent = q.price;
    document.getElementById('cf-quote-price').hidden = !q.price;
    document.getElementById('cf-quote-note').textContent = q.note;
    setStep(2);
    document.getElementById('cf-quote').focus({ preventScroll: true });
    if (form.getBoundingClientRect().top < 0) form.scrollIntoView({ block: 'start' });
  }
  document.getElementById('cf-next').addEventListener('click', goNext);
  document.getElementById('cf-back').addEventListener('click', () => { setStep(1); document.getElementById('cf-next').focus(); });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (form.dataset.cardStep === '1') { goNext(); return; }
    const sent = await sendEmail(form, statusEl, sendBtn,
      () => `New ${form.service.value.toLowerCase()} booking from ${form.elements.name.value.trim()}`, extra());
    if (sent) syncCard();
  });
  document.getElementById('cf-wa').addEventListener('click', () => {
    sendWhatsApp(form, statusEl, "Hi BCH Taxi, I'd like to book: " + form.service.value, extra());
  });

  // Buttons elsewhere on the page pick a service and jump to the card.
  function pickService(service) {
    const kind = Object.keys(TOUR_SERVICE).find(k => TOUR_SERVICE[k] === service);
    const opt = kind && [...tourSel.options].find(o => o.dataset.kind === kind);
    if (opt) { tourSel.value = opt.value; setMode('tours'); }
    else { setMode('taxi'); form.service.value = service; syncCard(); }
    setStep(1);
  }
  document.querySelectorAll('[data-service]').forEach(btn => {
    btn.addEventListener('click', () => {
      pickService(btn.dataset.service);
      form.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
      setTimeout(() => document.getElementById('cf-date').focus({ preventScroll: true }), 500);
    });
  });

  // Prefill from links on other pages, e.g. index.html?service=School%20transport#booking
  const wanted = new URLSearchParams(location.search).get('service');
  const wantedVehicle = new URLSearchParams(location.search).get('vehicle');
  if (vehicleSel && wantedVehicle && [...vehicleSel.options].some(o => o.value === wantedVehicle)) vehicleSel.value = wantedVehicle;
  if (wanted && [...form.service.options].some(o => o.value === wanted)) pickService(wanted);
  else syncCard();
  // From the business quote bar and the "Book now" cards on other pages.
  const params = new URLSearchParams(location.search);
  if (params.get('date')) form.date.value = params.get('date');
  if (params.get('pickup')) form.pickup.value = params.get('pickup');
  if (params.get('destination')) form.destination.value = params.get('destination');
  if (params.get('topic')) form.message.value = 'About: ' + params.get('topic');
  if (params.get('date') || params.get('pickup') || params.get('destination')) syncCard();
  form.querySelectorAll('input[type="date"], input[type="time"]').forEach(markEmpty);
}

// Business and partner enquiry forms: sent like the booking forms, to the same inbox.
document.querySelectorAll('form.enquiry').forEach(f => {
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    sendEmail(f, f.querySelector('.form-status'), f.querySelector('[type="submit"]'),
      () => f.dataset.subject + ' ' + f.elements[f.dataset.subjectField].value.trim(),
      [['Enquiry', f.dataset.enquiry]]);
  });
});

// Tour modal (on every page that has tour "Book" buttons)
const modal = document.getElementById('tour-modal');
if (modal) {
  const tourForm = document.getElementById('tour-form');
  const tmStatus = document.getElementById('tm-status');
  let currentTour = null;

  function priceText(tour) {
    return tour.price === null ? 'Price on request' : euro(tour.price);
  }

  function updateSummary() {
    if (!currentTour) return;
    const pax = Number(tourForm.adults.value) + Number(tourForm.children.value);
    document.getElementById('tm-sub').textContent = `${currentTour.name}, ${priceText(currentTour)}${currentTour.price === null ? '' : ' ' + currentTour.unit}`;
    document.getElementById('tm-sum-tour').textContent = currentTour.name;
    document.getElementById('tm-sum-pax').textContent = pax;
    document.getElementById('tm-sum-total').textContent = priceText(currentTour);
    document.getElementById('tm-sum-label').textContent = currentTour.price === null ? 'Total' : `Total (${currentTour.unit})`;
  }
  tourForm.addEventListener('paxchange', updateSummary);

  document.querySelectorAll('.tour-book').forEach(btn => {
    btn.addEventListener('click', () => {
      currentTour = { name: btn.dataset.tour, price: btn.dataset.price === '' ? null : Number(btn.dataset.price), unit: btn.dataset.unit || 'per vehicle' };
      setStatus(tmStatus, '');
      tourForm.querySelectorAll('.invalid').forEach(el => el.classList.remove('invalid'));
      updateSummary();
      modal.showModal();
      document.body.classList.add('modal-open');
      setTimeout(() => document.getElementById('tm-name').focus(), 50);
    });
  });

  modal.addEventListener('close', () => document.body.classList.remove('modal-open'));
  modal.querySelector('[data-close]').addEventListener('click', () => modal.close());
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.close(); });

  const tourExtra = () => [['Tour', currentTour.name], ['Price', currentTour.price === null ? 'Price on request' : euro(currentTour.price) + ' ' + currentTour.unit]];
  tourForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ok = await sendEmail(tourForm, tmStatus, document.getElementById('tm-send'),
      () => `New tour booking: ${currentTour.name} from ${tourForm.name.value.trim()}`, tourExtra());
    if (ok) updateSummary();
  });
  document.getElementById('tm-wa').addEventListener('click', () => {
    sendWhatsApp(tourForm, tmStatus, "Hi BCH Taxi, I'd like to book the " + currentTour.name + ' tour.', tourExtra());
  });
}

// On the homepage the booking card has its own WhatsApp button, so the floating
// shortcut stays out of the way until the card has scrolled off screen.
const fab = document.querySelector('.whatsapp-fab');
if (fab && form && 'IntersectionObserver' in window) {
  new IntersectionObserver(([entry]) => {
    fab.classList.toggle('is-hidden', entry.isIntersecting);
  }).observe(form);
}
