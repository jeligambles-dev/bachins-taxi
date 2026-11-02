// Instant airport fares from picked (or typed) addresses. Pure functions, no DOM:
// usable in the browser (window.BCHFares) and in Node (module.exports).
(function (root) {
  const AIRPORT = { lat: 53.4264, lon: -6.2499 };
  const AIRPORT_RADIUS_KM = 3;

  function km(a, b) {
    const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(h));
  }

  const num = (v) => (v === '' || v === null || v === undefined ? NaN : Number(v));

  // A place is the airport if its label says so, or it is within 3 km of it.
  function isAirport(p) {
    if (!p) return false;
    if (/dublin airport/i.test(p.label || '')) return true;
    const lat = num(p.lat), lon = num(p.lon);
    return isFinite(lat) && isFinite(lon) && km({ lat, lon }, AIRPORT) <= AIRPORT_RADIUS_KM;
  }

  const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // "Dublin 13" -> D13; "Dublin City Centre" -> D01, D02, D07, D08 (Eircode routing keys).
  function routingKeys(area) {
    const a = area.trim();
    const m = /^dublin\s+(\d{1,2})$/i.exec(a);
    if (m) return ['D' + m[1].padStart(2, '0')];
    if (/^dublin city( centre| center)?$/i.test(a)) return ['D01', 'D02', 'D07', 'D08'];
    return [];
  }

  // Does a fare area name match a place? Picked places are matched on their
  // structured parts; typed text (no structure) on the whole label.
  function placeMatches(area, p) {
    if (!p || !area) return false;
    // A place's own name only counts when the place is an area (a street called
    // "Bray Road" is not Bray).
    const areaName = /^(city|town|village|hamlet|locality|district|suburb|county|neighbourhood|state)$/i.test(p.type || '') ? p.name : '';
    const parts = [areaName, p.district, p.locality, p.city, p.county].filter(Boolean);
    const texts = parts.length ? parts : [p.label || ''];
    const word = new RegExp('(^|[^\\p{L}\\p{N}])' + escape(area.trim()) + '($|[^\\p{L}\\p{N}])', 'iu');
    if (texts.some((t) => word.test(t))) return true;
    const keys = routingKeys(area);
    if (!keys.length) return false;
    const codes = [p.postcode, p.label].filter(Boolean).join(' ').toUpperCase();
    return keys.some((k) => new RegExp('(^|[^A-Z0-9])' + k + '(\\s?[0-9A-Z]{4})?($|[^A-Z0-9])').test(codes));
  }

  // fares: { airport: [{area, to, from}], long: [{area, price}] }
  // Returns { area, dir: 'to'|'from', price } or null when there is no fixed fare.
  function matchFare(from, to, fares) {
    const fa = isAirport(from), ta = isAirport(to);
    if (fa === ta) return null;                       // neither end, or both ends, at the airport
    const other = fa ? to : from;
    if (!other || !String(other.label || '').trim()) return null;
    const dir = ta ? 'to' : 'from';
    const list = [
      ...((fares && fares.airport) || []).map((f) => ({ area: f.area, to: f.to, from: f.from })),
      ...((fares && fares.long) || []).map((f) => ({ area: f.area, to: f.price, from: f.price })),
    ].sort((a, b) => b.area.length - a.area.length);  // most specific name first
    const hit = list.find((f) => placeMatches(f.area, other));
    return hit ? { area: hit.area, dir, price: dir === 'to' ? hit.to : hit.from } : null;
  }

  const api = { matchFare, isAirport, placeMatches, routingKeys, km };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.BCHFares = api;
})(typeof window !== 'undefined' ? window : globalThis);
