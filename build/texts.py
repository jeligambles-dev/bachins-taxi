"""Editable page text.

Two sources feed the owner admin:

* TEXTS: copy that lives in build.py, as key -> (group, label, default).
  Defaults are plain text ("&", not "&amp;"); T() escapes on output.
* Template markers in build/templates/index.html:
  <!-- @t:home.hero_title -->default<!-- /@t:home.hero_title -->

Owner overrides arrive as a {key: value} dict via configure(). Values are
always HTML-escaped on output. Computed values (rates, counts) and markup such
as links stay in build.py; only the plain-text parts around them are keys.
"""
import html
import re
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "index.html"
MARKER_RE = re.compile(r"<!-- @t:([\w.]+) -->(.*?)<!-- /@t:\1 -->", re.S)

_overrides = {}
_max_pax = 8
_template_cache = {}

# Built-in wording that states the passenger limit as a bare "8". The admin
# still shows the original default; the build swaps in the real limit. Owner
# overrides are never touched. ("8-seater" and "Up to 8 seats" describe the
# vehicle and stay as they are.)
_PAX_PHRASES = (
    (re.compile(r"\b(up to|more than) 8\b(?! seat)", re.I), lambda m, n: f"{m.group(1)} {n}"),
    (re.compile(r"\bpassenger or 8\b"), lambda m, n: f"passenger or {n}"),
    (re.compile(r'\bmax="8"'), lambda m, n: f'max="{n}"'),
    (re.compile(r"\(9(\+|%2B)\)"), lambda m, n: f"({n + 1}{m.group(1)})"),
)

TEXTS = {
    # ── Call-to-action band (bottom of most pages) ───────────────────────────
    "cta.title": ("Call-to-action band", "Heading", "Ready to book?"),
    "cta.text": ("Call-to-action band", "Text",
                 "Send us your dates and we'll confirm availability and a fixed price, usually within the hour."),

    # ── Large groups band ────────────────────────────────────────────────────
    "group.title_rest": ("Large groups (home page)", "Heading (follows \"More than N\", where N is your passenger limit)",
                         "passengers"),
    "group.text": ("Large groups (home page)", "Paragraph",
                   "Weddings, teams and big families. We add extra vans, minibuses or coaches so everyone travels together, with one booking and one contact."),

    # ── What's included / Good to know, per tour type ────────────────────────
    "included.day": ("Day tours: included", "What's included (one item per line)",
                     "Private vehicle for your group only\nUp to 8 passengers, one price for the vehicle\nBigger group? We can arrange extra vehicles\nPickup and drop-off anywhere in Dublin or Meath\nWheelchair-accessible van with ramp\nFlexible stops and pace on the day"),
    "included.pub": ("Pub tours: included", "What's included (one item per line)",
                     "Private vehicle for your group only\nYour driver gets everyone home safely, so no designated driver needed\nUp to 8 passengers, one price for the vehicle\nPickup and drop-off anywhere in Dublin or Meath\nYour driver waits at each pub while you enjoy yourselves\nFlexible stops and pace on the day"),
    "included.golf": ("Golf trips: included", "What's included (one item per line)",
                      "Private vehicle for your group only\nRoom for clubs and bags for the whole group\nOne fixed price for the whole trip\nPickup and drop-off anywhere in Dublin or Meath\nYour driver waits at the course or returns for pickup\nFlexible timings around your tee times"),
    "good_to_know.day": ("Day tours: included", "Good to know",
                         "Every tour is private and fully flexible. Tell us where you're staying and anything you'd love to see, and we'll shape the day around you. Admission tickets for attractions are not included in the tour price."),
    "good_to_know.pub": ("Pub tours: included", "Good to know",
                         "Every pub tour is private and fully flexible. Your driver gets everyone home safely, so nobody has to stay sober behind the wheel. Tell us what you like to drink and how long you want at each stop, and we'll shape the day around you. Food and drinks are not included in the price."),
    "good_to_know.golf": ("Golf trips: included", "Good to know",
                          "Room for clubs and bags is built in, and every golf trip is private and flexible. Your driver can wait at the course or return for pickup, whichever suits your group. Green fees, caddies and food are not included in the price."),

    # ── Individual tour pages ────────────────────────────────────────────────
    "tour.about_title": ("Tour pages", "\"About this tour\" heading", "About this tour"),
    "tour.highlights_title": ("Tour pages", "\"Highlights\" heading", "Highlights"),
    "tour.included_title": ("Tour pages", "\"What's included\" heading", "What's included"),
    "tour.good_title": ("Tour pages", "\"Good to know\" heading", "Good to know"),
    "tour.more_title": ("Tour pages", "\"More tours\" heading", "You might also like"),

    # ── Footer ───────────────────────────────────────────────────────────────
    "footer.about": ("Footer", "About paragraph",
                     "Taxis, Dublin Airport transfers and private tours of Ireland in our wheelchair-accessible 8-seater. Available 24/7."),
    "footer.tagline": ("Footer", "Bottom line", "Wheelchair-accessible 8-seater. Dublin, Meath and all of Ireland."),

    # ── Tours page ───────────────────────────────────────────────────────────
    "tours.title": ("Tours page", "Main heading", "Private tours of Ireland"),
    "tours.lead": ("Tours page", "Intro paragraph (follows the number of tours, e.g. \"Ten full-day private tours\")",
                   "from Dublin and Meath in our 8-seater. One price covers the whole vehicle, so the more of you there are, the better the value."),
    "tours.multi_title": ("Tours page", "Multi-day promo: heading", "Multi-day tours"),
    "tours.multi_before": ("Tours page", "Multi-day promo: text before the daily rate",
                           "Keep the same driver and van for your whole trip, from"),
    "tours.multi_after": ("Tours page", "Multi-day promo: text after the daily rate",
                          "per day. See our sample routes or plan your own."),

    # ── Pub tours page ───────────────────────────────────────────────────────
    "pub.title": ("Pub tours page", "Main heading", "Rural pub tours from Dublin and Meath"),
    "pub.lead": ("Pub tours page", "Intro paragraph",
                 "Country pubs, great pints and no one drawing the short straw. Your driver gets everyone home safely, in our wheelchair-accessible 8-seater."),
    "pub.description": ("Pub tours page", "Search-engine description",
                        "Private rural pub tours from Dublin and Meath for up to 8 people. Your driver gets everyone home safely, so no designated driver needed."),
    "pub.cta_title": ("Pub tours page", "Bottom banner heading", "Plan your pub tour"),
    "pub.cta_text": ("Pub tours page", "Bottom banner text",
                     "Tell us your dates, group size and the kind of pubs you like, and we'll put together a route and a price."),
    "pub.empty": ("Pub tours page", "Message when no pub tours are listed",
                  "New trips are on the way. Tell us what you have in mind and we will plan it for you."),

    # ── Golf trips page ──────────────────────────────────────────────────────
    "golf.title": ("Golf trips page", "Main heading", "Golf trips from Dublin and Meath"),
    "golf.lead": ("Golf trips page", "Intro paragraph",
                  "Links courses and parkland favourites with a private driver and room for clubs and bags. One fixed price per trip, for up to 8 golfers."),
    "golf.description": ("Golf trips page", "Search-engine description",
                         "Private golf trips from Dublin and Meath for up to 8 golfers, with room for clubs and bags and one fixed price per trip."),
    "golf.cta_title": ("Golf trips page", "Bottom banner heading", "Plan your golf trip"),
    "golf.cta_text": ("Golf trips page", "Bottom banner text",
                      "Tell us your dates, group size and the courses you have in mind, and we'll confirm a fixed price."),
    "golf.empty": ("Golf trips page", "Message when no golf trips are listed",
                   "New trips are on the way. Tell us what you have in mind and we will plan it for you."),

    # ── Multi-day page ───────────────────────────────────────────────────────
    "multi.title": ("Multi-day page", "Main heading", "Multi-day private tours of Ireland"),
    "multi.lead_before": ("Multi-day page", "Intro: text before the daily rate",
                          "Your own driver and wheelchair-accessible 8-seater for the whole trip, from"),
    "multi.lead_after": ("Multi-day page", "Intro: text after the daily rate",
                         "per day. Pick a sample route below or tell us what you'd like to see."),
    "multi.notes_title": ("Multi-day page", "Pricing notes: heading", "How multi-day pricing works"),
    "multi.note_rate": ("Multi-day page", "Pricing note 1 (follows the daily rate)",
                        "per day for the vehicle and driver, for up to 8 passengers."),
    "multi.notes": ("Multi-day page", "Pricing notes 2 onwards (one per line)",
                    "Accommodation, meals and attraction tickets are not included. We can suggest places to stay along the route.\nRoutes are samples. We'll adjust the days, stops and pace to suit you.\nMore than 8 travelling? We can arrange extra vehicles so the whole group tours together."),
    "multi.cta_title": ("Multi-day page", "Bottom banner heading", "Plan your Ireland road trip"),
    "multi.cta_text": ("Multi-day page", "Bottom banner text",
                       "Tell us your dates, group size and the places on your list, and we'll put together a route and a fixed price."),

    # ── Price calculator page ────────────────────────────────────────────────
    "calc.title": ("Calculator page", "Main heading", "Tour and taxi price calculator"),
    "calc.lead": ("Calculator page", "Intro paragraph",
                  "Pick a tour, a transfer or a multi-day trip and see your price instantly. Every price is for the whole vehicle, the same for 1 passenger or 8."),
    "calc.row1_desc": ("Calculator page", "Step 1 description", "A full-day private tour from Dublin or Meath."),
    "calc.row2_before": ("Calculator page", "Step 2 description: text before the daily rate",
                         "Same driver and van for the whole trip,"),
    "calc.row2_after": ("Calculator page", "Step 2 description: text after the daily rate", "per day."),
    "calc.row3_desc": ("Calculator page", "Step 3 description", "Fixed fares to and from Dublin Airport."),
    "calc.row4_before": ("Calculator page", "Step 4 description: text before the hourly rate",
                         "More time on any tour,"),
    "calc.row4_after": ("Calculator page", "Step 4 description: text after the hourly rate", "per hour."),
    "calc.row5_before": ("Calculator page", "Step 5 description: text before the passenger limit", "Up to"),
    "calc.row5_after": ("Calculator page", "Step 5 description: text after the passenger limit",
                        "in our van. It doesn't change the price."),
    "calc.legal": ("Calculator page", "Small print under the quote form",
                   "This is an estimate. We'll confirm a fixed price before anything is booked. Parking, tolls and attraction tickets may be extra."),
    "calc.how_title": ("Calculator page", "How it works: heading", "From estimate to fixed price"),
    "calc.step1_title": ("Calculator page", "How it works 1: title", "Build your trip"),
    "calc.step1_text": ("Calculator page", "How it works 1: text",
                        "Combine a day tour, a multi-day trip, airport transfers and extra hours."),
    "calc.step2_title": ("Calculator page", "How it works 2: title", "See the price live"),
    "calc.step2_text": ("Calculator page", "How it works 2: text",
                        "The total updates as you choose. Prices are for the whole vehicle."),
    "calc.step3_title": ("Calculator page", "How it works 3: title", "Send it to us"),
    "calc.step3_text": ("Calculator page", "How it works 3: text",
                        "Send the quote by email or WhatsApp with your dates and pickup."),
    "calc.step4_title": ("Calculator page", "How it works 4: title", "Get a fixed price"),
    "calc.step4_text": ("Calculator page", "How it works 4: text",
                        "We confirm availability and a final fixed price. You pay on the day."),

    # ── Destinations page ────────────────────────────────────────────────────
    "dest.title": ("Destinations page", "Main heading", "Where can we take you?"),
    "dest.lead": ("Destinations page", "Intro paragraph",
                  "Ireland's best-loved places, grouped by region, with approximate driving times from Dublin. Tap any place to see the full tour."),
    "dest.note_before": ("Destinations page", "Note: text before the \"Ask us\" link",
                         "Driving times are approximate and depend on traffic and stops. Don't see your destination?"),
    "dest.note_after": ("Destinations page", "Note: text after the \"Ask us\" link",
                        ", we go anywhere in Ireland."),

    # ── Blog page ────────────────────────────────────────────────────────────
    "blog.title": ("Blog page", "Main heading", "Ireland travel guides and tips"),
    "blog.lead": ("Blog page", "Intro paragraph",
                  "Day trip ideas, airport advice and practical tips for getting around Ireland."),

    # ── Home page additions ──────────────────────────────────────────────────
    "home.card_vehicle_label": ("Home page", "Booking card: vehicle label", "Vehicle"),
    "home.fleet_title": ("Home page", "Fleet strip: heading", "Our fleet"),
    "home.fleet_intro": ("Home page", "Fleet strip: text", "Saloon, MPV, van or minibus. Pick the one that fits."),
    "home.fleet_link": ("Home page", "Fleet strip: link", "See the whole fleet"),
    "home.biz_title": ("Home page", "Business row: heading", "For business"),
    "home.biz_text": ("Home page", "Business row: text", "Monthly invoicing and one account for your whole team."),
    "home.biz_button": ("Home page", "Business row: button", "Business accounts"),
    "home.partner_title": ("Home page", "Partners row: heading", "For partners"),
    "home.partner_text": ("Home page", "Partners row: text", "Hotels, agents and planners: reliable transfers for your guests."),
    "home.partner_button": ("Home page", "Partners row: button", "Become a partner"),
    "home.faq_all": ("Home page", "Questions: link to the Help centre", "More answers in the Help centre"),

    # ── Fleet page ───────────────────────────────────────────────────────────
    "fleet.title": ("Fleet page", "Main heading", "Our fleet"),
    "fleet.lead": ("Fleet page", "Intro paragraph",
                   "From a single traveller to a whole wedding party, choose the vehicle that fits. Photos and models are examples, and we'll confirm the exact vehicle when you book."),
    "fleet.description": ("Fleet page", "Search-engine description",
                          "The BCH Taxi fleet: executive saloon, premium MPV, wheelchair-accessible 8-seater van and minibus or coach for groups, in Dublin, Meath and across Ireland."),
    "fleet.book_button": ("Fleet page", "Vehicle button", "Book this vehicle"),
    "fleet.empty": ("Fleet page", "Message when no vehicles are listed",
                    "Tell us what you need and we'll arrange the right vehicle."),
    "fleet.cta_title": ("Fleet page", "Bottom banner heading", "Not sure which vehicle?"),
    "fleet.cta_text": ("Fleet page", "Bottom banner text",
                       "Tell us your group size, luggage and route, and we'll suggest the right vehicle and a price."),

    # ── Business page ────────────────────────────────────────────────────────
    "business.title": ("Business page", "Main heading", "Travel for business"),
    "business.lead": ("Business page", "Intro paragraph",
                      "Reliable transport for your team and your clients, with one account and one contact."),
    "business.description": ("Business page", "Search-engine description",
                             "Corporate taxi and transfer accounts in Dublin and Meath: monthly invoicing, one account for the whole team, airport and roadshow transfers and a named contact."),
    "business.benefits_title": ("Business page", "Benefits: heading", "What you get"),
    "business.benefits": ("Business page", "Benefits (one per line)",
                          "Monthly invoicing\nOne account for the whole team\nAirport and roadshow transfers\nPriority booking\nA named contact"),
    "business.how_title": ("Business page", "How it works: heading", "How it works"),
    "business.step1_title": ("Business page", "Step 1: title", "Tell us about your business"),
    "business.step1_text": ("Business page", "Step 1: text", "Send the short form below with your company and the trips you usually make."),
    "business.step2_title": ("Business page", "Step 2: title", "We set up your account"),
    "business.step2_text": ("Business page", "Step 2: text", "We get in touch to agree prices and invoicing, and set the account up for you."),
    "business.step3_title": ("Business page", "Step 3: title", "Book when you need us"),
    "business.step3_text": ("Business page", "Step 3: text", "Call, WhatsApp or book online. Your named contact looks after the rest."),
    "business.form_title": ("Business page", "Form: heading", "Open a business account"),
    "business.form_lead": ("Business page", "Form: intro", "This is an enquiry, not a sign-up. We'll contact you to set everything up."),
    "business.form_button": ("Business page", "Form: send button", "Send enquiry"),
    "business.form_legal": ("Business page", "Form: small print", "We only use these details to reply to your enquiry."),

    # ── Partners page ────────────────────────────────────────────────────────
    "partners.title": ("Partners page", "Main heading", "Partner with BCH Taxi"),
    "partners.lead": ("Partners page", "Intro paragraph",
                      "Hotels, travel agents, event planners and tour operators: dependable transfers for your guests and clients."),
    "partners.description": ("Partners page", "Search-engine description",
                             "Partnerships with BCH Taxi for hotels, travel agents, event planners and tour operators: referral arrangements, reliable guest transfers and priority availability."),
    "partners.gets_title": ("Partners page", "What partners get: heading", "What partners get"),
    "partners.gets": ("Partners page", "What partners get (one per line)",
                      "A commission or referral arrangement\nReliable transfers for your guests\nPriority availability"),
    "partners.who_title": ("Partners page", "Who it's for: heading", "Who it's for"),
    "partners.who": ("Partners page", "Who it's for (one per line)",
                     "Hotels and guest houses\nTravel agents\nEvent planners\nTour operators"),
    "partners.form_title": ("Partners page", "Form: heading", "Become a partner"),
    "partners.form_lead": ("Partners page", "Form: intro", "Tell us about your business and we'll be in touch to talk through the arrangement."),
    "partners.form_button": ("Partners page", "Form: send button", "Send enquiry"),
    "partners.form_legal": ("Partners page", "Form: small print", "We only use these details to reply to your enquiry."),

    # ── Help page ────────────────────────────────────────────────────────────
    "help.title": ("Help page", "Main heading", "Help centre"),
    "help.lead": ("Help page", "Intro paragraph", "Answers to common questions, and how to reach us."),
    "help.description": ("Help page", "Search-engine description",
                         "Help for BCH Taxi customers: booking, payment, wheelchair access, airport pickups, areas covered, vehicles and how to change a booking."),
    "help.faq_title": ("Help page", "Questions: heading", "Frequently asked questions"),
    "help.contact_title": ("Help page", "Contact: heading", "Contact us"),
    "help.contact_text": ("Help page", "Contact: text", "We answer calls and messages day and night."),
    "help.changes_title": ("Help page", "Booking changes: heading", "Need to change a booking?"),
    "help.changes_text": ("Help page", "Booking changes: text",
                          "Call or WhatsApp us with your name and the date of your trip, and we'll sort it out."),
    "help.faq_question_7": ("Help page", "Extra question 1: question", "Which vehicle should I choose?"),
    "help.faq_answer_7": ("Help page", "Extra question 1: answer",
                          "Tell us how many people and how much luggage, and we'll suggest one. See the Fleet page for the saloon, MPV, 8-seater van and minibus."),
    "help.faq_question_8": ("Help page", "Extra question 2: question", "Can my company open an account?"),
    "help.faq_answer_8": ("Help page", "Extra question 2: answer",
                          "Yes. Send the form on the Business page and we'll set up an account by hand and agree invoicing with you."),
    # These two started life on the home page; the keys are kept so earlier edits survive.
    "home.faq_question_5": ("Help page", "Question: groups (question)", "Can I book for a group?"),
    "home.faq_answer_5": ("Help page", "Question: groups (answer)",
                          "Absolutely. Our 8-seater van is perfect for groups of up to 8, whether it's a family holiday, a hen party or a team outing. For larger groups we can arrange extra vehicles, from a second van to a minibus or coach, so everyone travels together with one booking and one point of contact."),
    "home.faq_question_6": ("Help page", "Question: flights (question)", "Do you track flights for airport pickups?"),
    "home.faq_answer_6": ("Help page", "Question: flights (answer)",
                          "Yes. We monitor your flight in real time so if it's early or delayed, we adjust. No waiting around at arrivals — we'll be there when you land."),
}


# ── Lookup ───────────────────────────────────────────────────────────────────

def configure(overrides, max_passengers=8):
    """Set the owner overrides ({key: value}) used by T() until the next call."""
    global _overrides, _max_pax
    _max_pax = max_passengers
    _overrides = {k: v for k, v in (overrides or {}).items()
                  if isinstance(k, str) and isinstance(v, str)}


def template_texts(template):
    """{key: default} for every <!-- @t:key -->default<!-- /@t:key --> marker."""
    return {m.group(1): html.unescape(m.group(2)) for m in MARKER_RE.finditer(template)}


def _template_defaults():
    stamp = TEMPLATE_PATH.stat().st_mtime_ns
    cached = _template_cache.get("v")
    if not cached or cached[0] != stamp:
        _template_cache["v"] = (stamp, template_texts(TEMPLATE_PATH.read_text()))
    return _template_cache["v"][1]


def dyn(text):
    """Built-in wording with the passenger limit swapped in (see _PAX_PHRASES)."""
    if _max_pax == 8:
        return text
    for pat, fn in _PAX_PHRASES:
        text = pat.sub(lambda m, fn=fn: fn(m, _max_pax), text)
    return text


def dyn_template(s):
    """dyn() for the parts of a template outside @t: markers."""
    out, pos = [], 0
    for m in MARKER_RE.finditer(s):
        out += [dyn(s[pos:m.start()]), m.group(0)]
        pos = m.end()
    return "".join(out) + dyn(s[pos:])


def _raw(key):
    if key in _overrides:
        return _overrides[key]
    if key in TEXTS:
        return dyn(TEXTS[key][2])
    return dyn(_template_defaults()[key])


def raw(key):
    """The merged value, unescaped (for places that escape it themselves)."""
    return _raw(key)


def esc(value):
    """Escape for HTML text. '{{' is neutralised so text can't forge a token."""
    return html.escape(value, quote=False).replace("{{", "&#123;{")


def T(key):
    """The merged value (owner override, else the default), HTML-escaped."""
    return esc(_raw(key))


def T_lines(key):
    """A list text: one escaped item per non-blank line."""
    return [esc(line.strip()) for line in _raw(key).splitlines() if line.strip()]


def replace_markers(s):
    """Replace every template marker with its escaped merged value (markers stripped)."""
    def sub(m):
        key, default = m.group(1), html.unescape(m.group(2))
        return esc(_overrides[key] if key in _overrides else dyn(default))
    return MARKER_RE.sub(sub, s)


# ── For the admin ────────────────────────────────────────────────────────────

_WORDS = {"faq": "FAQ", "wa": "WhatsApp", "btn": "button", "cta": "call-to-action"}


def humanize(key):
    name = key.split(".", 1)[-1]
    words = [_WORDS.get(w, w) for w in name.split("_")]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def _multiline(value):
    return "\n" in value or len(value) > 80


def all_text_defaults():
    """{key: {group, label, default, multiline}} from the registry and the template."""
    out = {}
    for key, default in _template_defaults().items():
        out[key] = {"group": "Home page", "label": humanize(key),
                    "default": default, "multiline": _multiline(default)}
    for key, (group, label, default) in TEXTS.items():
        out[key] = {"group": group, "label": label, "default": default,
                    "multiline": _multiline(default)}
    return out
