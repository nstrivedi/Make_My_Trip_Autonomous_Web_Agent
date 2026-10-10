import json
import os
import re
from datetime import datetime, date, timedelta
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel
from browser_use import Agent, ChatGoogle

load_dotenv()

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

MODEL = "gemini-flash-lite-latest"
MAX_STEPS = 80            # normal search (date selection needs a few extra steps)
FARE_WINDOW_DAYS = 30     # "cheapest fare" view covers start date + 30 days
MAX_COMPARE_DAYS = 30     # multi-date comparison: up to ~1 month
FAST_CHUNK_DAYS = 6       # flights fast mode: dates handled per agent run
FALLBACK_MAX = 3          # flights fast mode: max dates re-tried with the slow method


# =====================================================================
# Helpers
# =====================================================================
def _default_date(d: Optional[date], days_ahead: int = 7) -> date:
    return d if d else date.today() + timedelta(days=days_ahead)


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y (%A)")


def _pick_date(field: str, d: date) -> str:
    """Prompt text that tells the agent exactly how to set a date."""
    return (
        f"Open the {field} date picker (calendar). Use the next-month arrow until "
        f"{d.strftime('%B %Y')} is visible, then click day number {d.day}. "
        f"Afterwards read the selected date back from the page and make sure it is "
        f"{_fmt(d)}; if it is different, correct it before searching."
    )


def _trav(adults: int, children: int, rooms=None, child_age=None) -> dict:
    """Travellers block stored in every result / JSON file."""
    d = {"adults": int(adults), "children": int(children), "total": int(adults) + int(children)}
    if rooms:
        d["rooms"] = int(rooms)
    if child_age is not None and int(children) > 0:
        d["child_age_years"] = int(child_age)
    return d


def _flight_travellers(adults: int, children: int) -> str:
    return (f"Open the TRAVELLERS & CLASS selector and set Adults to {adults} and Children (2-12 yrs) to "
            f"{children}; keep Infants at 0 and the class on Economy; then click Apply / Done.")


def _guests_instr(adults: int, children: int, rooms: int, child_age: int) -> str:
    kids = f" and {children} child(ren) (each child aged {child_age} years)" if children else ""
    return (f"Open the 'Rooms & Guests' selector. Set Rooms to {rooms} and spread {adults} adult(s){kids} "
            f"across the rooms as evenly as possible (every room needs at least 1 adult). Click Apply.")


def _optional_guests(adults: int, children: int) -> str:
    return (f"If the page has a travellers / guests selector, set Adults to {adults} and Children to {children}. "
            f"If there is none, skip this step.")


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


def _price_num(text) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def _save(data: dict, stem: str) -> str:
    """Write one JSON file in results/ as <stem>_<timestamp>.json and return its path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{RESULTS_DIR}/{_safe(stem)}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved to {filename}")
    return filename


async def _agent_json(task: str, schema, extra: Optional[dict] = None, max_steps: int = MAX_STEPS):
    """Run one agent task and return the parsed JSON (no file is written here)."""
    llm = ChatGoogle(model=MODEL)
    agent = Agent(
        task=task,
        llm=llm,
        max_steps=max_steps,
        use_vision=True,
        output_model_schema=schema,
    )
    result = await agent.run()
    final = result.final_result()
    if not final:
        return None
    try:
        data = json.loads(final)
    except json.JSONDecodeError:
        print("⚠️ Agent returned invalid JSON")
        return None
    if extra:
        data.update(extra)
    return data


async def _run(task: str, schema, stem: str, extra: Optional[dict] = None,
               save: bool = True, max_steps: int = MAX_STEPS):
    data = await _agent_json(task, schema, extra, max_steps)
    if data and save:
        _save(data, stem)
    return data


# =====================================================================
# Multi-date comparison -> ONE merged JSON file
# =====================================================================
def _save_merged(service, src, dst, start, end, blocks, failed, extra=None):
    """Merge everything (date order) and save ONE file:
        <service>_<src>_to_<dst>_<first>_To_<last>_<timestamp>.json
    e.g. flights_Ahmedabad_to_Delhi_2026-10-04_To_2026-10-06_20261004_115640.json
    """
    merged = {
        "service": service,
        "from": src,
        "to": dst,
        "first_date": start.isoformat(),
        "last_date": end.isoformat(),
        "dates_compared": [b["requested_date"] for b in blocks],
        "dates_failed": failed,
    }
    if extra:
        merged.update(extra)
    trav = next((b["data"].get("travellers") for b in blocks if b["data"].get("travellers")), None)
    if trav:
        merged["travellers"] = trav
    merged["results"] = blocks  # one block per date, in date sequence
    if blocks:
        path = _save(merged, f"{service}_{src}_to_{dst}_{start.isoformat()}_To_{end.isoformat()}")
        merged = dict(merged, saved_file=path)
    return merged


async def compare_dates(fn, service: str, src: str, dst: str, start: date, end: date,
                        progress_cb=None):
    """
    Compare every date from `start` to `end` (max MAX_COMPARE_DAYS) and save ONE merged file.
    progress_cb(done, total, text) is called while running.
    Flights use the fast URL-date-swap method; other services search each date separately.
    """
    if service == "flights":
        return await _compare_flights_fast(src, dst, start, end, progress_cb)

    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    blocks, failed = [], []
    for i, d in enumerate(dates):
        if progress_cb:
            progress_cb(i, len(dates), f"Searching {d:%d %b %Y} ({i + 1}/{len(dates)})...")
        try:
            data = await fn(src, dst, d, save=False)
        except Exception as e:  # keep going with the remaining dates
            print(f"⚠️ {d.isoformat()} failed: {e}")
            data = None
        if data:
            blocks.append({"requested_date": d.isoformat(), "data": data})
        else:
            failed.append(d.isoformat())
    return _save_merged(service, src, dst, start, end, blocks, failed, {"method": "one_search_per_date"})


# =====================================================================
# Flights
# =====================================================================
class Flight(BaseModel):
    airline: str
    flight_number: str
    departure_date: str   # date of the flight, as shown on the results page
    departure_time: str
    price: str


class FlightResults(BaseModel):
    from_city: str
    to_city: str
    travel_date: str      # date read back from the results page
    flights: List[Flight]


class FareDay(BaseModel):
    date: str             # ISO format YYYY-MM-DD
    lowest_fare: str


class FareCalendarResults(BaseModel):
    from_city: str
    to_city: str
    fares: List[FareDay]


def _flight_steps(from_city, to_city, d, adults=1, children=0):
    return f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Flights' tab if not already selected. Trip type must be 'One Way'.
    In the 'From' field, type '{from_city}' and select it from the dropdown suggestions.
    In the 'To' field, type '{to_city}' and select it from the dropdown suggestions.
    {_pick_date('Departure', d)}
    {_flight_travellers(adults, children)}
    Click the Search button.
    Wait for results to load.
    """


async def search_flights(from_city: str, to_city: str, travel_date: Optional[date] = None,
                         save: bool = True,
        adults: int = 1, children: int = 0):
    d = _default_date(travel_date)
    task = _flight_steps(from_city, to_city, d, adults, children) + """
    Read the DEPART date shown in the search bar at the top of the results page and put it in travel_date.
    Extract the top 5 flight results with airline name, flight number, departure time, and price.
    For every flight set departure_date to that same travel date.
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, FlightResults,
        f"flights_{from_city}_to_{to_city}_{d.isoformat()}",
        {"requested_date": d.isoformat(), "travellers": _trav(adults, children)}, save,
    )


# ---------- Fast multi-date comparison (change the date in the results URL) ----------
class DayFlight(BaseModel):
    airline: str
    flight_number: str
    departure_time: str
    price: str


class DayFlights(BaseModel):
    date: str            # ISO format YYYY-MM-DD
    flights: List[DayFlight]


class MultiDayFlights(BaseModel):
    from_city: str
    to_city: str
    days: List[DayFlights]


def _fast_chunk_task(src: str, dst: str, dates: List[date]) -> str:
    first, rest = dates[0], dates[1:]
    rest_lines = "\n".join(
        f"      - {d.isoformat()}  (URL format {d.strftime('%d/%m/%Y')})" for d in rest
    ) or "      (none)"
    return f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Flights' tab if not already selected. Trip type must be 'One Way'.
    In the 'From' field, type '{src}' and select it from the dropdown suggestions.
    In the 'To' field, type '{dst}' and select it from the dropdown suggestions.
    {_pick_date('Departure', first)}
    Click the Search button and wait for the results to load.

    DATE 1 ({first.isoformat()}): read the DEPART date in the search bar to confirm it, then record the top 5
    flights (airline, flight number, departure time, price).

    OTHER DATES, in this order:
{rest_lines}
    For each of them:
      1. The current page URL contains 'itinerary=<FROM>-<TO>-DD/MM/YYYY'. Navigate (same tab) to the same URL
         with ONLY that DD/MM/YYYY replaced by the target date.
      2. Wait about 4 seconds, check that the DEPART date in the search bar is the target date, then record the
         top 5 flights.
      3. If changing the URL does not work, set the date with the calendar on the results page and search again.
    Report every date in ISO format YYYY-MM-DD. Do not skip a date.
    Do NOT click any flight and do NOT proceed to booking or payment.
    """


async def _compare_flights_fast(src: str, dst: str, start: date, end: date, progress_cb=None):
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    chunks = [dates[i:i + FAST_CHUNK_DAYS] for i in range(0, len(dates), FAST_CHUNK_DAYS)]
    total = len(dates)
    found, names, done = {}, {}, 0

    # 1) fast pass: one agent run per chunk of dates
    for ci, chunk in enumerate(chunks):
        if progress_cb:
            progress_cb(done, total, f"Fast search {chunk[0]:%d %b} → {chunk[-1]:%d %b} "
                                     f"(part {ci + 1}/{len(chunks)})...")
        try:
            raw = await _agent_json(_fast_chunk_task(src, dst, chunk), MultiDayFlights,
                                    max_steps=60 + 12 * len(chunk))
        except Exception as e:
            print(f"⚠️ chunk {ci + 1} failed: {e}")
            raw = None
        if raw:
            names = {"from_city": raw.get("from_city", src), "to_city": raw.get("to_city", dst)}
            wanted = set(chunk)
            for day in raw.get("days", []):
                d = _parse_fare_date(day.get("date", ""), chunk[0])
                if d in wanted and day.get("flights"):
                    found[d] = [dict(f, departure_date=d.isoformat()) for f in day["flights"]]
        done += len(chunk)

    # 2) slow fallback for a few dates the fast pass missed
    missing = [d for d in dates if d not in found]
    for d in missing[:FALLBACK_MAX]:
        if progress_cb:
            progress_cb(total, total, f"Re-trying {d:%d %b %Y} with the normal method...")
        try:
            data = await search_flights(src, dst, d, save=False)
        except Exception as e:
            print(f"⚠️ fallback {d.isoformat()} failed: {e}")
            data = None
        if data and data.get("flights"):
            names = names or {"from_city": data.get("from_city", src), "to_city": data.get("to_city", dst)}
            found[d] = data["flights"]

    # 3) build blocks in date order + flag dates that look copied from the previous date
    blocks, failed, suspect, prev_key = [], [], [], None
    for d in dates:
        if d not in found:
            failed.append(d.isoformat())
            continue
        flights = found[d]
        key = sorted((f.get("flight_number", ""), f.get("price", "")) for f in flights)
        if key == prev_key:
            suspect.append(d.isoformat())
        prev_key = key
        blocks.append({"requested_date": d.isoformat(), "data": {
            "from_city": names.get("from_city", src), "to_city": names.get("to_city", dst),
            "travel_date": d.isoformat(), "requested_date": d.isoformat(), "flights": flights}})

    return _save_merged("flights", src, dst, start, end, blocks, failed,
                        {"method": "fast_url_date_swap", "dates_suspect": suspect})


# ---------- Cheapest fare per date, next ~1 month ----------
def _parse_fare_date(text: str, ref: date) -> Optional[date]:
    t = str(text).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    # no year given, e.g. 'Sat, Sep 19' or '19 Sep'
    for fmt in ("%a, %b %d %Y", "%b %d %Y", "%d %b %Y", "%a, %d %b %Y"):
        for year in (ref.year, ref.year + 1):
            try:
                d = datetime.strptime(f"{t} {year}", fmt).date()
            except ValueError:
                continue
            if d >= ref - timedelta(days=7):
                return d
    return None


def _build_fare_calendar(raw: dict, start: date, days: int = FARE_WINDOW_DAYS) -> dict:
    """Clean the agent output: ISO dates, de-duplicate, keep only the `days` dates from start, sort."""
    end = start + timedelta(days=days - 1)
    best = {}
    for f in raw.get("fares", []):
        d = _parse_fare_date(f.get("date", ""), start)
        if not d or d < start or d > end:
            continue
        n = _price_num(f.get("lowest_fare", ""))
        old = best.get(d)
        if old is None or (n is not None and (old[0] is None or n < old[0])):
            best[d] = (n, f.get("lowest_fare", ""))

    rows = [
        {"date": d.isoformat(), "weekday": d.strftime("%a"), "lowest_fare": v[1]}
        for d, v in sorted(best.items())
    ]
    missing = [
        (start + timedelta(days=i)).isoformat()
        for i in range(days)
        if (start + timedelta(days=i)) not in best
    ]
    out = {k: v for k, v in raw.items() if k != "fares"}
    out.update({
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "fares": rows,
        "missing_dates": missing,
    })
    priced = [(v[0], d) for d, v in best.items() if v[0] is not None]
    if priced:
        lo = min(priced)
        out["cheapest_date"] = lo[1].isoformat()
        out["cheapest_fare"] = best[lo[1]][1]
    return out


async def search_flight_fares(from_city: str, to_city: str, travel_date: Optional[date] = None,
                              save: bool = True, days: int = FARE_WINDOW_DAYS,
                              adults: int = 1, children: int = 0):
    """Cheapest fare for `days` dates (1..30), starting from the chosen date."""
    d = _default_date(travel_date)
    days = max(1, min(int(days), FARE_WINDOW_DAYS))
    end = d + timedelta(days=days - 1)
    task = _flight_steps(from_city, to_city, d, adults, children) + f"""
    Now collect the LOWEST FARE for every date from {d.isoformat()} to {end.isoformat()} ({days} days).
    Above the flight list there is a row of date tabs; each tab shows a date and its lowest fare
    (for example 'Sat, Sep 19  ₹6,240').
    1. Read every date tab that is visible right now.
    2. The current page URL contains 'itinerary=<FROM>-<TO>-DD/MM/YYYY'. To see later dates, navigate
       (in the same tab) to the same URL with ONLY that DD/MM/YYYY replaced by the date right after the last
       date you have already read. Wait about 4 seconds, then read the date tabs again.
    3. Repeat step 2 until you have read dates up to {end.strftime('%d/%m/%Y')}.
    4. If changing the URL does not work, click the right arrow at the end of the date-tab row instead.
    Report every date in ISO format YYYY-MM-DD (use the year from the URL) together with its lowest fare
    exactly as shown. Do not report a date twice.
    Do NOT click any flight and do NOT proceed to booking or payment. Stop once {end.isoformat()} is covered.
    """
    raw = await _agent_json(task, FareCalendarResults,
                            {"requested_date": d.isoformat(), "travellers": _trav(adults, children)}, max(60, 40 + 3 * days))
    if not raw:
        return None
    data = _build_fare_calendar(raw, d, days)
    if save:
        _save(data, f"flightfares_{from_city}_to_{to_city}_{d.isoformat()}_To_{end.isoformat()}")
    return data


# =====================================================================
# Trains
# =====================================================================
class Train(BaseModel):
    train_name: str
    train_number: str
    departure_date: str
    departure_time: str
    arrival_time: str
    price: str


class TrainResults(BaseModel):
    from_city: str
    to_city: str
    travel_date: str
    trains: List[Train]


async def search_trains(from_city: str, to_city: str, travel_date: Optional[date] = None,
                        save: bool = True,
        adults: int = 1, children: int = 0):
    d = _default_date(travel_date)
    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Trains' tab.
    In the 'From' field, type '{from_city}' and select it from the dropdown suggestions.
    In the 'To' field, type '{to_city}' and select it from the dropdown suggestions.
    {_pick_date('Travel', d)}
    Click the Search button.
    Wait for results to load.
    Read the travel date shown on the results page and put it in travel_date.
    Extract the top 5 train results with train name, train number, departure time, arrival time, and price.
    For every train set departure_date to that travel date.
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, TrainResults,
        f"trains_{from_city}_to_{to_city}_{d.isoformat()}",
        {"requested_date": d.isoformat(), "travellers": _trav(adults, children)}, save,
    )


# =====================================================================
# Buses
# =====================================================================
class Bus(BaseModel):
    operator: str
    bus_type: str
    departure_date: str
    departure_time: str
    duration: str
    price: str


class BusResults(BaseModel):
    from_city: str
    to_city: str
    travel_date: str
    buses: List[Bus]


async def search_buses(from_city: str, to_city: str, travel_date: Optional[date] = None,
                       save: bool = True,
        adults: int = 1, children: int = 0):
    d = _default_date(travel_date, 3)
    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Buses' tab.
    In the 'From' field, type '{from_city}' and select it from the dropdown suggestions.
    In the 'To' field, type '{to_city}' and select it from the dropdown suggestions.
    {_pick_date('Travel', d)}
    Click the Search button.
    Wait for results to load.
    Read the travel date shown on the results page and put it in travel_date.
    Extract the top 5 bus results with operator name, bus type (AC/Non-AC/Sleeper), departure time, journey duration, and price.
    For every bus set departure_date to the travel date.
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, BusResults,
        f"buses_{from_city}_to_{to_city}_{d.isoformat()}",
        {"requested_date": d.isoformat(), "travellers": _trav(adults, children)}, save,
    )


# =====================================================================
# Cabs
# =====================================================================
class Cab(BaseModel):
    cab_type: str
    provider: str
    price: str
    eta: str


class CabResults(BaseModel):
    from_location: str
    to_location: str
    pickup_date: str
    cabs: List[Cab]


async def search_cabs(from_location: str, to_location: str, travel_date: Optional[date] = None,
                      save: bool = True,
        adults: int = 1, children: int = 0):
    d = _default_date(travel_date, 2)
    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Cabs' tab.
    In the 'From' / pickup location field, type '{from_location}' and select it from the dropdown suggestions.
    In the 'To' / drop location field, type '{to_location}' and select it from the dropdown suggestions.
    {_pick_date('Pickup', d)}
    Keep the default pickup time.
    Click the Search button.
    Wait for results to load.
    Read the pickup date shown on the results page and put it in pickup_date.
    Extract the top 5 cab results with cab type (e.g. Sedan, SUV, Hatchback), provider/operator name if visible, price, and estimated pickup time (ETA).
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, CabResults,
        f"cabs_{from_location}_to_{to_location}_{d.isoformat()}",
        {"requested_date": d.isoformat(), "travellers": _trav(adults, children)}, save,
    )


# =====================================================================
# Hotels
# =====================================================================
class Hotel(BaseModel):
    name: str
    location: str
    rating: str
    price_per_night: str


class HotelResults(BaseModel):
    city: str
    check_in: str
    check_out: str
    hotels: List[Hotel]


async def search_hotels(city: str, check_in: Optional[date] = None,
                        check_out: Optional[date] = None, save: bool = True,
                        adults: int = 2, children: int = 0, rooms: int = 1, child_age: int = 8):
    cin = _default_date(check_in)
    cout = check_out if check_out and check_out > cin else cin + timedelta(days=1)
    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Hotels' tab.
    In the city/destination field, type '{city}' and select it from the dropdown suggestions.
    {_pick_date('Check-In', cin)}
    {_pick_date('Check-Out', cout)}
    {_guests_instr(adults, children, rooms, child_age)}
    Click the Search button.
    Wait for results to load.
    Read the check-in and check-out dates shown on the results page and put them in check_in and check_out.
    Extract the top 5 hotel results with hotel name, location/area, rating, and price per night.
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, HotelResults,
        f"hotels_{city}_{cin.isoformat()}",
        {"requested_check_in": cin.isoformat(), "requested_check_out": cout.isoformat(),
         "travellers": _trav(adults, children, rooms, child_age)}, save,
    )


# =====================================================================
# Villas & Homestays
# =====================================================================
class Villa(BaseModel):
    name: str
    location: str
    rating: str
    price_per_night: str
    property_type: str  # e.g. "Villa", "Homestay", "Cottage"


class VillaResults(BaseModel):
    city: str
    check_in: str
    check_out: str
    villas: List[Villa]


async def search_villas(city: str, check_in: Optional[date] = None,
                        check_out: Optional[date] = None, save: bool = True,
                        adults: int = 2, children: int = 0, rooms: int = 1, child_age: int = 8):
    cin = _default_date(check_in)
    cout = check_out if check_out and check_out > cin else cin + timedelta(days=1)
    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Hotels' tab.
    In the city/destination field, type '{city}' and select it from the dropdown suggestions.
    {_pick_date('Check-In', cin)}
    {_pick_date('Check-Out', cout)}
    {_guests_instr(adults, children, rooms, child_age)}
    Click the Search button.
    Wait for results to load.
    Look for a filter or category option labeled 'Villas', 'Homestays', or 'Alternate Accommodation' in the property type filters on the left side of the results page, and apply it.
    If no such filter exists, look for properties in the results whose type is Villa, Homestay, or Cottage.
    Read the check-in and check-out dates shown on the results page and put them in check_in and check_out.
    Extract the top 5 villa/homestay results with property name, location/area, rating, price per night, and property type.
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, VillaResults,
        f"villas_{city}_{cin.isoformat()}",
        {"requested_check_in": cin.isoformat(), "requested_check_out": cout.isoformat(),
         "travellers": _trav(adults, children, rooms, child_age)}, save,
    )


# =====================================================================
# Attractions
# =====================================================================
class Attraction(BaseModel):
    name: str
    description: str
    rating: str
    price: str


class AttractionResults(BaseModel):
    city: str
    date_selected: str  # date picked on the page, or 'Not applicable'
    attractions: List[Attraction]


async def search_attractions(city: str, visit_date: Optional[date] = None, save: bool = True,
        adults: int = 1, children: int = 0):
    d = _default_date(visit_date, 14)
    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Things To Do' or 'Tours & Attractions' tab/section (it may also be under 'Holidays' menu).
    In the city/destination field, type '{city}' and select it from the dropdown suggestions.
    If the page has a date selector, {_pick_date('visit', d)}
    {_optional_guests(adults, children)}
    Click the Search button.
    Wait for results to load.
    Put the date you selected in date_selected. If no date selector exists anywhere, write 'Not applicable'.
    Extract the top 5 attraction/activity results with name, short description, rating, and price.
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, AttractionResults,
        f"attractions_{city}_{d.isoformat()}",
        {"requested_date": d.isoformat(), "travellers": _trav(adults, children)}, save,
    )


# =====================================================================
# Holiday Packages
# =====================================================================
class Package(BaseModel):
    name: str
    duration: str
    inclusions: str
    price: str


class PackageResults(BaseModel):
    destination: str
    travel_month: str  # month/date selected on the page, or 'Not applicable'
    packages: List[Package]


async def search_packages(destination: str, travel_date: Optional[date] = None, save: bool = True,
        adults: int = 1, children: int = 0):
    d = _default_date(travel_date, 30)
    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Holidays' tab.
    In the destination field, type '{destination}' and select it from the dropdown suggestions.
    If there is a departure date or month selector, choose {d.strftime('%B %Y')} (day {d.day} if a day is asked for).
    {_optional_guests(adults, children)}
    Click the Search button.
    Wait for results to load.
    Put the month/date you selected in travel_month. If there is no such selector, write 'Not applicable'.
    Extract the top 5 holiday package results with package name, duration (nights/days), key inclusions, and price.
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, PackageResults,
        f"packages_{destination}_{d.isoformat()}",
        {"requested_date": d.isoformat(), "travellers": _trav(adults, children)}, save,
    )


# =====================================================================
# Cruises
# =====================================================================
class CruisePackage(BaseModel):
    name: str
    duration: str
    destination: str
    price: str


class CruiseResults(BaseModel):
    search_type: str
    travel_month: str  # month/date selected on the page, or 'Not applicable'
    packages: List[CruisePackage]


async def search_cruises(destination: str, travel_date: Optional[date] = None, save: bool = True,
        adults: int = 1, children: int = 0):
    d = _default_date(travel_date, 30)
    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Look for the 'Holidays' tab or menu option and click it.
    If there is a search bar, search for 'Cruise packages {destination}'.
    If a direct search is not possible, navigate to the cruise packages section.
    If there is a departure date or month selector, choose {d.strftime('%B %Y')}.
    {_optional_guests(adults, children)}
    Wait for the page to load.
    Put the month/date you selected in travel_month. If there is no such selector, write 'Not applicable'.
    Extract the top 5 cruise package results with package name, duration, destination, and price.
    Do NOT proceed to booking or payment.
    """
    return await _run(
        task, CruiseResults,
        f"cruises_{destination}_{d.isoformat()}",
        {"requested_date": d.isoformat(), "travellers": _trav(adults, children)}, save,
    )
