"""
SMALL TEST (does NOT touch app.py / agent_core.py): same search on MakeMyTrip and competitor sites,
then compare the prices. Run from the mmt-agent folder with the venv active:

    python competitor_test.py hotels Goa 2026-10-20 2026-10-21
    python competitor_test.py flights Ahmedabad Delhi 2026-10-20
    python competitor_test.py hotels Goa 2026-10-20 2026-10-21 --sites makemytrip,booking

How it runs (to avoid Gemini free-tier 429 errors):
  1. At most 2 sites run at the same time, and each site starts >= 18 seconds after the previous one.
  2. A site that fails or returns nothing is retried automatically, one after another, after a cool-down.
"""
import argparse
import asyncio
import difflib
import json
import os
import re
import shutil
import tempfile
import time
from datetime import date, datetime, timedelta
from typing import List

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")   # no usage-telemetry calls

from dotenv import load_dotenv
from pydantic import BaseModel
from browser_use import Agent, Browser, ChatGoogle

load_dotenv()
MODEL = "gemini-flash-lite-latest"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

MAX_PARALLEL = int(os.environ.get("CMP_PARALLEL", 2))          # sites running at the same time
STAGGER = float(os.environ.get("CMP_STAGGER", 18))             # seconds between two site starts
RETRY_COOLDOWN = float(os.environ.get("CMP_COOLDOWN", 60))     # wait before retrying after a 429


# ------------------------------------------------------------------ schemas
class Flight(BaseModel):
    airline: str
    flight_number: str
    departure_time: str
    price: str


class SiteFlights(BaseModel):
    travel_date: str          # the date shown on the results page
    flights: List[Flight]


class Hotel(BaseModel):
    name: str
    location: str
    rating: str               # exactly as shown, with its scale if visible (4.2/5, 8.4/10 ...)
    price: str                # price shown for the room, exactly as displayed
    price_basis: str          # "per night", "total for stay" or "unknown"
    taxes: str                # "included", "excluded" or "unknown"


class SiteHotels(BaseModel):
    check_in: str
    check_out: str
    hotels: List[Hotel]


class Villa(BaseModel):
    name: str
    location: str
    rating: str
    price: str
    price_basis: str          # "per night", "total for stay" or "unknown"
    taxes: str                # "included", "excluded" or "unknown"
    property_type: str        # villa, homestay, apartment, cottage ...


class SiteVillas(BaseModel):
    check_in: str
    check_out: str
    villas: List[Villa]


class Bus(BaseModel):
    operator: str
    bus_type: str             # AC/Non-AC, Sleeper/Seater
    departure_time: str
    price: str                # lowest seat price shown


class SiteBuses(BaseModel):
    travel_date: str
    buses: List[Bus]


class Train(BaseModel):
    train_name: str
    train_number: str
    departure_time: str
    price: str                # price of the cheapest class shown
    travel_class: str         # class of that price (SL, 3A, CC ...)


class SiteTrains(BaseModel):
    travel_date: str
    trains: List[Train]


class Cab(BaseModel):
    cab_type: str             # Hatchback, Sedan, SUV ...
    price: str
    price_basis: str          # "total trip", "per km" or "unknown"


class SiteCabs(BaseModel):
    pickup_date: str
    cabs: List[Cab]


class Attraction(BaseModel):
    name: str
    rating: str
    price: str
    price_basis: str          # "per person", "per group" or "unknown"


class SiteAttractions(BaseModel):
    date_selected: str        # date picked on the page, or "Not applicable"
    attractions: List[Attraction]


class Package(BaseModel):
    name: str
    duration: str             # e.g. 4N/5D
    price: str
    price_basis: str          # "per person", "total" or "unknown"


class SitePackages(BaseModel):
    travel_month: str         # month/date picked on the page, or "Not applicable"
    packages: List[Package]


class Cruise(BaseModel):
    name: str
    duration: str             # e.g. 3 Nights
    price: str
    price_basis: str          # "per person", "per cabin", "total" or "unknown"


class SiteCruises(BaseModel):
    travel_month: str
    cruises: List[Cruise]


# ------------------------------------------------------------------ helpers
def fmt_t(sec):
    return f"{sec / 60:.1f} min" if sec >= 60 else f"{sec:.0f} s"


def price_num(s):
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None


def norm_flight(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


STOP = {"hotel", "hotels", "the", "by", "and", "resort", "resorts"}


def name_tokens(s):
    return [w for w in re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split() if w not in STOP]


def same_hotel(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return False
    jaccard = len(sa & sb) / len(sa | sb)
    ratio = difflib.SequenceMatcher(None, " ".join(sorted(sa)), " ".join(sorted(sb))).ratio()
    return jaccard >= 0.75 or ratio >= 0.9


def pick_date(label, d):
    return (f"Open the {label} date picker (calendar), use the next-month arrow until {d.strftime('%B %Y')} "
            f"is visible and click day number {d.day}.")


COMMON_RULES = """
    Stay on the same tab the whole time. Do NOT click offers, banners, ads or other products (hotels/flights/etc.
    that you were not asked for). If an extra browser tab opens, close it and return to the results tab.
    Report ONLY what you can actually see on the page; scroll down to load more if needed; if fewer items are
    visible than requested return fewer. Never invent, guess or extrapolate names, numbers or prices.
    Do NOT open an item and do NOT proceed to booking or payment.
"""


# ------------------------------------------------------------------ flights
def flights_task(site_url, p):
    d = p["date"]
    return f"""
    Go to {site_url}.
    If any popup, login modal, cookie banner or app-download dialog appears, close it first.
    Open the Flights search. Trip type 'One Way', 1 adult, Economy.
    Set the origin (From) to '{p['src']}' and select it from the dropdown suggestions.
    Set the destination (To) to '{p['dst']}' and select it from the dropdown suggestions.
    {pick_date('departure', d)} Afterwards read the selected date back and correct it if it is not {d.strftime('%d %b %Y')}.
    Click Search and wait for the flight results to load.
    Read the departure date shown on the results page into travel_date.
    Extract the flights listed (airline, flight number, departure time, price shown for 1 adult), up to 15.
    {COMMON_RULES}
    """


def hotels_task(site_url, p):
    cin, cout = p["check_in"], p["check_out"]
    return f"""
    Go to {site_url}.
    If any popup, sign-in prompt, cookie banner or app-download dialog appears, close it first.
    Open the Hotels / Stays search (hotels, not flights).
    Type '{p['city']}' as the destination and select the matching city from the dropdown suggestions.
    {pick_date('check-in', cin)} Then click check-out day number {cout.day} in {cout.strftime('%B %Y')}.
    Read the selected dates back and correct them if they are not {cin.strftime('%d %b %Y')} to {cout.strftime('%d %b %Y')}.
    Keep 2 adults, 1 room, no children.
    Click Search and wait for the hotel results to load.
    Read the check-in and check-out dates shown on the results page into check_in and check_out.
    Extract the hotels listed, up to 15. For each: name, area/location, rating exactly as shown (with its scale if
    visible), the price shown for the stay exactly as displayed, whether that price is 'per night' or 'total for stay'
    (price_basis), and whether taxes are 'included', 'excluded' or 'unknown'.
    {COMMON_RULES}
    """


def _head(site_url, what):
    return f"""
    Go to {site_url}.
    If any popup, login/sign-in prompt, cookie banner or app-download dialog appears, close it first.
    {what}"""


def villas_task(site_url, p):
    cin, cout = p["check_in"], p["check_out"]
    return _head(site_url, f"""Open the stays search and look for villas / homestays / entire homes
    (use the 'Villas', 'Homestays' or 'Homes' option or filter if the site has one).
    Destination '{p['city']}' (select it from the suggestions).
    {pick_date('check-in', cin)} Then click check-out day number {cout.day} in {cout.strftime('%B %Y')}.
    Read the dates back and correct them if they are not {cin.strftime('%d %b %Y')} to {cout.strftime('%d %b %Y')}.
    2 adults, no children. Click Search and wait for the results.
    Read the check-in and check-out dates shown on the results page into check_in and check_out.
    Extract up to 15 properties: name, area, rating exactly as shown (with scale), price shown exactly as displayed,
    price_basis ('per night' / 'total for stay' / 'unknown'), taxes ('included' / 'excluded' / 'unknown') and the
    property type (villa, homestay, apartment, cottage ...).
    {COMMON_RULES}""")


def buses_task(site_url, p):
    d = p["date"]
    return _head(site_url, f"""Open the Bus tickets search.
    From '{p['src']}' and To '{p['dst']}' (select both from the dropdown suggestions).
    {pick_date('travel', d)} Read the date back and correct it if it is not {d.strftime('%d %b %Y')}.
    Click Search and wait for the buses to load. Read the travel date shown on the results page into travel_date.
    Extract up to 15 buses: operator name, bus type (AC/Non-AC, Sleeper/Seater), departure time, and the lowest seat
    price shown.
    {COMMON_RULES}""")


def trains_task(site_url, p):
    d = p["date"]
    return _head(site_url, f"""Open the Train tickets search (trains, not flights).
    From '{p['src']}' and To '{p['dst']}' (select both from the dropdown suggestions).
    {pick_date('travel', d)} Read the date back and correct it if it is not {d.strftime('%d %b %Y')}.
    Click Search and wait for the trains to load. Read the travel date shown on the results page into travel_date.
    Extract up to 15 trains: train name, train number, departure time, the price of the CHEAPEST class shown
    and that class (SL, 3A, 2A, CC, 2S ...) in travel_class.
    {COMMON_RULES}""")


def cabs_task(site_url, p):
    d = p["date"]
    return _head(site_url, f"""Open the outstation / one-way cab search.
    Pickup '{p['src']}' and drop '{p['dst']}' (select both from the dropdown suggestions).
    {pick_date('pickup', d)} Read the date back and correct it if it is not {d.strftime('%d %b %Y')}. Keep the default pickup time.
    Click Search and wait for the cab options to load. Read the pickup date shown on the results page into pickup_date.
    Extract up to 10 cab options: cab type (Hatchback, Sedan, SUV ...), price exactly as displayed, and price_basis
    ('total trip' / 'per km' / 'unknown').
    {COMMON_RULES}""")


def attractions_task(site_url, p):
    d = p["date"]
    return _head(site_url, f"""Open the 'Things to do' / 'Activities' / 'Tours & attractions' search for '{p['city']}'
    (select the city from the suggestions). If there is a date selector, {pick_date('visit', d)}
    Click Search and wait for the results. Put the date you selected in date_selected, or 'Not applicable' if there is
    no date selector.
    Extract up to 15 activities: name, rating exactly as shown, the (starting) price exactly as displayed, and
    price_basis ('per person' / 'per group' / 'unknown').
    {COMMON_RULES}""")


def packages_task(site_url, p):
    d = p["date"]
    return _head(site_url, f"""Open the Holidays / Holiday packages search.
    Destination '{p['destination']}' (select it from the suggestions). If a departure city is asked, use
    '{p['from_city']}'. If there is a departure date or month selector, choose {d.strftime('%B %Y')}.
    Click Search and wait for the packages to load. Put the month/date you selected in travel_month, or
    'Not applicable' if there is none.
    Extract up to 12 packages: name, duration (like 4N/5D), price exactly as displayed, and price_basis
    ('per person' / 'total' / 'unknown').
    {COMMON_RULES}""")


def cruises_task(site_url, p):
    d = p["date"]
    return _head(site_url, f"""Open the Cruises / Cruise packages search.
    Destination or route '{p['destination']}' (select it from the suggestions if there is a search box).
    If there is a departure date or month selector, choose {d.strftime('%B %Y')}.
    Click Search / view the cruises and wait for the page to load. Put the month/date you selected in travel_month,
    or 'Not applicable' if there is none.
    Extract up to 10 cruises: name, duration (nights), price exactly as displayed, and price_basis
    ('per person' / 'per cabin' / 'total' / 'unknown').
    {COMMON_RULES}""")


# ---- generic comparison helpers (matches use the same shape: label / prices / cheapest_site / saving)
def norm_time(s):
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AaPp][Mm])?", str(s))
    if not m:
        return None
    h, mi, ap = int(m.group(1)), m.group(2), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mi}"


def nights_of(s):
    t = str(s).lower()
    m = re.search(r"(\d+)\s*n(?:ight)?", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*d(?:ay)?", t)
    return int(m.group(1)) - 1 if m else None


def cab_category(s):
    t = str(s).lower()
    for key, cat in (("hatch", "hatchback"), ("sedan", "sedan"), ("suv", "suv"), ("innova", "suv"),
                     ("ertiga", "suv"), ("traveller", "tempo traveller"), ("tempo", "tempo traveller")):
        if key in t:
            return cat
    return re.sub(r"[^a-z0-9 ]", "", t).strip() or None


OP_STOP = {"travels", "travel", "tours", "pvt", "ltd", "private", "limited", "bus", "buses", "services", "transport"}


def op_tokens(s):
    toks = [w for w in re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split() if w not in OP_STOP]
    return toks or re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split()


def _finish(by_site, label, flag=None):
    lo = min(by_site, key=lambda s: by_site[s]["value"])
    hi = max(v["value"] for v in by_site.values())
    m = {"label": label, "prices": by_site, "cheapest_site": lo, "saving": hi - by_site[lo]["value"]}
    if flag:
        m["flag"] = flag
        m["saving"] = None          # prices are not like-for-like, so no saving is claimed
    return m


def compare_fuzzy(results, p, items_key, value_fn=None):
    """Match items of different sites by (approximately) the same name."""
    value_fn = value_fn or (lambda it, p: price_num(it["price"]))
    clusters = []
    for r in results:
        if r["status"] != "OK":
            continue
        for it in r["data"][items_key]:
            v = value_fn(it, p)
            if v is None:
                continue
            info = {"name": it["name"], "text": it["price"], "basis": it.get("price_basis"), "value": v}
            toks = name_tokens(it["name"])
            for c in clusters:
                if r["site"] not in c["by_site"] and same_hotel(toks, c["tokens"]):
                    c["by_site"][r["site"]] = info
                    break
            else:
                clusters.append({"tokens": toks, "by_site": {r["site"]: info}})
    matches, singles = [], {}
    for c in clusters:
        if len(c["by_site"]) >= 2:
            matches.append(_finish(c["by_site"], next(iter(c["by_site"].values()))["name"]))
        else:
            site, info = next(iter(c["by_site"].items()))
            singles.setdefault(site, []).append(info["name"])
    return sorted(matches, key=lambda m: m["label"].lower()), singles


def compare_groups(results, p, items_key, group_fn, label_fn, note_fn=None, skip_fn=None):
    """Group items by a key (train number, cab category, number of nights); keep the cheapest per site."""
    groups = {}
    for r in results:
        if r["status"] != "OK":
            continue
        for it in r["data"][items_key]:
            g, v = group_fn(it), price_num(it["price"])
            if g is None or v is None or (skip_fn and skip_fn(it)):
                continue
            cur = groups.setdefault(g, {}).get(r["site"])
            if cur is None or v < cur["value"]:
                groups[g][r["site"]] = {"name": it.get("name") or it.get("train_name") or it.get("cab_type"),
                                        "text": it["price"], "basis": it.get("price_basis") or (note_fn(it) if note_fn else None),
                                        "value": v}
    matches, singles = [], {}
    for g, by_site in groups.items():
        if len(by_site) >= 2:
            notes = {str(v["basis"]).lower() for v in by_site.values()}
            matches.append(_finish(by_site, label_fn(g), "[price basis/class differs]" if len(notes) > 1 else None))
        else:
            site = next(iter(by_site))
            singles.setdefault(site, []).append(label_fn(g))
    return sorted(matches, key=lambda m: m["label"]), singles


def compare_buses(results, p):
    clusters = []
    for r in results:
        if r["status"] != "OK":
            continue
        for b in r["data"]["buses"]:
            t, v = norm_time(b["departure_time"]), price_num(b["price"])
            if t is None or v is None:
                continue
            toks = op_tokens(b["operator"])
            info = {"name": f"{b['operator']} ({b['bus_type']})", "text": b["price"], "basis": b["bus_type"], "value": v}
            for c in clusters:
                if c["time"] == t and same_hotel(toks, c["tokens"]):
                    cur = c["by_site"].get(r["site"])
                    if cur is None or v < cur["value"]:
                        c["by_site"][r["site"]] = info
                    break
            else:
                clusters.append({"time": t, "tokens": toks, "by_site": {r["site"]: info}})
    matches, singles = [], {}
    for c in clusters:
        label = f"{next(iter(c['by_site'].values()))['name']} {c['time']}"
        if len(c["by_site"]) >= 2:
            matches.append(_finish(c["by_site"], label))
        else:
            singles.setdefault(next(iter(c["by_site"])), []).append(label)
    return sorted(matches, key=lambda m: m["label"].lower()), singles


def compare_trains(results, p):
    return compare_groups(results, p, "trains", lambda t: re.sub(r"\D", "", str(t["train_number"])) or None,
                          lambda g: f"train {g}", note_fn=lambda t: t["travel_class"])


def compare_cabs(results, p):
    return compare_groups(results, p, "cabs", lambda c: cab_category(c["cab_type"]), lambda g: f"cab: {g}",
                          skip_fn=lambda c: "km" in (str(c["price"]) + str(c["price_basis"])).lower())   # per-km rates are not a trip total


def compare_packages(results, p):
    return compare_groups(results, p, "packages", lambda x: nights_of(x["duration"]),
                          lambda g: f"{g} nights (cheapest per site)")


def compare_cruises(results, p):
    return compare_groups(results, p, "cruises", lambda x: nights_of(x["duration"]),
                          lambda g: f"{g} nights (cheapest per site)")


def compare_flights(results, p):
    table = {}
    for r in results:
        if r["status"] != "OK":
            continue
        for f in r["data"]["flights"]:
            n = price_num(f["price"])
            if n is None:
                continue
            table.setdefault(norm_flight(f["flight_number"]), {})[r["site"]] = {
                "price": f["price"], "n": n, "airline": f["airline"], "time": f["departure_time"]}
    matches, singles = [], {}
    for fn, by_site in table.items():
        if len(by_site) >= 2:
            lo = min(by_site, key=lambda s: by_site[s]["n"])
            hi = max(v["n"] for v in by_site.values())
            matches.append({"flight_number": fn, "prices": by_site, "cheapest_site": lo,
                            "saving_vs_dearest": hi - by_site[lo]["n"]})
        else:
            singles.setdefault(next(iter(by_site)), []).append(fn)
    return sorted(matches, key=lambda m: m["flight_number"]), singles


def compare_hotels(results, p, items_key="hotels"):
    nights = max((p["check_out"] - p["check_in"]).days, 1)
    clusters = []   # each: {"tokens": [...], "by_site": {site: info}}
    for r in results:
        if r["status"] != "OK":
            continue
        for h in r["data"][items_key]:
            n = price_num(h["price"])
            if n is None:
                continue
            per_night = round(n / nights) if "total" in str(h["price_basis"]).lower() else n
            info = {"name": h["name"], "price": h["price"], "basis": h["price_basis"], "taxes": h["taxes"],
                    "rating": h["rating"], "per_night": per_night}
            toks = name_tokens(h["name"])
            for c in clusters:
                if r["site"] not in c["by_site"] and same_hotel(toks, c["tokens"]):
                    c["by_site"][r["site"]] = info
                    break
            else:
                clusters.append({"tokens": toks, "by_site": {r["site"]: info}})
    matches, singles = [], {}
    for c in clusters:
        bs = c["by_site"]
        if len(bs) >= 2:
            lo = min(bs, key=lambda s: bs[s]["per_night"])
            hi = max(v["per_night"] for v in bs.values())
            taxes = {str(v["taxes"]).lower() for v in bs.values()}
            matches.append({"hotel": next(iter(bs.values()))["name"], "prices": bs, "cheapest_site": lo,
                            "saving_vs_dearest_per_night": hi - bs[lo]["per_night"],
                            "like_for_like": len(taxes) == 1 and "unknown" not in taxes})
        else:
            site, info = next(iter(bs.items()))
            singles.setdefault(site, []).append(info["name"])
    return sorted(matches, key=lambda m: m["hotel"].lower()), singles


def print_matches(service, matches):
    for m in matches:
        if "label" in m:
            line = " | ".join(f"{s} {v['value']:,}" for s, v in m["prices"].items())
            saving = "not comparable" if m["saving"] is None else f"saves Rs. {m['saving']}"
            print(f"  {m['label'][:40]:<40} {line} -> lowest number: {m['cheapest_site']} "
                  f"({saving}) {m.get('flag', '')}")
            continue
        if service == "flights":
            line = " | ".join(f"{s} {v['price']}" for s, v in m["prices"].items())
            print(f"  {m['flight_number']:<8} {line}  -> cheapest: {m['cheapest_site']} "
                  f"(saves Rs. {m['saving_vs_dearest']} vs dearest)")
        else:
            line = " | ".join(f"{s} {v['per_night']}/night (tax {v['taxes']})" for s, v in m["prices"].items())
            flag = "" if m["like_for_like"] else "  [taxes not comparable]"
            print(f"  {m['hotel'][:34]:<34} {line} -> cheapest: {m['cheapest_site']} "
                  f"(saves Rs. {m['saving_vs_dearest_per_night']}){flag}")


SPECS = {
    "flights": {"sites": {"makemytrip": "makemytrip.com", "cleartrip": "cleartrip.com", "easemytrip": "easemytrip.com"},
                "default": ["makemytrip", "cleartrip", "easemytrip"], "schema": SiteFlights, "items": "flights",
                "task": flights_task, "compare": compare_flights,
                "dedupe": lambda f: (norm_flight(f["flight_number"]), str(f["departure_time"]).strip()),
                "page_date": "travel_date"},
    "hotels": {"sites": {"makemytrip": "makemytrip.com", "booking": "booking.com", "agoda": "agoda.com",
                         "cleartrip": "cleartrip.com"},
               "default": ["makemytrip", "booking", "agoda"], "schema": SiteHotels, "items": "hotels",
               "task": hotels_task, "compare": compare_hotels,
               "dedupe": lambda h: " ".join(sorted(set(name_tokens(h["name"])))),
               "page_date": "check_in"},
}


def _spec(sites, default, schema, items, task, compare, dedupe, page_date):
    return {"sites": sites, "default": default, "schema": schema, "items": items, "task": task,
            "compare": compare, "dedupe": dedupe, "page_date": page_date}


_name_key = lambda x: " ".join(sorted(set(name_tokens(x["name"]))))
SPECS.update({
    "villas": _spec({"makemytrip": "makemytrip.com", "stayvista": "stayvista.com", "airbnb": "airbnb.co.in",
                     "booking": "booking.com"}, ["makemytrip", "stayvista", "airbnb"], SiteVillas, "villas",
                    villas_task, lambda r, p: compare_hotels(r, p, "villas"), _name_key, "check_in"),
    "buses": _spec({"makemytrip": "makemytrip.com", "abhibus": "abhibus.com", "ixigo": "ixigo.com",
                    "redbus": "redbus.in"}, ["makemytrip", "abhibus", "ixigo"], SiteBuses, "buses",
                   buses_task, compare_buses,
                   lambda b: (" ".join(op_tokens(b["operator"])), norm_time(b["departure_time"]), str(b["bus_type"]).lower()),
                   "travel_date"),
    "trains": _spec({"makemytrip": "makemytrip.com", "ixigo": "ixigo.com", "confirmtkt": "confirmtkt.com"},
                    ["makemytrip", "ixigo", "confirmtkt"], SiteTrains, "trains", trains_task, compare_trains,
                    lambda t: re.sub(r"\D", "", str(t["train_number"])) or t["train_name"], "travel_date"),
    "cabs": _spec({"makemytrip": "makemytrip.com", "savaari": "savaari.com", "gozocabs": "gozocabs.com"},
                  ["makemytrip", "savaari", "gozocabs"], SiteCabs, "cabs", cabs_task, compare_cabs,
                  lambda c: (str(c["cab_type"]).lower(), c["price"]), "pickup_date"),
    "attractions": _spec({"makemytrip": "makemytrip.com", "viator": "viator.com", "getyourguide": "getyourguide.com",
                          "thrillophilia": "thrillophilia.com"}, ["makemytrip", "viator", "thrillophilia"],
                         SiteAttractions, "attractions", attractions_task,
                         lambda r, p: compare_fuzzy(r, p, "attractions"), _name_key, "date_selected"),
    "packages": _spec({"makemytrip": "makemytrip.com", "thomascook": "thomascook.in", "yatra": "yatra.com",
                       "thrillophilia": "thrillophilia.com"}, ["makemytrip", "thomascook", "thrillophilia"],
                      SitePackages, "packages", packages_task, compare_packages,
                      lambda x: (_name_key(x), str(x["duration"]).lower()), "travel_month"),
    "cruises": _spec({"makemytrip": "makemytrip.com", "cordelia": "cordeliacruises.com", "thomascook": "thomascook.in"},
                     ["makemytrip", "cordelia", "thomascook"], SiteCruises, "cruises", cruises_task, compare_cruises,
                     lambda x: (_name_key(x), str(x["duration"]).lower()), "travel_month"),
})


# ------------------------------------------------------------------ running
class Gate:
    """At most MAX_PARALLEL sites at once, and starts at least STAGGER seconds apart."""

    def __init__(self):
        self.sem = asyncio.Semaphore(MAX_PARALLEL)
        self.lock = asyncio.Lock()
        self.last_start = None

    async def run(self, make_coro):
        async with self.sem:
            async with self.lock:
                if self.last_start is not None:
                    wait = self.last_start + STAGGER - time.monotonic()
                    if wait > 0:
                        await asyncio.sleep(wait)
                self.last_start = time.monotonic()
            return await make_coro()


async def run_site(spec, site, p, llm):
    t0 = time.time()
    profile = tempfile.mkdtemp(prefix=f"cmp_{site}_")
    browser = Browser(user_data_dir=profile, headless=False)
    out = {"site": site, "status": "FAILED", "seconds": 0.0, "steps": None, "error": None, "data": None,
           "attempts": 1}
    history = None
    try:
        agent = Agent(task=spec["task"](spec["sites"][site], p), llm=llm, browser=browser,
                      max_steps=60, use_vision=True, output_model_schema=spec["schema"])
        history = await agent.run()
        try:
            out["steps"] = history.number_of_steps()
        except Exception:
            pass
        final = history.final_result()
        if final:
            data = json.loads(final)
            items, seen, unique = data.get(spec["items"], []), set(), []
            for it in items:                      # the same item can be listed twice: keep it once
                key = spec["dedupe"](it)
                if key not in seen:
                    seen.add(key)
                    unique.append(it)
            out["duplicates_removed"] = len(items) - len(unique)
            data[spec["items"]] = unique
            out["data"] = data
            out["status"] = "OK" if unique else "EMPTY"
        else:
            out["error"] = "agent returned no result"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        if history is not None and out["status"] != "OK":
            try:
                errs = [str(e) for e in history.errors() if e]
            except Exception:
                errs = []
            if errs:
                out["last_errors"] = [e[:300] for e in errs[-3:]]
                out["error"] = (out["error"] or "list was empty") + " | last errors: " + \
                               " || ".join(e[:120] for e in errs[-2:])
        try:
            await browser.stop()
        except Exception:
            pass
        shutil.rmtree(profile, ignore_errors=True)
        out["seconds"] = round(time.time() - t0, 1)
    return out


def looks_rate_limited(r):
    text = (r.get("error") or "") + " ".join(r.get("last_errors") or [])
    return "429" in text or "RESOURCE_EXHAUSTED" in text


async def main(service, p, sites, label, date_label):
    spec = SPECS[service]
    llm = ChatGoogle(model=MODEL)
    t0 = time.time()

    print(f"\n▶ Phase 1: {len(sites)} sites, at most {MAX_PARALLEL} at a time, starts {STAGGER:.0f}s apart")
    gate = Gate()
    results = await asyncio.gather(*[gate.run(lambda s=s: run_site(spec, s, p, llm)) for s in sites])
    results = list(results)

    failed = [i for i, r in enumerate(results) if r["status"] != "OK"]
    if failed:
        wait = RETRY_COOLDOWN if any(looks_rate_limited(results[i]) for i in failed) else 5
        names = ", ".join(results[i]["site"] for i in failed)
        print(f"\n▶ Phase 2: retrying one after another: {names} (waiting {wait:.0f}s first)")
        await asyncio.sleep(wait)
        for i in failed:
            first_error = results[i]["error"]
            again = await run_site(spec, results[i]["site"], p, llm)
            again["attempts"] = 2
            again["first_error"] = first_error
            again["recovered_by_retry"] = again["status"] == "OK"
            results[i] = again

    wall = round(time.time() - t0, 1)
    matches, singles = spec["compare"](results, p)

    print("\n" + "=" * 70)
    print(f"{service.upper()} | {label} | {date_label}")
    print("=" * 70)
    for r in results:
        n = len(r["data"][spec["items"]]) if r["data"] else 0
        shown = r["data"].get(spec["page_date"], "-") if r["data"] else "-"
        retry = "  (OK after retry)" if r.get("recovered_by_retry") else ""
        print(f"{r['site']:<12} {r['status']:<7} {fmt_t(r['seconds']):>8}  steps={r['steps']}  items={n} "
              f"(dups removed: {r.get('duplicates_removed', 0)})  page_date={shown}{retry}"
              + (f"\n             ERROR: {str(r['error'])[:240]}" if r["error"] and r["status"] != "OK" else ""))
    print(f"\nTotal time: {fmt_t(wall)}   (sum of all sites: {fmt_t(sum(r['seconds'] for r in results))})")
    print(f"Found on 2+ sites: {len(matches)}")
    print_matches(service, matches)
    print("Seen on only ONE site (check these, may be misread): " +
          (" | ".join(f"{k} {len(v)}" for k, v in singles.items()) or "none"))

    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", f"sitetest_{service}_{label}_{date_label}_comparison")
    path = f"{RESULTS_DIR}/{stem}_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"service": service, "label": label, "dates": date_label, "total_seconds": wall,
                   "config": {"max_parallel": MAX_PARALLEL, "stagger_seconds": STAGGER,
                              "retry_cooldown_seconds": RETRY_COOLDOWN},
                   "sites": results, "matched": matches, "only_on_one_site": singles},
                  f, indent=2, ensure_ascii=False, default=str)
    print(f"\n✅ Saved to {path}")


def parse():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="service", required=True)
    shapes = {
        "flights": ["src", "dst", "date"], "buses": ["src", "dst", "date"], "trains": ["src", "dst", "date"],
        "cabs": ["src", "dst", "date"], "hotels": ["city", "check_in", "check_out"],
        "villas": ["city", "check_in", "check_out"], "attractions": ["city", "date"],
        "packages": ["destination", "date"], "cruises": ["destination", "date"],
    }
    for name, args in shapes.items():
        sp = sub.add_parser(name)
        for a in args:
            sp.add_argument(a)
        sp.add_argument("--sites", default="")
        if name == "packages":
            sp.add_argument("--from-city", default="Ahmedabad", help="departure city for holiday packages")
    a = ap.parse_args()
    spec = SPECS[a.service]
    sites = [s.strip() for s in a.sites.split(",") if s.strip()] or spec["default"]
    bad = [s for s in sites if s not in spec["sites"]]
    if bad:
        raise SystemExit(f"Unknown sites {bad}. Choose from: {', '.join(spec['sites'])}")
    today = date.today()
    v = vars(a)
    try:
        if "check_in" in v:
            cin, cout = date.fromisoformat(a.check_in), date.fromisoformat(a.check_out)
            if cin < today or cout <= cin or (cout - cin).days > 10:
                raise SystemExit("Check-in must be today or later, check-out after check-in, at most 10 nights.")
            return a.service, {"city": a.city, "check_in": cin, "check_out": cout}, sites, a.city, \
                f"{cin.isoformat()}_To_{cout.isoformat()}"
        d = date.fromisoformat(a.date)
    except ValueError:
        raise SystemExit("Dates must look like YYYY-MM-DD, e.g. 2026-10-20")
    if d < today:
        raise SystemExit("Use today or a later date.")
    if a.service in ("attractions", "packages", "cruises") and d < today + timedelta(days=2):
        raise SystemExit("For this service use a date from today + 2 days.")
    if a.service in ("flights", "buses", "trains", "cabs"):
        return a.service, {"src": a.src, "dst": a.dst, "date": d}, sites, f"{a.src}_to_{a.dst}", d.isoformat()
    if a.service == "attractions":
        return a.service, {"city": a.city, "date": d}, sites, a.city, d.isoformat()
    p = {"destination": a.destination, "date": d}
    if a.service == "packages":
        p["from_city"] = a.from_city
    return a.service, p, sites, a.destination, d.isoformat()


if __name__ == "__main__":
    service, p, sites, label, date_label = parse()
    asyncio.run(main(service, p, sites, label, date_label))
