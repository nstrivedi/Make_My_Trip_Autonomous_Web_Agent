import streamlit as st
import asyncio
from agent_core import search_flights, search_buses, search_trains, search_cabs, search_hotels, search_villas, search_attractions, search_packages, search_cruises

st.set_page_config(page_title="MakeMyTrip Autonomous Agent", page_icon="✈️")
st.title("✈️ MakeMyTrip Autonomous Web Agent")

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(["🛫 Flights", "🚆 Trains", "🚌 Buses", "🚕 Cabs", "🏨 Hotels", "🏡 Villas & Homestays", "🎟️ Attractions", "🧳 Holiday Packages", "🚢 Cruises"])

with tab1:
    st.subheader("Flight Search")
    col1, col2 = st.columns(2)
    from_city = col1.text_input("From", "Ahmedabad", key="flight_from")
    to_city = col2.text_input("To", "Delhi", key="flight_to")

    if st.button("Search Flights"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_flights(from_city, to_city))
        if result:
            st.success(f"Found {len(result['flights'])} flights from {result['from_city']} to {result['to_city']}")
            st.table(result["flights"])
        else:
            st.error("Could not fetch results. Try again.")

with tab2:
    st.subheader("Train Search")
    col1, col2 = st.columns(2)
    train_from = col1.text_input("From", "Ahmedabad", key="train_from")
    train_to = col2.text_input("To", "Mumbai", key="train_to")

    if st.button("Search Trains"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_trains(train_from, train_to))
        if result:
            st.success(f"Found {len(result['trains'])} trains from {result['from_city']} to {result['to_city']}")
            st.table(result["trains"])
        else:
            st.error("Could not fetch results. Try again.")

with tab3:
    st.subheader("Bus Search")
    col1, col2 = st.columns(2)
    bus_from = col1.text_input("From", "Ahmedabad", key="bus_from")
    bus_to = col2.text_input("To", "Mumbai", key="bus_to")

    if st.button("Search Buses"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_buses(bus_from, bus_to))
        if result:
            st.success(f"Found {len(result['buses'])} buses from {result['from_city']} to {result['to_city']}")
            st.table(result["buses"])
        else:
            st.error("Could not fetch results. Try again.")

with tab4:
    st.subheader("Cab Search")
    col1, col2 = st.columns(2)
    cab_from = col1.text_input("Pickup Location", "Ahmedabad")
    cab_to = col2.text_input("Drop Location", "Vadodara")

    if st.button("Search Cabs"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_cabs(cab_from, cab_to))
        if result:
            st.success(f"Found {len(result['cabs'])} cabs from {result['from_location']} to {result['to_location']}")
            st.table(result["cabs"])
        else:
            st.error("Could not fetch results. Try again.")


with tab5:
    st.subheader("Hotel Search")
    city = st.text_input("City", "Goa", key="hotel_city")

    if st.button("Search Hotels"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_hotels(city))
        if result:
            st.success(f"Found {len(result['hotels'])} hotels in {result['city']}")
            st.table(result["hotels"])
        else:
            st.error("Could not fetch results. Try again.")

with tab6:
    st.subheader("Villas & Homestays Search")
    villa_city = st.text_input("City", "Goa", key="villa_city")

    if st.button("Search Villas & Homestays"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_villas(villa_city))
        if result:
            st.success(f"Found {len(result['villas'])} properties in {result['city']}")
            st.table(result["villas"])
        else:
            st.error("Could not fetch results. Try again.")

with tab7:
    st.subheader("Tours & Attractions")
    attraction_city = st.text_input("City", "Jaipur", key="attraction_city")

    if st.button("Search Attractions"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_attractions(attraction_city))
        if result:
            st.success(f"Found {len(result['attractions'])} attractions in {result['city']}")
            st.table(result["attractions"])
        else:
            st.error("Could not fetch results. Try again.")

with tab8:
    st.subheader("Holiday Packages")
    package_dest = st.text_input("Destination", "Kerala", key="package_dest")

    if st.button("Search Packages"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_packages(package_dest))
        if result:
            st.success(f"Found {len(result['packages'])} packages for {result['destination']}")
            st.table(result["packages"])
        else:
            st.error("Could not fetch results. Try again.")

with tab9:
    st.subheader("Cruise Packages")
    cruise_dest = st.text_input("Destination", "Singapore", key="cruise_dest")
    if st.button("Search Cruises"):
        with st.spinner("Agent is searching MakeMyTrip... (may take 1-2 minutes)"):
            result = asyncio.run(search_cruises(cruise_dest))
        if result:
            st.success(f"Found {len(result['packages'])} cruise packages")
            st.table(result["packages"])
        else:
            st.error("Could not fetch results. Try again.")