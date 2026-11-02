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
    "home.fleet_title": ("Home page", "Fleet strip: heading", "From solo travellers to large groups"),
    "home.fleet_intro": ("Home page", "Fleet strip: text", "Saloon, people carrier, 8-seater van or minibus. Pick the one that fits."),
    "home.fleet_link": ("Home page", "Fleet strip: link", "See the whole fleet"),
    "home.biz_title": ("Home page", "Business row: heading", "Business accounts"),
    "home.biz_text": ("Home page", "Business row: text", "One account, one contact and one monthly invoice for your whole team."),
    "home.biz_button": ("Home page", "Business row: button", "Travel for business"),
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
    "business.title": ('Business page', 'Main heading', 'Business travel'),
    "business.lead": ('Business page', 'Intro paragraph', 'Team transport, client travel and guest transfers, from airport runs to a driver for the whole day.'),
    "business.description": ('Business page', 'Search-engine description', 'Business taxi and chauffeur transport in Dublin, Meath and across Ireland: airport transfers, hourly hire, roadshows, events, crew and staff transport, with one account and one monthly invoice.'),
    "business.bar_title": ('Business page', 'Quick quote bar: heading', 'Get a business quote'),
    "business.bar_button": ('Business page', 'Quick quote bar: button', 'Get a quote'),
    "business.offer_title": ('Business page', 'What we offer: heading', 'What we offer'),
    "business.offer_text": ('Business page', 'What we offer: text', "One local team for your company's ground transport. Every trip is booked in advance at an agreed price, so there's no meter and no surprises on the invoice."),
    "business.built_title": ('Business page', 'Built for business: heading', 'Built for business'),
    "business.built_text": ('Business page', 'Built for business: text', 'One account, one invoice and one contact. Every trip is itemised, so you can see who travelled, where and when.'),
    "business.p1_title": ('Business page', 'Promise 1: title', 'On time'),
    "business.p1_text": ('Business page', 'Promise 1: text', 'We track flights and adjust pickups, and you can reach us by phone day and night.'),
    "business.p2_title": ('Business page', 'Promise 2: title', 'Discreet and professional'),
    "business.p2_text": ('Business page', 'Promise 2: text', 'Clean vehicles, smart drivers and quiet journeys. We can sign an NDA on request.'),
    "business.p3_title": ('Business page', 'Promise 3: title', 'One monthly invoice'),
    "business.p3_text": ('Business page', 'Promise 3: text', 'Agreed prices, with every trip itemised on a single invoice each month.'),
    "business.chauffeur_title": ('Business page', 'Chauffeur service: heading', 'Chauffeur service'),
    "business.chauffeur_text": ('Business page', 'Chauffeur service: intro', 'For executives, clients and visitors, booked ahead with a fixed price.'),
    "business.c1_title": ('Business page', 'Chauffeur card 1: title', 'Airport transfers'),
    "business.c1_text": ('Business page', 'Chauffeur card 1: text', "Dublin Airport collections and drop-offs for staff and visiting clients. We watch the flight, so a delay doesn't mean a missed pickup."),
    "business.c2_title": ('Business page', 'Chauffeur card 2: title', 'Hourly chauffeur hire'),
    "business.c2_text": ('Business page', 'Chauffeur card 2: text', 'One vehicle and driver from first pickup to last drop-off, with waiting time included. Half-day options are available.'),
    "business.c3_title": ('Business page', 'Chauffeur card 3: title', 'Roadshows and multi-stop days'),
    "business.c3_text": ('Business page', 'Chauffeur card 3: text', 'Meetings, client visits and office-to-office runs, with multi-stop days handled without rebooking.'),
    "business.c4_title": ('Business page', 'Chauffeur card 4: title', 'Events and conferences'),
    "business.c4_text": ('Business page', 'Chauffeur card 4: text', 'Group pickups and scheduled returns for conferences, company dinners and events.'),
    "business.c5_title": ('Business page', 'Chauffeur card 5: title', 'Intercity transfers'),
    "business.c5_text": ('Business page', 'Chauffeur card 5: text', 'Door to door to Cork, Galway, Limerick, Belfast and anywhere else in Ireland, at one fixed price.'),
    "business.book_button": ('Business page', 'Card button', 'Book now'),
    "business.why_title": ('Business page', 'Why companies choose us: heading', 'Why companies choose us'),
    "business.benefits": ('Business page', 'Why companies choose us (one per line)', 'Booked ahead at an agreed price, with no meter\nOne contact who knows your account\nWe track flights and adjust pickups\nA wheelchair-accessible van when you need one\nAvailable day and night, seven days a week'),
    "business.crew_title": ('Business page', 'Employee and crew transport: heading', 'Employee and crew transport'),
    "business.crew_text": ('Business page', 'Employee and crew transport: intro', 'Regular and one-off runs for teams, crews and staff.'),
    "business.e1_title": ('Business page', 'Crew card 1: title', 'Crew transfers'),
    "business.e1_text": ('Business page', 'Crew card 1: text', 'Hotel, airport and site runs for crews, timed around flights and call times.'),
    "business.e2_title": ('Business page', 'Crew card 2: title', 'Staff commutes'),
    "business.e2_text": ('Business page', 'Crew card 2: text', 'Regular pickups and drop-offs for staff, on a schedule you set.'),
    "business.e3_title": ('Business page', 'Crew card 3: title', 'Shift-time transport'),
    "business.e3_text": ('Business page', 'Crew card 3: text', "Early-morning and late-night runs for workplaces that public transport doesn't reach."),
    "business.e4_title": ('Business page', 'Crew card 4: title', 'Team and group transport'),
    "business.e4_text": ('Business page', 'Crew card 4: text', 'Our 8-seater van, or a minibus for bigger teams, so everyone arrives together.'),
    "business.fleet_title": ('Business page', 'Vehicles: heading', 'Vehicles for business'),
    "business.fleet_text": ('Business page', 'Vehicles: intro', "Choose the vehicle that suits the trip. We'll confirm the exact vehicle when you book."),
    "business.fleet_link": ('Business page', 'Vehicles: link', 'See the whole fleet'),
    "business.special_title": ('Business page', 'Special requirements: heading', 'Special requirements'),
    "business.special_text": ('Business page', 'Special requirements: intro', "Tell us what you need and we'll reply within one business day."),
    "business.special_options": ('Business page', 'Special requirements: options (one per line)', 'Several vehicles for one event\nRecurring schedules\nA dedicated vehicle and driver\nInvoicing set up the way your company needs'),
    "business.form_title": ('Business page', 'Form: heading', 'Open a business account or ask for a quote'),
    "business.form_lead": ('Business page', 'Form: intro', "This is an enquiry, not a sign-up. We'll contact you to set everything up."),
    "business.form_button": ('Business page', 'Form: send button', 'Send enquiry'),
    "business.form_legal": ('Business page', 'Form: small print', 'We only use these details to reply to your enquiry.'),
    "business.faq_title": ('Business page', 'Questions: heading', 'Business questions'),
    "business.faq_q1": ('Business page', 'Question 1', 'How does a business account work?'),
    "business.faq_a1": ('Business page', 'Answer 1', 'Send us the form on this page. We agree prices and invoicing with you, then your team books by phone, WhatsApp or email, and each trip appears on one monthly invoice.'),
    "business.faq_q2": ('Business page', 'Question 2', "What's included in a business account?"),
    "business.faq_a2": ('Business page', 'Answer 2', 'Agreed prices, one contact, itemised monthly invoices and help with changes, day or night.'),
    "business.faq_q3": ('Business page', 'Question 3', 'What vehicles do you use?'),
    "business.faq_a3": ('Business page', 'Answer 3', "See the vehicles on this page and on our Fleet page. Tell us about the trip and we'll suggest the right one."),
    "business.faq_q4": ('Business page', 'Question 4', 'Where do travellers meet the driver at the airport?'),
    "business.faq_a4": ('Business page', 'Answer 4', "We agree the meeting point when you book and send the driver's details. We track the flight, so we're there when they land."),
    "business.faq_q5": ('Business page', 'Question 5', 'Can you handle several vehicles for one event?'),
    "business.faq_a5": ('Business page', 'Answer 5', 'Yes. We can arrange extra vehicles, from a second van to a minibus or coach, so the whole group travels with one booking and one contact.'),
    "business.faq_q6": ('Business page', 'Question 6', 'How do you handle last-minute changes?'),
    "business.faq_a6": ('Business page', 'Answer 6', "Call or WhatsApp us. We'll do our best to change times or add pickups, day or night."),
    "business.faq_q7": ('Business page', 'Question 7', 'Do you take recurring bookings?'),
    "business.faq_a7": ('Business page', 'Answer 7', 'Yes. Regular runs such as staff commutes or weekly airport trips can be set up as a schedule.'),

    # ── Partners page ────────────────────────────────────────────────────────
    "partners.title": ("Partners page", "Main heading", "Partner with BCH Taxi"),
    "partners.lead": ("Partners page", "Intro paragraph",
                      "Hotels, travel agents, event planners and tour operators: dependable transfers for your guests and clients."),
    "partners.description": ("Partners page", "Search-engine description",
                             "Partnerships with BCH Taxi for hotels, travel agents, event planners and tour operators: referral arrangements, reliable guest transfers and priority availability."),
    "partners.gets_title": ("Partners page", "Why partner: heading", "Why partner with us"),
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

    # ── Round 3 additions (fleet, partners, help, home) ──────────────────────
    "partners.how_title": ('Partners page', 'How it works: heading', 'How it works'),
    "partners.step1_title": ('Partners page', 'Step 1: title', 'Tell us about your business'),
    "partners.step1_text": ('Partners page', 'Step 1: text', 'Send the short form below.'),
    "partners.step2_title": ('Partners page', 'Step 2: title', 'We agree the details'),
    "partners.step2_text": ('Partners page', 'Step 2: text', 'We talk through bookings, prices and the referral arrangement.'),
    "partners.step3_title": ('Partners page', 'Step 3: title', 'Send us your guests'),
    "partners.step3_text": ('Partners page', 'Step 3: text', 'Book by phone, WhatsApp or email, and we look after the trip.'),
    "partners.faq_title": ('Partners page', 'Questions: heading', 'Partner questions'),
    "partners.faq_q1": ('Partners page', 'Question 1', 'What kinds of businesses partner with you?'),
    "partners.faq_a1": ('Partners page', 'Answer 1', 'Hotels and guest houses, travel agents, event planners and tour operators in Dublin, Meath and beyond.'),
    "partners.faq_q2": ('Partners page', 'Question 2', 'How does the referral arrangement work?'),
    "partners.faq_a2": ('Partners page', 'Answer 2', 'We agree it with each partner when we talk, depending on the kind of trips you send us.'),
    "partners.faq_q3": ('Partners page', 'Question 3', 'Do I need to install anything?'),
    "partners.faq_a3": ('Partners page', 'Answer 3', 'No. You book with us by phone, WhatsApp or email.'),
    "fleet.faq_title": ('Fleet page', 'Questions: heading', 'Choosing a vehicle'),
    "fleet.faq_q1": ('Fleet page', 'Question 1', 'How do I choose the right vehicle?'),
    "fleet.faq_a1": ('Fleet page', 'Answer 1', "Count your passengers and bags. One to three people with normal luggage fit the saloon. Bigger groups or lots of luggage suit the MPV, the 8-seater van or the minibus. Tell us and we'll suggest one."),
    "fleet.faq_q2": ('Fleet page', 'Question 2', 'Can I book a specific car model?'),
    "fleet.faq_a2": ('Fleet page', 'Answer 2', "The photos and models are examples. We'll confirm the exact vehicle when you book."),
    "fleet.faq_q3": ('Fleet page', 'Question 3', 'Are child seats available?'),
    "fleet.faq_a3": ('Fleet page', 'Answer 3', "Tell us your children's ages in the booking notes and we'll confirm what we can provide."),
    "fleet.faq_q4": ('Fleet page', 'Question 4', 'Which vehicle is wheelchair accessible?'),
    "fleet.faq_a4": ('Fleet page', 'Answer 4', 'Our 8-seater van has a built-in ramp and secure fastening points.'),
    "help.topics_title": ('Help page', 'Topics: heading', 'Browse topics'),
    "help.topics": ('Help page', 'Topics (one per line)', 'Booking and changes\nAirport pickups\nVehicles\nBusiness accounts\nPartners\nContact us'),
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
