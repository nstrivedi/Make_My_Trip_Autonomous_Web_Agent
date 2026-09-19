import json
import os
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
from browser_use import Agent, ChatGoogle

load_dotenv()

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# ---- Schemas ----
class Flight(BaseModel):
    airline: str
    flight_number: str
    departure_time: str
    price: str

class FlightResults(BaseModel):
    from_city: str
    to_city: str
    flights: List[Flight]

class Hotel(BaseModel):
    name: str
    location: str
    rating: str
    price_per_night: str

class HotelResults(BaseModel):
    city: str
    hotels: List[Hotel]

# ---- Reusable functions ----
async def search_flights(from_city: str, to_city: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Flights' tab if not already selected.
    In the 'From' field, type '{from_city}' and select it from the dropdown suggestions.
    In the 'To' field, type '{to_city}' and select it from the dropdown suggestions.
    Click the Search button.
    Wait for results to load.
    Extract the top 5 flight results with airline name, flight number, departure time, and price.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=FlightResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        # Timestamp sathe unique filename banavo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/flights_{from_city}_to_{to_city}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None

async def search_hotels(city: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Hotels' tab.
    In the city/destination field, type '{city}' and select it from the dropdown suggestions.
    Keep default check-in and check-out dates.
    Click the Search button.
    Wait for results to load.
    Extract the top 5 hotel results with hotel name, location/area, rating, and price per night.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=HotelResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/hotels_{city}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None

#--------------------------------------------------------------------------------------------------------------------------

class Bus(BaseModel):
    operator: str
    bus_type: str
    departure_time: str
    duration: str
    price: str

class BusResults(BaseModel):
    from_city: str
    to_city: str
    buses: List[Bus]


async def search_buses(from_city: str, to_city: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Buses' tab.
    In the 'From' field, type '{from_city}' and select it from the dropdown suggestions.
    In the 'To' field, type '{to_city}' and select it from the dropdown suggestions.
    Select any available date about 3 days from today if a date field appears.
    Click the Search button.
    Wait for results to load.
    Extract the top 5 bus results with operator name, bus type (AC/Non-AC/Sleeper), departure time, journey duration, and price.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=BusResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/buses_{from_city}_to_{to_city}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# ---- Train Schema ----
class Train(BaseModel):
    train_name: str
    train_number: str
    departure_time: str
    arrival_time: str
    price: str

class TrainResults(BaseModel):
    from_city: str
    to_city: str
    trains: List[Train]

# ---- Train search function ----
async def search_trains(from_city: str, to_city: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Trains' tab.
    In the 'From' field, type '{from_city}' and select it from the dropdown suggestions.
    In the 'To' field, type '{to_city}' and select it from the dropdown suggestions.
    Keep the default travel date, or select any available date about a week from today.
    Click the Search button.
    Wait for results to load.
    Extract the top 5 train results with train name, train number, departure time, arrival time, and price.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=TrainResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/trains_{from_city}_to_{to_city}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None

class Cab(BaseModel):
    cab_type: str
    provider: str
    price: str
    eta: str

class CabResults(BaseModel):
    from_location: str
    to_location: str
    cabs: List[Cab]

async def search_cabs(from_location: str, to_location: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Cabs' tab.
    In the 'From' / pickup location field, type '{from_location}' and select it from the dropdown suggestions.
    In the 'To' / drop location field, type '{to_location}' and select it from the dropdown suggestions.
    Keep default date and time (or select any available date about 2 days from today).
    Click the Search button.
    Wait for results to load.
    Extract the top 5 cab results with cab type (e.g. Sedan, SUV, Hatchback), provider/operator name if visible, price, and estimated pickup time (ETA).
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=CabResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/cabs_{from_location}_to_{to_location}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class Villa(BaseModel):
    name: str
    location: str
    rating: str
    price_per_night: str
    property_type: str  # e.g. "Villa", "Homestay", "Cottage"

class VillaResults(BaseModel):
    city: str
    villas: List[Villa]

async def search_villas(city: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Hotels' tab.
    In the city/destination field, type '{city}' and select it from the dropdown suggestions.
    Keep default check-in and check-out dates.
    Click the Search button.
    Wait for results to load.
    Look for a filter or category option labeled 'Villas', 'Homestays', or 'Alternate Accommodation' in the property type filters on the left side of the results page, and apply it.
    If no such filter exists, look for properties in the results whose type is Villa, Homestay, or Cottage.
    Extract the top 5 villa/homestay results with property name, location/area, rating, price per night, and property type.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=VillaResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/villas_{city}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class CruisePackage(BaseModel):
    name: str
    duration: str
    destination: str
    price: str

class CruiseResults(BaseModel):
    search_type: str
    packages: List[CruisePackage]

async def search_cruises(destination: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Look for the 'Holidays' tab or menu option and click it.
    If there is a search bar, search for 'Cruise packages {destination}'.
    If a direct search is not possible, navigate to the cruise packages section.
    Wait for the page to load.
    Extract the top 5 cruise package results with package name, duration, destination, and price.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=CruiseResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/cruises_{destination}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


# ---- Tours & Attractions Schema ----
class Attraction(BaseModel):
    name: str
    description: str
    rating: str
    price: str

class AttractionResults(BaseModel):
    city: str
    attractions: List[Attraction]

# ---- Holiday Packages Schema ----
class Package(BaseModel):
    name: str
    duration: str
    inclusions: str
    price: str

class PackageResults(BaseModel):
    destination: str
    packages: List[Package]


async def search_attractions(city: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Things To Do' or 'Tours & Attractions' tab/section (it may also be under 'Holidays' menu).
    In the city/destination field, type '{city}' and select it from the dropdown suggestions.
    Click the Search button.
    Wait for results to load.
    Extract the top 5 attraction/activity results with name, short description, rating, and price.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=AttractionResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/attractions_{city}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None


async def search_packages(destination: str):
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = f"""
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Holidays' tab.
    In the destination field, type '{destination}' and select it from the dropdown suggestions.
    Click the Search button.
    Wait for results to load.
    Extract the top 5 holiday package results with package name, duration (nights/days), key inclusions, and price.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        output_model_schema=PackageResults,
    )

    result = await agent.run()
    final = result.final_result()
    if final:
        data = json.loads(final)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{RESULTS_DIR}/packages_{destination}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        return data
    return None
    # return json.loads(final) if final else None

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

