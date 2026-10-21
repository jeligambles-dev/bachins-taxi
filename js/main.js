// Scroll reveal
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

// Nav scroll effect
window.addEventListener('scroll', () => {
  document.querySelector('nav').classList.toggle('scrolled', window.scrollY > 50);
});

// Close mobile menu on link click
document.querySelectorAll('.nav-links a').forEach(link => {
  link.addEventListener('click', () => {
    document.querySelector('.nav-links').classList.remove('open');
  });
});

// ── Booking forms ──
const FORM_ENDPOINT = 'https://formsubmit.co/ajax/bachintaxi@gmail.com';
const WHATSAPP = 'https://wa.me/353870330046?text=';
const MAX_PAX = 8;
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
  f.querySelectorAll('[required]').forEach(el => {
    const live = !el.disabled && !el.closest('[hidden]') && !el.closest('fieldset:disabled');
    const bad = live && !el.checkValidity();
    el.classList.toggle('invalid', bad);
    if (bad && !first) first = el;
  });
  if (first) {
    setStatus(statusEl, 'Please fill in the highlighted fields.', 'err');
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
    setStatus(statusEl, "Sorry, that didn't send. Please call +353 87 033 0046 or use WhatsApp.", 'err');
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

// Steppers. Passenger counters (adults/children/passengers) share the van's 8 seats.
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

document.querySelectorAll('[required]').forEach(el => el.addEventListener('input', () => el.classList.remove('invalid')));

if (form) {
  // Main form: reason cards switch which panel is shown.
  const statusEl = document.getElementById('cf-status');
  const sendBtn = document.getElementById('cf-send');
  const SEND_LABELS = { Booking: 'Send Booking Request', Enquiry: 'Send Enquiry', Support: 'Submit Support Request', Other: 'Send Message' };
  const reason = () => form.querySelector('[name="reason"]:checked').value;

  function showReason() {
    const r = reason();
    form.querySelectorAll('.panel').forEach(p => {
      const on = p.dataset.reason === r;
      p.hidden = !on;
      p.disabled = !on;
    });
    sendBtn.querySelector('.send-label').textContent = SEND_LABELS[r];
    setStatus(statusEl, '');
  }
  form.querySelectorAll('[name="reason"]').forEach(r => r.addEventListener('change', showReason));

  function setReason(r) {
    form.querySelector(`[name="reason"][value="${r}"]`).checked = true;
    showReason();
  }

  const fullName = () => (form.first.value + ' ' + form.last.value).trim();
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    sendEmail(form, statusEl, sendBtn,
      () => reason() === 'Booking' ? `New ${form.service.value.toLowerCase()} booking from ${fullName()}` : `New ${reason().toLowerCase()} from ${fullName()}`,
      [['Reason', reason()]]);
  });
  document.getElementById('cf-wa').addEventListener('click', () => {
    const intro = reason() === 'Booking' ? "Hi BCH Taxi, I'd like to book: " + form.service.value : 'Hi BCH Taxi, ' + reason().toLowerCase() + ':';
    sendWhatsApp(form, statusEl, intro);
  });

  function goToForm(fill) {
    setReason('Booking');
    fill();
    form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(() => document.getElementById('cf-first').focus({ preventScroll: true }), 600);
  }

  document.getElementById('quick-book')?.addEventListener('submit', (e) => {
    e.preventDefault();
    goToForm(() => {
      form.service.value = document.getElementById('qb-service').value;
      form.pickup.value = document.getElementById('qb-pickup').value;
      form.destination.value = document.getElementById('qb-dropoff').value;
    });
  });

  document.querySelectorAll('[data-service]').forEach(btn => {
    btn.addEventListener('click', () => goToForm(() => { form.service.value = btn.dataset.service; }));
  });

    // Prefill from links on other pages, e.g. index.html?service=School%20transport#booking
    const wanted = new URLSearchParams(location.search).get('service');
    if (wanted && [...form.service.options].some(o => o.value === wanted)) {
      form.service.value = wanted;
    }

}

// Tour modal (on every page that has tour "Book" buttons)
const modal = document.getElementById('tour-modal');
if (modal) {
  const tourForm = document.getElementById('tour-form');
  const tmStatus = document.getElementById('tm-status');
  let currentTour = null;

  function priceText(tour) {
    return tour.price === null ? 'Price on request' : '€' + tour.price;
  }

  function updateSummary() {
    if (!currentTour) return;
    const pax = Number(tourForm.adults.value) + Number(tourForm.children.value);
    document.getElementById('tm-sub').textContent = `${currentTour.name} · ${priceText(currentTour)} · ${pax} ${pax === 1 ? 'guest' : 'guests'}`;
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

  const tourExtra = () => [['Tour', currentTour.name], ['Price', currentTour.price === null ? 'Price on request' : '€' + currentTour.price + ' ' + currentTour.unit]];
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
