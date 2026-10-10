import asyncio
import json
import math
import os
import time
from functools import partial
import re
from contextlib import contextmanager
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from agent_core import (
    search_flights, search_flight_fares, search_trains, search_buses, search_cabs,
    search_hotels, search_villas, search_attractions, search_packages, search_cruises,
    compare_dates, FARE_WINDOW_DAYS, MAX_COMPARE_DAYS,
)

st.set_page_config(page_title="MakeMyTrip Autonomous Agent", page_icon="✈️")

try:  # travel theme: animated cards, glow, step-by-step flow (theme.py)
    from theme import apply_theme, highlight_active, highlight_mode
    apply_theme()
except ImportError:
    def highlight_active(active, col=0):
        pass

    def highlight_mode(sid, idx):
        pass

st.title("✈️ MakeMyTrip Autonomous Web Agent")

TODAY = date.today()
MAX_DATE = TODAY + timedelta(days=330)
FARE_MAX_DATE = TODAY + timedelta(days=300)   # keeps start + 30 days inside the bookable range
MIN_LEISURE_DATE = TODAY + timedelta(days=2)  # attractions / packages / cruises: from today + 2 days
SPINNER = "Agent is searching MakeMyTrip... (may take 1-2 minutes per search)"
MODE_SINGLE = "Single date"
MODE_COMPARE = "Compare multiple dates"
MODE_FARES = "Cheapest fare per date (Fast)"


# ------------------------------------------------------------------ helpers
def clean(text):
    """Text areas wrap long text; collapse any line breaks / extra spaces before searching."""
    return " ".join((text or "").split())


def price_num(text):
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def show_rows(rows, key):
    st.table(rows)
    csv = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Download CSV", csv, file_name=f"{key}.csv", mime="text/csv", key=f"{key}_dl")


def render_fares(p, key):
    data = p["data"]
    fares = data["fares"]
    st.success(
        f"Cheapest fare per date · {p['label']} · "
        f"{data.get('window_start')} → {data.get('window_end')} · {len(fares)} dates found"
    )
    priced = [(price_num(f["lowest_fare"]), f) for f in fares if price_num(f["lowest_fare"]) is not None]
    if priced:
        lo = min(priced, key=lambda x: x[0])
        hi = max(priced, key=lambda x: x[0])
        avg = sum(n for n, _ in priced) / len(priced)
        c1, c2, c3 = st.columns(3)
        c1.metric("Cheapest", lo[1]["lowest_fare"])
        c1.caption(f"{lo[1]['date']} ({lo[1]['weekday']})")
        c2.metric("Most expensive", hi[1]["lowest_fare"])
        c2.caption(f"{hi[1]['date']} ({hi[1]['weekday']})")
        c3.metric("Average", f"₹ {avg:,.0f}")
        c3.caption(f"over {len(priced)} dates")

        by_day = {}
        for n, f in priced:
            by_day.setdefault(f["weekday"], []).append(n)
        best_day = min(by_day, key=lambda k: sum(by_day[k]) / len(by_day[k]))
        st.info(
            f"Planning tip: {best_day} departures are cheapest on average "
            f"(₹ {sum(by_day[best_day]) / len(by_day[best_day]):,.0f}). "
            f"The lowest fare in this window is on {lo[1]['date']}."
        )

        st.markdown("**Fare trend**")
        df = pd.DataFrame({"date": [pd.to_datetime(f["date"]) for _, f in priced],
                           "fare": [n for n, _ in priced]})
        st.bar_chart(df, x="date", y="fare")

        st.markdown("**Top 5 cheapest dates**")
        st.table([{"date": f["date"], "weekday": f["weekday"], "lowest_fare": f["lowest_fare"]}
                  for _, f in sorted(priced, key=lambda x: x[0])[:5]])

    st.markdown("**All dates**")
    show_rows(fares, key)
    if data.get("missing_dates"):
        st.warning("Could not read fares for: " + ", ".join(data["missing_dates"]))


def render(key):
    """Show the last stored result of a service (survives Streamlit reruns)."""
    p = st.session_state.get(key)
    if not p:
        p = restore(key)
        if not p:
            return
        st.session_state[key] = p
        st.caption("ℹ️ Showing your last search result (restored after the page was refreshed).")
    kind = p["kind"]
    if kind == "error":
        st.error("Could not fetch results. Try again.")
        return

    group_info(p)

    if kind == "single":
        data = p["data"]
        items = with_group_total(data[p["list_key"]], p)
        page_date = data.get(p["date_key"], "-") if p["date_key"] else "-"
        st.success(
            f"Found {len(items)} results for {p['label']} · "
            f"requested: {data.get('requested_date', '-')} · date on MakeMyTrip page: {page_date}"
        )
        show_rows(items, key)

    elif kind == "stay":
        data = p["data"]
        items = data[p["list_key"]]
        st.success(
            f"Found {len(items)} results in {p['label']} · "
            f"check-in {data.get('check_in', '-')} → check-out {data.get('check_out', '-')}"
        )
        show_rows(items, key)

    elif kind == "fares":
        render_fares(p, key)

    elif kind == "multi":
        rows = with_group_total(p["rows"], p)
        if rows:
            best = {}
            for r in rows:
                n = price_num(r.get("price", ""))
                if n is not None and (r["requested_date"] not in best or n < best[r["requested_date"]][0]):
                    best[r["requested_date"]] = (n, r["price"])
            st.success(f"Date-wise comparison · {p['label']}")
            if p.get("saved"):
                st.caption(f"All dates saved in ONE file: {p['saved']}")
            st.markdown("**Cheapest option per date**")
            st.table([{"date": d, "cheapest": v[1]} for d, v in sorted(best.items())])
            st.markdown("**All results**")
            show_rows(rows, key)
        if p.get("suspect"):
            st.warning("These dates returned exactly the same flights/prices as the previous date, "
                       "please verify: " + ", ".join(p["suspect"]))
        if p["failed"]:
            st.warning("No result for: " + ", ".join(p["failed"]))
        if not rows:
            st.error("Could not fetch results for any date. Try again.")


@contextmanager
def step(sid, n, title=None):
    """One animated step of the flow (appears only after the previous step is completed)."""
    with st.container(key=f"step_{sid}_{n}"):
        arrow = '<div class="step-arrow">▼</div>' if n > 1 else ""
        label = f'<div class="step-label"><b>{n}</b>{title}</div>' if title else ""
        if arrow or label:
            st.markdown(arrow + label, unsafe_allow_html=True)
        yield


def set_mode(sid, mode):
    st.session_state[f"{sid}_mode"] = mode


def place_box(col, label, key, placeholder):
    return clean(col.text_area(label, key=key, placeholder=placeholder, height=68, max_chars=80))


LAST_DIR = os.path.join("results", "_last")   # last on-screen result of every service
RESTORE_MAX_AGE = 60 * 60                     # restore a saved screen result only if it is < 1 hour old


def keep(state, payload):
    """Put a result on screen AND save it, so it survives a dropped session / page reload."""
    st.session_state[state] = payload
    try:
        os.makedirs(LAST_DIR, exist_ok=True)
        with open(os.path.join(LAST_DIR, f"{state}.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
    except Exception:
        pass


def restore(state):
    """Reload the last saved screen result (used only when the session lost it)."""
    path = os.path.join(LAST_DIR, f"{state}.json")
    try:
        if time.time() - os.path.getmtime(path) > RESTORE_MAX_AGE:
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def store(state, data, **payload):
    keep(state, {"data": data, **payload} if data else {"kind": "error"})


def travellers_step(sid, n, stay=False, cap_total=None, title="Travellers"):
    """Adults / Children (>2 yrs) / Infants (<2 yrs) (+ Rooms and child age for hotels & villas)."""
    with step(sid, n, title):
        cols = st.columns([1, 1, 1, 1, 1] if stay else [1, 1, 1, 2])
        ak, ck, ik = f"{sid}_adults", f"{sid}_children", f"{sid}_infants"
        if ak not in st.session_state:
            st.session_state[ak] = 2 if stay else 1
        if ck not in st.session_state:
            st.session_state[ck] = 0
        if ik not in st.session_state:
            st.session_state[ik] = 0
        adults = int(cols[0].number_input("Adults", min_value=1, max_value=9, step=1, key=ak))
        max_c = 9 if cap_total is None else max(0, cap_total - adults)
        if st.session_state[ck] > max_c:
            st.session_state[ck] = max_c
        children = int(cols[1].number_input("Children (>2 yrs)", min_value=0, max_value=max_c, step=1, key=ck))
        # an infant travels on an adult's lap -> at most 1 infant per adult
        max_i = min(adults, 9)
        if st.session_state[ik] > max_i:
            st.session_state[ik] = max_i
        infants = int(cols[2].number_input("Infants (<2 yrs)", min_value=0, max_value=max_i, step=1, key=ik))
        out = {"adults": adults, "children": children, "infants": infants, "rooms": None, "child_age": None}
        if stay:
            rk = f"{sid}_rooms"
            if rk not in st.session_state:
                st.session_state[rk] = 1
            out["rooms"] = int(cols[3].number_input("Rooms", min_value=1, max_value=5, step=1, key=rk))
            if children:
                ag = f"{sid}_cage"
                if ag not in st.session_state or st.session_state[ag] < 2:
                    st.session_state[ag] = 8
                out["child_age"] = int(cols[4].number_input("Child age (2-17 yrs)", min_value=2, max_value=17,
                                                            step=1, key=ag))
        note = f"👥 Total travellers: {adults + children}"
        if infants:
            note += f" + {infants} infant(s)"
        if cap_total:
            note += f" (max {cap_total} adults + children per search)"
        st.caption(note)
        if infants:
            st.caption("🍼 Infants (under 2 yrs) travel on an adult's lap - max 1 infant per adult.")
    return out


def trav_payload(t):
    return {"adults": t["adults"], "children": t["children"], "infants": t.get("infants", 0),
            "total": t["adults"] + t["children"], "rooms": t.get("rooms")}


def group_info(p):
    """Travellers line + the right note for each service, shown above the results."""
    t, sid = p.get("trav"), p.get("sid")
    if not t:
        return
    txt = f"👥 {t['adults']} adult(s)" + (f" + {t['children']} child(ren) (>2 yrs)" if t["children"] else "")
    txt += f" = {t['total']} traveller(s)"
    if t.get("infants"):
        txt += f" + {t['infants']} infant(s) (<2 yrs)"
    txt += f" · {t['rooms']} room(s)" if t.get("rooms") else ""
    st.caption(txt)
    if sid in ("trains", "buses"):
        st.caption("ℹ️ MakeMyTrip's search does not take a traveller count for this service, so "
                   "'est_total_for_group' is simply price × travellers (an estimate).")
    elif sid == "cabs":
        need = math.ceil(t["total"] / 4)
        st.caption("ℹ️ Cab prices are per vehicle, not per person. " + (
            f"{t['total']} travellers need about {need} cabs of 4 seats, or pick an SUV / 6-7 seater."
            if t["total"] > 4 else "A 4-seater cab is enough for this group."))
    elif sid == "flights":
        st.caption("ℹ️ Fares are as MakeMyTrip shows them for this selection (it may show per person or "
                   "the group total, check on the site).")


def with_group_total(rows, p):
    """trains / buses only: add price × travellers as an estimate column."""
    t = p.get("trav")
    if not t or p.get("sid") not in ("trains", "buses"):
        return rows
    out = []
    for r in rows:
        n = price_num(r.get("price", ""))
        out.append({**r, "est_total_for_group": f"₹ {n * t['total']:,}" if n is not None else "-"})
    return out


# --------------------------------------------------------------------- flows
def travel_flow(s):
    """From/To -> Mode -> Dates -> Search  (flights, trains, buses, cabs)"""
    sid, state = s["id"], f"{s['id']}_result"
    # flights: Single date + Cheapest fare ; trains / buses / cabs: Single date + Compare multiple dates
    modes = [MODE_SINGLE, MODE_FARES] if s.get("fares_fn") else [MODE_SINGLE, MODE_COMPARE]

    with step(sid, 1, "Route"):
        c1, c2, _ = st.columns([1, 1, 2])
        src = place_box(c1, s["from_label"], f"{sid}_from", s["from_ph"])
        dst = place_box(c2, s["to_label"], f"{sid}_to", s["to_ph"])
    if not (src and dst):
        st.caption("Fill both fields to continue.")
        return
    label = f"{src} → {dst}"

    with step(sid, 2, "Mode"):
        st.caption("Choose a mode")
        mcols = st.columns([1, 1.3, 2])
        for i, (c, m) in enumerate(zip(mcols, modes)):
            c.button(m, key=f"mode_{sid}_{i}", on_click=set_mode, args=(sid, m))
        mode = st.session_state.get(f"{sid}_mode")
        if mode in modes:
            highlight_mode(sid, modes.index(mode))
    if mode not in modes:
        return

    with step(sid, 3, "Dates"):
        if mode == MODE_SINGLE:
            c1, _ = st.columns([1, 3])
            d = c1.date_input("Travel date", TODAY + timedelta(days=7), min_value=TODAY,
                              max_value=MAX_DATE, key=f"{sid}_date")
        else:
            fare_mode = mode == MODE_FARES
            c1, c2, _ = st.columns([1, 1, 2])
            start = c1.date_input("From date", TODAY if not fare_mode else TODAY + timedelta(days=7),
                                  min_value=TODAY,
                                  max_value=(FARE_MAX_DATE if fare_mode else MAX_DATE - timedelta(days=MAX_COMPARE_DAYS - 1)),
                                  key=f"{sid}_{'fstart' if fare_mode else 'start'}")
            n = int(c2.number_input("No. of days to compare", min_value=1, max_value=MAX_COMPARE_DAYS,
                                    value=FARE_WINDOW_DAYS if fare_mode else 3, step=1,
                                    key=f"{sid}_{'fdays' if fare_mode else 'days'}"))
            if not fare_mode and s["id"] != "flights" and n > 5:
                st.caption(f"{n} dates = {n} separate searches (about 1-2 minutes each).")
            if fare_mode:
                st.caption("One search reads the cheapest fare of every date in this window.")
            elif n > 10:
                st.info("Long range: keep this tab open until it finishes.")

    trav = travellers_step(sid, 4, cap_total=9 if sid == "flights" else None)
    tp = trav_payload(trav)
    a, c, inf = trav["adults"], trav["children"], trav["infants"]

    with step(sid, 5):
        if mode == MODE_SINGLE:
            btn_label = f"🔍 Search {s['title'].lower()}"
        elif mode == MODE_COMPARE:
            btn_label = f"🔍 Compare {n} date(s)"
        else:
            btn_label = "🔍 Get cheapest fares"
        clicked = st.button(btn_label, key=f"search_{sid}")

    if clicked:
        if mode == MODE_SINGLE:
            with st.spinner(SPINNER):
                data = asyncio.run(s["fn"](src, dst, d, adults=a, children=c, infants=inf))
            store(state, data, kind="single", list_key=s["list_key"], date_key=s["date_key"], label=label,
                  trav=tp, sid=sid)

        elif mode == MODE_COMPARE:
            end = start + timedelta(days=n - 1)
            bar = st.progress(0.0)

            def progress(done, total, text):
                bar.progress(min(done / total, 1.0), text=text)

            merged = asyncio.run(compare_dates(partial(s["fn"], adults=a, children=c, infants=inf), s["service"],
                                               src, dst, start, end, progress))
            bar.empty()
            rows = []
            for block in merged["results"]:
                rows += [{"requested_date": block["requested_date"], **item}
                         for item in block["data"][s["list_key"]]]
            keep(state, {"kind": "multi", "rows": rows, "failed": merged["dates_failed"],
                         "suspect": merged.get("dates_suspect", []),
                         "label": label, "saved": merged.get("saved_file"),
                         "trav": tp, "sid": sid})

        else:  # cheapest fare per date
            with st.spinner(f"Agent is collecting fares for {n} days... (this visits several pages, "
                            "may take several minutes)"):
                data = asyncio.run(s["fares_fn"](src, dst, start, days=n, adults=a, children=c, infants=inf))
            store(state, data, kind="fares", label=label, trav=tp, sid=sid)


def stay_flow(s):
    """City -> Check-in / Check-out -> Search  (hotels, villas)"""
    sid, state = s["id"], f"{s['id']}_result"
    with step(sid, 1, "Destination"):
        c1, _ = st.columns([1, 3])
        city = place_box(c1, "City", f"{sid}_city", s["ph"])
    if not city:
        st.caption("Fill the city to continue.")
        return

    with step(sid, 2, "Dates"):
        c1, c2, _ = st.columns([1, 1, 2])
        cin = c1.date_input("Check-in", TODAY + timedelta(days=7), min_value=TODAY,
                            max_value=MAX_DATE, key=f"{sid}_in")
        cout = c2.date_input("Check-out", TODAY + timedelta(days=8), min_value=TODAY,
                             max_value=MAX_DATE, key=f"{sid}_out")
        valid = cout > cin
        if not valid:
            st.warning("Check-out must be after check-in.")

    trav = travellers_step(sid, 3, stay=True, title="Guests & rooms")
    tp = trav_payload(trav)

    with step(sid, 4):
        clicked = st.button(f"🔍 Search {s['title'].lower()}", key=f"search_{sid}", disabled=not valid)

    if clicked:
        with st.spinner(SPINNER):
            data = asyncio.run(s["fn"](city, cin, cout, adults=trav["adults"], children=trav["children"],
                                       infants=trav["infants"], rooms=trav["rooms"],
                                       child_age=trav["child_age"] or 8))
        store(state, data, kind="stay", list_key=s["list_key"], label=city, trav=tp, sid=sid)


def simple_flow(s):
    """Place -> Date (today + 2 days onwards) -> Search  (attractions, packages, cruises)"""
    sid, state = s["id"], f"{s['id']}_result"
    with step(sid, 1, "Destination"):
        c1, _ = st.columns([1, 3])
        place = place_box(c1, s["field"], f"{sid}_place", s["ph"])
    if not place:
        st.caption("Fill this field to continue.")
        return

    with step(sid, 2, "Date"):
        c1, _ = st.columns([1, 3])
        d = c1.date_input(s["date_label"], TODAY + timedelta(days=14), min_value=MIN_LEISURE_DATE,
                          max_value=MAX_DATE, key=f"{sid}_date")

    trav = travellers_step(sid, 3)
    tp = trav_payload(trav)

    with step(sid, 4):
        clicked = st.button(f"🔍 Search {s['title'].lower()}", key=f"search_{sid}")

    if clicked:
        with st.spinner(SPINNER):
            data = asyncio.run(s["fn"](place, d, adults=trav["adults"], children=trav["children"],
                                infants=trav["infants"]))
        store(state, data, kind="single", list_key=s["list_key"], date_key=s["date_key"], label=place,
              trav=tp, sid=sid)


# ---------------------------------------------------------------- services
SERVICES = [
    dict(id="flights", label="Flights", title="Flights", flow=travel_flow, service="flights",
         from_label="From", to_label="To", from_ph="e.g. Ahmedabad", to_ph="e.g. Delhi",
         fn=search_flights, fares_fn=search_flight_fares, list_key="flights", date_key="travel_date"),
    dict(id="trains", label="Trains", title="Trains", flow=travel_flow, service="trains",
         from_label="From", to_label="To", from_ph="e.g. Ahmedabad", to_ph="e.g. Mumbai",
         fn=search_trains, list_key="trains", date_key="travel_date"),
    dict(id="buses", label="Buses", title="Buses", flow=travel_flow, service="buses",
         from_label="From", to_label="To", from_ph="e.g. Ahmedabad", to_ph="e.g. Mumbai",
         fn=search_buses, list_key="buses", date_key="travel_date"),
    dict(id="cabs", label="Cabs", title="Cabs", flow=travel_flow, service="cabs",
         from_label="Pickup location", to_label="Drop location", from_ph="e.g. Ahmedabad", to_ph="e.g. Vadodara",
         fn=search_cabs, list_key="cabs", date_key="pickup_date"),
    dict(id="hotels", label="Hotels", title="Hotels", flow=stay_flow,
         ph="e.g. Goa", fn=search_hotels, list_key="hotels"),
    dict(id="villas", label="Villas & Homestays", title="Villas & Homestays", flow=stay_flow,
         ph="e.g. Goa", fn=search_villas, list_key="villas"),
    dict(id="attractions", label="Attractions", title="Attractions", flow=simple_flow,
         field="City", ph="e.g. Jaipur", date_label="Visit date (from today + 2 days)",
         fn=search_attractions, list_key="attractions", date_key="date_selected"),
    dict(id="packages", label="Holiday Packages", title="Holiday packages", flow=simple_flow,
         field="Destination", ph="e.g. Kerala", date_label="Travel date (from today + 2 days)",
         fn=search_packages, list_key="packages", date_key="travel_month"),
    dict(id="cruises", label="Cruises", title="Cruises", flow=simple_flow,
         field="Destination", ph="e.g. Singapore", date_label="Travel date (from today + 2 days)",
         fn=search_cruises, list_key="packages", date_key="travel_month"),
]
BY_ID = {s["id"]: s for s in SERVICES}

# ------------------------------------------------------------ 3 x 3 card grid
def set_active(sid):
    """Click a card to open its menu right below it; click it again to close the menu."""
    if st.session_state.get("active") == sid:
        st.session_state["active"] = None
    else:
        st.session_state["active"] = sid
        st.session_state.pop(f"{sid}_mode", None)


def panel(s):
    with st.container(key=f"flow_{s['id']}"):
        st.markdown(f'<div class="flow-title">{s["label"]}</div>', unsafe_allow_html=True)
        s["flow"](s)
    render(f"{s['id']}_result")


active = st.session_state.get("active")
active_row, active_col = None, 0
for idx, s in enumerate(SERVICES):
    if s["id"] == active:
        active_row, active_col = divmod(idx, 3)
highlight_active(active, active_col)

for row in range(3):
    cols = st.columns(3)
    for col, s in zip(cols, SERVICES[row * 3: row * 3 + 3]):
        col.button(s["label"], key=f"svc_{s['id']}", on_click=set_active, args=(s["id"],))
    if row == active_row:
        panel(BY_ID[active])        # the dropdown opens directly under the clicked card's row

if not active:
    st.caption("👆 Pick a service to start.")