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
    tabs.forEach(t => t.setAttribute('aria-selected', String(t.dataset.kind === kind)));
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

if (form) {
  // Homepage booking card.
  const statusEl = document.getElementById('cf-status');
  const sendBtn = document.getElementById('cf-send');

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    sendEmail(form, statusEl, sendBtn,
      () => `New ${form.service.value.toLowerCase()} booking from ${form.elements.name.value.trim()}`);
  });
  document.getElementById('cf-wa').addEventListener('click', () => {
    sendWhatsApp(form, statusEl, "Hi BCH Taxi, I'd like to book: " + form.service.value);
  });

  // "Ask us" buttons elsewhere on the page pick a service and jump to the card.
  document.querySelectorAll('[data-service]').forEach(btn => {
    btn.addEventListener('click', () => {
      form.service.value = btn.dataset.service;
      form.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
      setTimeout(() => document.getElementById('cf-pickup').focus({ preventScroll: true }), 500);
    });
  });

  // Prefill from links on other pages, e.g. index.html?service=School%20transport#booking
  const wanted = new URLSearchParams(location.search).get('service');
  if (wanted && [...form.service.options].some(o => o.value === wanted)) {
    form.service.value = wanted;
  }
}

const euro = n => '€' + Number(n).toLocaleString('en-IE');

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
