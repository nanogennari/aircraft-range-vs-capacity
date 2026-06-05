#!/usr/bin/env python3
"""
Scrape Wikipedia for commercial aircraft data.
Outputs aircraft_data.json with range, capacity, manufacturer, first-flight year.
"""

import re
import json
import time
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "aircraft-range-viz/1.0 (educational project)"}
BASE_URL = "https://en.wikipedia.org"
LIST_URL = f"{BASE_URL}/wiki/List_of_jet_airliners"
CACHE = Path("aircraft_data.json")
DELAY = 0.35  # seconds between requests — be polite to Wikipedia


# ── Text helpers ─────────────────────────────────────────────────────────────

def txt(el) -> str:
    if el is None:
        return ""
    return el.get_text(separator=" ", strip=True)


def clean(text: str) -> str:
    return re.sub(r"\[.*?\]", "", text).replace("\xa0", " ").strip()


# ── Unit parsers ──────────────────────────────────────────────────────────────

def parse_range_km(text: str) -> float | None:
    if not text:
        return None
    t = clean(text).replace(",", "")

    def mid(a, b):
        return (float(a) + float(b)) / 2

    # km — try range first, then single value
    m = re.findall(r"([\d.]+)\s*(?:–|-|to)\s*([\d.]+)\s*k(?:m|ilometres?)", t, re.I)
    if m:
        return mid(*m[0])
    m = re.search(r"([\d.]+)\s*k(?:m|ilometres?)", t, re.I)
    if m:
        return float(m.group(1))

    # nmi → km
    m = re.findall(r"([\d.]+)\s*(?:–|-|to)\s*([\d.]+)\s*n(?:mi|autical)", t, re.I)
    if m:
        return mid(*m[0]) * 1.852
    m = re.search(r"([\d.]+)\s*n(?:mi|autical)", t, re.I)
    if m:
        return float(m.group(1)) * 1.852

    # statute miles → km
    m = re.findall(r"([\d.]+)\s*(?:–|-|to)\s*([\d.]+)\s*mi\b", t, re.I)
    if m:
        return mid(*m[0]) * 1.60934
    m = re.search(r"([\d.]+)\s*mi\b", t, re.I)
    if m:
        return float(m.group(1)) * 1.60934

    return None


def parse_capacity(text: str) -> int | None:
    if not text:
        return None
    t = clean(text).replace(",", "")

    # Leading total with per-class breakdown in parens: "305 (24F/54J/227Y)"
    # Leading total followed by per-cabin breakdown, e.g.:
    #   "305 (24F/54J/227Y)"  — paren style
    #   "298: 16F + 56J + 226Y or 323: 34J + 289Y"  — colon style (MD-11)
    # In both cases the number before the separator is the grand total.
    m_lead = re.match(r"(\d{2,4})\s*[:(]", t)
    if m_lead:
        n = int(m_lead.group(1))
        if 10 <= n <= 900:
            return n

    # Explicit passenger marker: "155Y", "90pax", "162 pax"
    m = re.search(r"\b(\d{2,4})\s*[Yy]\b", t)
    if m:
        n = int(m.group(1))
        if 10 <= n <= 900:
            return n

    # Range midpoint (e.g. "150–186") — skip seat-pitch ranges (followed by ", in, cm)
    for match in re.finditer(r"\b(\d{2,4})\s*(?:–|-|to)\s*(\d{2,4})\b", t):
        lo, hi = int(match.group(1)), int(match.group(2))
        if not (10 <= lo < hi <= 900):
            continue
        # Skip if this range is seat pitch (followed by ", in, cm)
        tail = t[match.end():match.end() + 8]
        if re.search(r'[\"”’]\s*|(?:in|cm)\b', tail, re.I):
            continue
        # Also skip if preceded by "@" (seat pitch annotation)
        head = t[max(0, match.start()-5):match.start()]
        if "@" in head:
            continue
        return (lo + hi) // 2

    # Single reasonable number
    candidates = [int(n) for n in re.findall(r"\b(\d{2,4})\b", t) if 10 <= int(n) <= 900]
    # Prefer 3+-digit numbers: actual seat counts are usually ≥100, while 2-digit numbers
    # often appear as variant suffixes (e.g. "-40/43: 177" on DC-8 comparison tables).
    for n in candidates:
        if n >= 100:
            return n
    for n in candidates:
        return n   # first 2-digit if nothing bigger found
    return None


def parse_year(text: str) -> int | None:
    if not text:
        return None
    m = re.search(r"\b(19[3-9]\d|20[012]\d)\b", text)
    return int(m.group(1)) if m else None


# ── Manufacturer normalization ────────────────────────────────────────────────

_MFR_MAP = [
    ("airbus",                      "Airbus"),
    ("boeing",                      "Boeing"),
    ("embraer",                     "Embraer"),
    ("bombardier",                  "Bombardier"),
    (r"\batr\b",                    "ATR"),
    ("mcdonnell douglas",           "McDonnell Douglas"),
    ("douglas aircraft",            "Douglas"),
    ("lockheed",                    "Lockheed"),
    ("de havilland canada",         "De Havilland Canada"),
    ("de havilland",                "De Havilland"),
    ("fokker",                      "Fokker"),
    ("british aerospace",           "British Aerospace"),
    (r"\bbac\b",                    "BAC"),
    ("hawker siddeley",             "Hawker Siddeley"),
    (r"\bsaab\b",                   "SAAB"),
    ("antonov",                     "Antonov"),
    ("tupolev",                     "Tupolev"),
    ("aviakor",                     "Tupolev"),      # Tu-154 built by Aviakor
    ("aviastar",                    "Tupolev"),      # Tu-204 built by Aviastar
    ("kazan aircraft",              "Tupolev"),      # Tu-214 built in Kazan
    ("ilyushin",                    "Ilyushin"),
    ("voronezh",                    "Ilyushin"),     # VASO builds Il-96
    ("sukhoi",                      "Sukhoi"),
    ("united aircraft",             "UAC"),          # Russian holding
    ("irkut",                       "Irkut"),
    ("yakovlev",                    "Yakovlev"),
    (r"\bcomac\b",                  "COMAC"),
    ("mitsubishi",                  "Mitsubishi"),
    ("aerospatiale",                "Aérospatiale"),
    ("sud aviation",                "Sud Aviation"),
    ("vickers",                     "Vickers"),
    ("convair",                     "Convair"),
    ("cessna",                      "Cessna"),
    ("let kunovice",                "LET"),
    (r"\blet\b",                    "LET"),
    ("short brothers",              "Short Brothers"),
    ("fairchild",                   "Fairchild Dornier"),
    ("dassault",                    "Dassault"),
    ("vfw",                         "VFW-Fokker"),
]


def normalize_manufacturer(text: str) -> str:
    if not text:
        return "Unknown"
    text = clean(text).split("\n")[0]
    tl = text.lower()
    for pattern, name in _MFR_MAP:
        if re.search(pattern, tl):
            return name
    return text[:35]


# ── Body-type classification ───────────────────────────────────────────────────
# Wide-body (twin-aisle) aircraft prefixes. Everything else is treated as
# narrow-body (single-aisle). Checked as substrings against the upper-cased name.
_WIDE_BODY_TOKENS = (
    "747", "767", "777", "787",          # Boeing wide-body families
    "A300", "A310", "A330", "A340", "A350", "A380",  # Airbus wide-body
    "L-1011", "DC-10", "MD-11",          # Lockheed / McDonnell Douglas
    "IL-86", "IL-96",                    # Ilyushin wide-body
    "C929", "C939",                      # COMAC wide-body (future)
    "CONCORDE",                          # supersonic / wide cabin
)


def _is_wide_body(name: str, context: str = "") -> bool:
    """Check name and optional context string (e.g. page URL) for wide-body tokens."""
    haystack = (name + " " + context).upper()
    return any(tok in haystack for tok in _WIDE_BODY_TOKENS)


def _family_prefix_from_url(url: str) -> str:
    """Derive aircraft family code from Wikipedia URL slug.

    Used to expand short variant names like '-10' → 'DC-10-10'.
    Extracts the last word in the article title that contains a digit
    (e.g. 'McDonnell_Douglas_DC-10' → 'DC-10', 'Fokker_F28_Fellowship' → 'F28').
    """
    slug = url.rstrip("/").split("/")[-1].replace("_", " ")
    words = slug.split()
    codes = [w for w in words if re.search(r"\d", w) and len(w) <= 12]
    return codes[-1] if codes else words[-1]


def _cap_priority(label: str, wide: bool) -> int:
    """Priority for a capacity table row. Higher wins; -1 = nothing set yet.
    Wide-body:  2-class (4) > generic (3) > 3-class (2) > max/exit limit (0)
    Narrow-body: 1-class (4) > generic (3) > 2-class (2) > 3-class (1) > max/exit limit (0)
    "Maximum seating" / "exit limit" is used only as a last resort (priority 0):
    it beats the sentinel -1 (nothing set) but loses to any real seating label.
    """
    if "maximum" in label or "max." in label or "exit limit" in label:
        return 0
    has2 = "2-class" in label or "2 class" in label
    has3 = "3-class" in label or "3 class" in label
    has1 = "1-class" in label or "1 class" in label
    if wide:
        return 4 if has2 else (2 if has3 else 3)
    else:
        return 4 if has1 else (1 if has3 else (2 if has2 else 3))


# ── Infobox parser ────────────────────────────────────────────────────────────

def parse_infobox(table) -> dict:
    """Return dict of label→value from an infobox table."""
    fields = {}
    for row in table.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td:
            fields[txt(th).lower()] = txt(td)
    return fields


def fields_to_record(fields: dict, name: str, url: str) -> dict:
    rec = dict(name=name, manufacturer=None, first_flight=None,
               range_km=None, capacity=None, url=url)
    cap_priority = -1   # -1 = nothing set; 0 = max-seating last resort; >0 = real label
    wide = _is_wide_body(name, url)

    for label, value in fields.items():
        if any(k in label for k in ("manufacturer", "company", "produced by",
                                      "builder", "built by", "designed by", "designer")):
            if rec["manufacturer"] is None:
                rec["manufacturer"] = normalize_manufacturer(value)

        elif "first flight" in label or "maiden flight" in label:
            rec["first_flight"] = parse_year(value)

        elif "introduction" in label and rec["first_flight"] is None:
            rec["first_flight"] = parse_year(value)

        elif re.search(r"\brange\b", label) and not any(
                ex in label for ex in ("cross", "cruise", "speed", "mach", "long-range", "ferry")):
            if rec["range_km"] is None:
                r = parse_range_km(value)
                if r and 100 <= r <= 22_000:
                    rec["range_km"] = round(r)

        elif (any(k in label for k in ("passenger", "seating", "pax", "accommodation",
                                       "1-class", "2-class", "typical seat"))
              and not any(ex in label for ex in ("payload", "fuel", "weight", "cargo", "pitch",
                                                 "width", "comfort", "count"))):
            prio = _cap_priority(label, wide)
            if prio > cap_priority:
                c = parse_capacity(value)
                if c and 10 <= c <= 900:
                    rec["capacity"] = c
                    cap_priority = prio

    return rec


# ── Variant table parsers ─────────────────────────────────────────────────────

def _is_aircraft_name(text: str) -> bool:
    """Heuristic: aircraft designations contain at least one digit."""
    return bool(text) and bool(re.search(r"\d", text)) and len(text) < 60


def _expand_row(row, skip_first: bool = True) -> list[str]:
    """Return cell text list, repeating values for colspan > 1 merged cells."""
    cells = row.find_all(["th", "td"])
    if skip_first:
        cells = cells[1:]
    result = []
    for c in cells:
        colspan = int(c.get("colspan", 1))
        val = txt(c)
        result.extend([val] * colspan)
    return result


def parse_table_variants_as_columns(table, manufacturer, first_flight, url) -> list[dict]:
    """
    Handle tables where variants are COLUMNS and specs are ROWS.
    Handles merged cells (colspan) by repeating the value across affected columns.

        | Spec          | Var-A | Var-B |
        | Range         | 5000  | 6000  |
        | Typical seats | 150   | 180   |
    """
    rows = table.find_all("tr")
    if not rows:
        return []

    # Find the header row: skip any grouping rows where cells use colspan > 1
    # (e.g. Boeing 777 has row-0 = "First gen / Second gen" with colspan=2,
    #  then row-1 = "777-200 | 777-300 | 777-300ER | 777-200LR" with individual models)
    header_row_idx = 0
    for idx, row in enumerate(rows[:3]):
        cells = row.find_all(["th", "td"])
        if len(cells) < 3:
            continue
        # If any data cell (not first column) has colspan > 1, this is a grouping row
        grouping = any(int(c.get("colspan", 1)) > 1 for c in cells[1:])
        if not grouping:
            header_row_idx = idx
            break
    else:
        header_row_idx = 0

    header_row = rows[header_row_idx]
    all_header_cells = header_row.find_all(["th", "td"])
    if len(all_header_cells) < 3:
        return []

    variants = _expand_row(header_row, skip_first=True)
    if not any(_is_aircraft_name(v) for v in variants):
        return []

    records = [{
        "name": v, "manufacturer": manufacturer,
        "first_flight": first_flight,
        "range_km": None, "capacity": None, "url": url,
    } for v in variants]
    # Priority for capacity source: 3=2-class (preferred), 2=generic, 1=3-class, 0=unset
    cap_priority = [-1] * len(records)   # -1 = nothing set; 0 = max-seating last resort

    for row in rows[header_row_idx + 1:]:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        label = txt(cells[0]).lower()
        values = _expand_row(row, skip_first=True)

        for i, val in enumerate(values):
            if i >= len(records):
                break
            if re.search(r"\brange\b", label) and not any(
                    ex in label for ex in ("cross", "cruise", "speed", "mach", "long-range", "ferry")):
                if records[i]["range_km"] is None:
                    r = parse_range_km(val)
                    if r and 100 <= r <= 22_000:
                        records[i]["range_km"] = round(r)
            elif (any(k in label for k in ("passenger", "seating", "pax", "seat",
                                           "accommodation", "1-class", "2-class", "main deck",
                                           "capacity"))
                  and not any(ex in label for ex in ("payload", "fuel", "weight", "cargo",
                                                     "pitch", "width"))):
                prio = _cap_priority(label, _is_wide_body(records[i]["name"], url))
                if cap_priority[i] < prio:
                    c = parse_capacity(val)
                    if c and 10 <= c <= 900:
                        records[i]["capacity"] = c
                        cap_priority[i] = prio
            elif "first flight" in label or "maiden" in label:
                if records[i]["first_flight"] is None:
                    records[i]["first_flight"] = parse_year(val)

    return [r for r in records if r["range_km"] or r["capacity"]]


def parse_flat_spec_wikitable(table, name: str, manufacturer: str,
                              first_flight: int | None, url: str) -> dict | None:
    """
    Handle flat two-column spec tables (e.g. Fokker 100).
    First column = spec label, remaining columns = one value per config variant.
    We take the first non-empty value for each spec.
    """
    fields = {}
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = txt(cells[0]).lower()
        # Take first non-empty value among data columns
        value = next((txt(c) for c in cells[1:] if txt(c).strip()), "")
        if value and label:
            fields[label] = value

    rec = fields_to_record(fields, name, url)
    if rec["manufacturer"] is None:
        rec["manufacturer"] = manufacturer
    if rec["first_flight"] is None:
        rec["first_flight"] = first_flight
    return rec if (rec["range_km"] or rec["capacity"]) else None


def parse_spec_bullets(soup, name: str, manufacturer: str,
                       first_flight: int | None, url: str) -> dict | None:
    """
    Some pages render specs as a bullet list via {{Specifications (aircraft)}}:
        • Range: 3,410 km (2,119 mi, 1,841 nmi)
        • Capacity: 79 passengers
    """
    rec = dict(name=name, manufacturer=manufacturer,
               first_flight=first_flight, range_km=None, capacity=None, url=url)

    for li in soup.find_all("li"):
        text = li.get_text(separator=" ", strip=True)
        m = re.match(r"(Range|Capacity|Passengers?|Seating)\s*:(.+)", text, re.I)
        if not m:
            continue
        kind, value = m.group(1).lower(), m.group(2)
        if "range" in kind:
            if rec["range_km"] is None:
                r = parse_range_km(value)
                if r and 100 <= r <= 22_000:
                    rec["range_km"] = round(r)
        elif any(k in kind for k in ("capacity", "passenger", "seating")):
            if rec["capacity"] is None:
                c = parse_capacity(value)
                if c and 10 <= c <= 900:
                    rec["capacity"] = c

    return rec if (rec["range_km"] and rec["capacity"]) else None


def parse_table_variants_as_rows(table, manufacturer, first_flight, url) -> list[dict]:
    """
    Handle tables where variants are ROWS and specs are COLUMNS.
    Example: Boeing 737 comparison table.
        | Variant  | Capacity | Range    |
        | 737-100  | 103      | 2850 km  |
        | 737-200  | 130      | 4200 km  |
    """
    rows = table.find_all("tr")
    if len(rows) < 3:
        return []

    header_cells = rows[0].find_all(["th", "td"])
    headers = [txt(c).lower() for c in header_cells]

    range_col = next((i for i, h in enumerate(headers)
                      if re.search(r"\brange\b", h)
                      and not any(ex in h for ex in ("cruise", "speed", "mach", "ferry"))), None)
    pax_col   = next((i for i, h in enumerate(headers)
                      if any(k in h for k in ("passenger", "seating", "seat", "pax",
                                              "accommodation", "1-class", "2-class"))
                      and not any(ex in h for ex in ("payload", "pitch", "width", "weight",
                                                     "cargo", "fuel"))), None)

    if range_col is None and pax_col is None:
        return []

    # First column should be variant names
    records = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        name = txt(cells[0])
        if not _is_aircraft_name(name):
            continue

        rec = dict(name=name, manufacturer=manufacturer,
                   first_flight=first_flight, range_km=None, capacity=None, url=url)

        if range_col and range_col < len(cells):
            r = parse_range_km(txt(cells[range_col]))
            if r and 100 <= r <= 22_000:
                rec["range_km"] = round(r)

        if pax_col and pax_col < len(cells):
            c = parse_capacity(txt(cells[pax_col]))
            if c and 10 <= c <= 900:
                rec["capacity"] = c

        if rec["range_km"] or rec["capacity"]:
            records.append(rec)

    return records


# ── Page scraper ──────────────────────────────────────────────────────────────

def fetch(url: str) -> BeautifulSoup:
    time.sleep(DELAY)
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def scrape_page(url: str, title: str) -> list[dict]:
    try:
        soup = fetch(url)
    except Exception as e:
        print(f"    fetch error: {e}")
        return []

    # --- Main infobox ---
    infobox = soup.find("table", class_=re.compile(r"infobox"))
    if infobox:
        fields    = parse_infobox(infobox)
        main_rec  = fields_to_record(fields, title, url)
        mfr       = main_rec["manufacturer"] or "Unknown"
        ff        = main_rec["first_flight"]
    else:
        main_rec, mfr, ff = None, "Unknown", None

    # --- Look for variant comparison tables ---
    variants: list[dict] = []
    flat_fallback: dict | None = None  # flat 2-col spec table used as last resort

    for table in soup.find_all("table", class_=re.compile(r"wikitable")):
        # Try column-variant format (with colspan expansion for merged cells)
        v = parse_table_variants_as_columns(table, mfr, ff, url)
        if len(v) >= 1:
            variants.extend(v)
            continue
        # Try row-variant format (Boeing 737 style)
        v = parse_table_variants_as_rows(table, mfr, ff, url)
        if len(v) >= 1:
            variants.extend(v)
            continue
        # Remember the first flat spec table as a fallback
        if flat_fallback is None:
            flat_fallback = parse_flat_spec_wikitable(table, title, mfr, ff, url)

    # Deduplicate variants by name
    seen_names: set[str] = set()
    unique_variants = []
    for v in variants:
        if v["name"] not in seen_names:
            seen_names.add(v["name"])
            unique_variants.append(v)

    if unique_variants:
        # Fill in missing manufacturer/year from main record
        for v in unique_variants:
            if v["manufacturer"] == "Unknown" and mfr != "Unknown":
                v["manufacturer"] = mfr
            if v["first_flight"] is None and ff:
                v["first_flight"] = ff
        good = [v for v in unique_variants if v["range_km"] and v["capacity"]]
        if good:
            return good

    # Fall back to main infobox record
    if main_rec and main_rec["range_km"] and main_rec["capacity"]:
        return [main_rec]

    # Fall back to flat spec wikitable
    if flat_fallback and flat_fallback["range_km"] and flat_fallback["capacity"]:
        return [flat_fallback]

    # Fall back to bullet-list specs ({{Specifications (aircraft)}} template)
    bullet = parse_spec_bullets(soup, title, mfr, ff, url)
    if bullet:
        return [bullet]

    return []


# ── Name fixups ───────────────────────────────────────────────────────────────
# Map ICAO engine-variant suffixed names to the common marketing designations.
_NAME_FIXUPS: dict[str, str] = {
    # A330neo: ICAO engine-variant suffix → common marketing name
    "A330-841": "A330-800neo",
    "A330-941": "A330-900neo",
    # A380: all delivered aircraft are the -800 variant; engine suffix not meaningful
    "A380-841": "A380-800",
    "A380-842": "A380-800",
    "A380-861": "A380-800",
    # Convair 880 model numbers (22 = model 22, the base -880 designation)
    "22":  "Convair 880-22",
    "22M": "Convair 880-22M",
}

# First-flight year overrides for variants that inherit the wrong year from the
# original-variant infobox on a shared Wikipedia page.
_FIRST_FLIGHT_FIXUPS: dict[str, int] = {
    "A321neo": 2016,
    "A321LR":  2018,
    "A321XLR": 2023,
    "777-200LR": 2005,
}

# ── Freighter exclusion list ──────────────────────────────────────────────────
# Variant names (exact, case-sensitive, post-citation-strip) that are pure
# freighters or cargo transports. Caught by pattern below where possible;
# this list handles cases that escape pattern matching.
_FREIGHTER_EXCLUSIONS: set[str] = {
    "Il-96T",          # cargo transport variant of Il-96
    "MD-11 F",         # MD-11 freighter (space before F, not caught by \dF$ pattern)
}


# ── Supplementary pages not in the main list ─────────────────────────────────
# These are variant sub-articles for multi-generation families whose main page
# only covers the first generation (e.g. 737 Original page → Classic/NG/MAX on
# separate articles).

_SUPPLEMENTARY = [
    ("Boeing 737 Classic",           f"{BASE_URL}/wiki/Boeing_737_Classic"),
    ("Boeing 737 Next Generation",   f"{BASE_URL}/wiki/Boeing_737_Next_Generation"),
    ("Boeing 737 MAX",               f"{BASE_URL}/wiki/Boeing_737_MAX"),
    ("Boeing 747SP",                 f"{BASE_URL}/wiki/Boeing_747SP"),
    ("Boeing 747-400",               f"{BASE_URL}/wiki/Boeing_747-400"),
    ("Boeing 747-8",                 f"{BASE_URL}/wiki/Boeing_747-8"),
    ("Airbus A320neo family",        f"{BASE_URL}/wiki/Airbus_A320neo_family"),
]


def find_hatnote_variants(soup) -> list[dict]:
    """
    Collect 'Main article: …' hatnote links inside the page.
    Wikipedia renders {{main|…}} as:
        <div class="hatnote">Main article: <a href="/wiki/…">…</a></div>
    These point to sub-articles for sections (e.g. variants, generations).
    """
    found = []
    seen: set[str] = set()
    for div in soup.find_all("div", class_=re.compile(r"hatnote")):
        text = div.get_text(strip=True).lower()
        if "main article" not in text and "see also" not in text:
            continue
        for a in div.find_all("a"):
            href = a.get("href", "")
            if not href.startswith("/wiki/") or ":" in href:
                continue
            url = BASE_URL + href
            if url in seen:
                continue
            seen.add(url)
            found.append({"title": a.get_text(strip=True), "url": url})
    return found


# ── List scraper ──────────────────────────────────────────────────────────────

def get_aircraft_list() -> list[dict]:
    print("Fetching aircraft list …")
    soup = fetch(LIST_URL)
    seen: set[str] = set()
    aircraft = []

    for table in soup.find_all("table", class_=re.compile(r"wikitable")):
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            link = cells[0].find("a")
            if not link:
                continue
            href = link.get("href", "")
            if not href.startswith("/wiki/") or ":" in href:
                continue
            url = BASE_URL + href
            if url in seen:
                continue
            seen.add(url)
            aircraft.append({"title": link.get_text(strip=True), "url": url})

    # Add known supplementary sub-articles
    for title, url in _SUPPLEMENTARY:
        if url not in seen:
            seen.add(url)
            aircraft.append({"title": title, "url": url})

    print(f"  {len(aircraft)} entries found (incl. {len(_SUPPLEMENTARY)} supplementary)")
    return aircraft


# ── Entry point ───────────────────────────────────────────────────────────────

MAX_RETRIES = 3  # retry passes for aircraft that yielded no data


def _scrape_pass(aircraft_list: list[dict], all_data: list[dict],
                 pass_num: int = 1, extra_delay: float = 0.0) -> list[dict]:
    """
    Scrape a list of aircraft. Returns those that still have no usable data
    (candidates for retry).
    """
    failed = []
    total = len(aircraft_list)
    global DELAY
    if extra_delay:
        DELAY += extra_delay  # back off on retries

    for i, ac in enumerate(aircraft_list, 1):
        label = f"[pass {pass_num} | {i:3d}/{total}]"
        print(f"{label} {ac['title']}")
        try:
            records = scrape_page(ac["url"], ac["title"])
        except Exception as e:
            print(f"    ✗ exception: {e}")
            failed.append(ac)
            continue

        valid = [r for r in records if r["range_km"] and r["capacity"]]
        if valid:
            # Avoid duplicates when retrying
            existing_names = {d["name"] for d in all_data}
            new = [r for r in valid if r["name"] not in existing_names]
            all_data.extend(new)
            for r in new:
                yr = r["first_flight"] or "?"
                print(f"    ✓ {r['name']}: {r['range_km']:.0f} km, "
                      f"{r['capacity']} pax, {yr}, {r['manufacturer']}")
        else:
            print("    – no usable data")
            failed.append(ac)

    return failed


def main(force: bool = False) -> list[dict]:
    if not force and CACHE.exists():
        print(f"Loading cached data from {CACHE}")
        return json.loads(CACHE.read_text())

    aircraft_list = get_aircraft_list()
    all_data: list[dict] = []

    # First pass
    failed = _scrape_pass(aircraft_list, all_data, pass_num=1)

    # Retry passes with increasing back-off
    for attempt in range(2, MAX_RETRIES + 2):
        if not failed:
            break
        print(f"\n── Retry pass {attempt - 1}: {len(failed)} aircraft to re-try ──")
        failed = _scrape_pass(failed, all_data, pass_num=attempt, extra_delay=0.2)

    # Final failure report
    if failed:
        print(f"\n{'─'*60}")
        print(f"COULD NOT FETCH DATA for {len(failed)} aircraft after {MAX_RETRIES} retries:")
        for ac in failed:
            print(f"  • {ac['title']}  →  {ac['url']}")
        print(f"{'─'*60}")
    else:
        print("\nAll aircraft fetched successfully.")

    all_data = _post_process(all_data)
    print(f"\nTotal: {len(all_data)} aircraft records with range + capacity")
    CACHE.write_text(json.dumps(all_data, indent=2))
    return all_data


def _post_process(data: list[dict]) -> list[dict]:
    """Clean up names, fix manufacturers, remove obvious junk."""
    clean_data = []
    seen: set[tuple] = set()   # (name_lower, manufacturer) dedup

    for rec in data:
        # Clean name: strip citation markers like [34], [*], trailing spaces
        name = re.sub(r"\s*\[[\s\w*]+\]", "", rec["name"]).strip()
        name = re.sub(r"\s{2,}", " ", name)

        # Expand "-N" style variant names (e.g. "-10" → "DC-10-10") using the page URL
        if name.startswith("-"):
            prefix = _family_prefix_from_url(rec.get("url", ""))
            name = prefix + name

        # Strip freighter co-designation suffixes before fixup lookups so that
        # "777-200LR/777F" → "777-200LR" matches _FIRST_FLIGHT_FIXUPS correctly.
        name = re.sub(r"\s*/\s*\d*[A-Z]*[Ff]\b", "", name).strip()

        # Apply marketing-name fixups (e.g. ICAO engine-suffix codes → common names)
        name = _NAME_FIXUPS.get(name, name)

        # Override first_flight for variants that inherit wrong year from shared infobox
        if name in _FIRST_FLIGHT_FIXUPS:
            rec["first_flight"] = _FIRST_FLIGHT_FIXUPS[name]

        rec["name"] = name

        # Fix manufacturer: re-normalize in case it wasn't caught before
        mfr = rec.get("manufacturer") or "Unknown"
        # Catch UAC/Irkut pattern for Superjet/MC-21
        if "united aircraft" in mfr.lower() or ("irkut" in mfr.lower()):
            # Determine brand by aircraft name
            nm = name.lower()
            if "superjet" in nm or "ssj" in nm:
                mfr = "Sukhoi"
            elif "mc-21" in nm or "mc21" in nm:
                mfr = "Irkut"
            else:
                mfr = normalize_manufacturer(mfr)
        elif "tu-204" in mfr.lower() or "aviastar" in mfr.lower() or "kazan" in mfr.lower():
            mfr = "Tupolev"
        elif "veb flugzeugwerke" in mfr.lower():
            mfr = "VEB Dresden"
        elif "british aircraft corporation" in mfr.lower():
            mfr = "BAC"
        rec["manufacturer"] = mfr

        # Fix Tu-144 manufacturer (Tupolev, not Ilyushin)
        if "tu-144" in name.lower() or "144" in name and "tupolev" in name.lower():
            rec["manufacturer"] = "Tupolev"

        # Drop year-only names — some tables use entry-into-service year as column
        # header (e.g. A340 overview table: "1991 [46]" → "1991" after citation strip)
        if re.fullmatch(r"\d{4}", name):
            continue

        # Drop freighter-only variants:
        #   - in the explicit exclusion set
        #   - "freighter" / "cargo" anywhere in the name
        #   - ends with " F" or "-F" (e.g. "MD-11 F")
        #   - ends with a digit followed by F (e.g. "747-8F", "A350F", "A300-600F")
        cap = rec.get("capacity") or 0
        if cap <= 20:          # below 21 is implausible for a commercial airliner
            continue
        if (name in _FREIGHTER_EXCLUSIONS
                or "freighter" in name.lower()
                or "cargo" in name.lower()
                or name.endswith(" F") or name.endswith("-F")
                or bool(re.search(r"\d[Ff]$", name))):
            continue

        # Dedup: strip leading manufacturer prefix so "Airbus A318" and "A318"
        # (both mfr=Airbus) map to the same key → keep whichever arrives first.
        name_lower = name.lower()
        mfr_lower = mfr.lower()
        short_name = name_lower.removeprefix(mfr_lower + " ").strip()
        key = (short_name, mfr_lower)
        if key in seen:
            continue
        seen.add(key)

        rec["body_type"] = "wide" if _is_wide_body(name, rec.get("url", "")) else "narrow"
        clean_data.append(rec)

    return clean_data


if __name__ == "__main__":
    force = "--force" in sys.argv or "--fresh" in sys.argv
    main(force=force)
