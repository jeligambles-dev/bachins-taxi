"""Terms, privacy and company details: the footer and legal pages that make the site look official."""
from pathlib import Path

import build
import texts
from content import default_content, merge


def _build(tmp_path, overrides=None):
    build.build_site(merge(default_content(), {"texts": overrides or {}}), tmp_path)
    return tmp_path


def _footer(html):
    return html[html.index('class="site-footer'):]


def test_terms_and_privacy_pages_exist(tmp_path):
    out = _build(tmp_path)
    terms = (out / "terms.html").read_text()
    privacy = (out / "privacy.html").read_text()
    assert "<h1>Terms &amp; conditions</h1>" in terms
    assert "<h1>Privacy policy</h1>" in privacy
    assert "<title>Terms &amp; Conditions | BCH Group</title>" in terms
    assert "<title>Privacy Policy | BCH Group</title>" in privacy


def test_every_footer_links_terms_and_privacy(tmp_path):
    out = _build(tmp_path)
    for p in Path(out).rglob("*.html"):
        depth = len(p.relative_to(out).parts) - 1
        root = "../" * depth
        foot = _footer(p.read_text())
        assert f'href="{root}terms.html"' in foot, p
        assert f'href="{root}privacy.html"' in foot, p
        assert "All rights reserved" in foot, p


def test_privacy_names_the_services_that_see_data(tmp_path):
    privacy = (_build(tmp_path) / "privacy.html").read_text()
    for name in ("FormSubmit", "Google", "Photon", "WhatsApp", "Railway", "Data Protection Commission"):
        assert name in privacy, name


def test_legal_pages_show_contact_details(tmp_path):
    out = _build(tmp_path)
    c = merge(default_content(), {})
    for page in ("terms.html", "privacy.html"):
        h = (out / page).read_text()
        email = c["settings"]["email"]
        assert f'<a href="mailto:{email}">{email}</a>' in h, page
        assert "&#123;" not in h and "{{" not in h and "[email]" not in h and "[phone]" not in h, page
    assert f'<a href="tel:{c["settings"]["phone"]}">' in (out / "terms.html").read_text()


def test_owner_text_can_use_contact_markers(tmp_path):
    h = (_build(tmp_path, {"privacy.s1_text": "Write to [email] or ring [phone]. {{EMAIL}}"}) / "privacy.html").read_text()
    h = h[h.index('class="wrap legal"'):]
    h = h[:h.index("</section>")]
    assert "Write to <a href=\"mailto:" in h and "ring <a href=\"tel:" in h
    assert "&#123;{EMAIL}}" in h   # real tokens stay neutralised in owner text


def test_legal_text_is_editable_and_override_wins(tmp_path):
    defaults = texts.all_text_defaults()
    assert "terms.s1_title" in defaults and "privacy.s1_text" in defaults
    assert defaults["terms.s1_title"]["group"] == "Terms page"
    out = _build(tmp_path, {"terms.s1_text": "Our own <b>wording</b>.\n\nSecond paragraph."})
    h = (out / "terms.html").read_text()
    assert "<p>Our own &lt;b&gt;wording&lt;/b&gt;.</p>" in h
    assert "<p>Second paragraph.</p>" in h


def test_company_details_hidden_until_set(tmp_path):
    foot = _footer((_build(tmp_path) / "index.html").read_text())
    assert 'class="footer-company"' not in foot


def test_company_details_shown_in_footer_and_terms(tmp_path):
    out = _build(tmp_path, {
        "company.legal_name": "BCH Group Ltd",
        "company.number": "712345",
        "company.vat": "IE1234567X",
        "company.spsv": "SPSV 01234",
        "company.address": "Main St, Dunshaughlin, Co. Meath & Co"})
    foot = _footer((out / "fleet.html").read_text())
    line = foot[foot.index('class="footer-company"'):]
    line = line[:line.index("</p>")]
    for part in ("BCH Group Ltd", "Company no. 712345", "VAT IE1234567X",
                 "SPSV licence SPSV 01234", "Main St, Dunshaughlin, Co. Meath &amp; Co"):
        assert part in line, part
    assert "&copy; 2026 BCH Group Ltd" in foot
    assert "BCH Group Ltd" in (out / "terms.html").read_text()


def test_company_details_partial(tmp_path):
    foot = _footer((_build(tmp_path, {"company.number": "712345"}) / "index.html").read_text())
    line = foot[foot.index('class="footer-company"'):]
    line = line[:line.index("</p>")]
    assert "Company no. 712345" in line and "VAT" not in line and "SPSV" not in line


def test_admin_saves_company_detail_and_blank(tmp_path):
    """The owner can fill in a company field and later clear it again."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from server.admin.texts import _mutator
    defaults = texts.all_text_defaults()
    filled = _mutator({"t__company.number": "712345"}, defaults)({"texts": {}})
    assert filled["texts"]["company.number"] == "712345"
    cleared = _mutator({"t__company.number": ""}, defaults)(filled)
    assert "company.number" not in cleared["texts"]


def test_site_photos_carry_content_hash(tmp_path):
    """Replacing a photo under the same name must reach browsers that cached
    the old one for a week: the URL changes with the file's content."""
    import hashlib
    out = _build(tmp_path)
    root = Path(build.__file__).resolve().parent.parent
    v = hashlib.sha256((root / "images/fleet-van.jpg").read_bytes()).hexdigest()[:8]
    for page in ("index.html", "fleet.html"):
        assert f'src="images/fleet-van.jpg?v={v}"' in (out / page).read_text(), page
    help_h = (out / "help.html").read_text()
    c = hashlib.sha256((root / "images/photo-commute.jpg").read_bytes()).hexdigest()[:8]
    assert f"images/photo-commute.jpg?v={c}" in help_h
