import asyncio
import json
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
from browser_use import Agent, ChatGoogle

load_dotenv()

class Hotel(BaseModel):
    name: str
    location: str
    rating: str
    price_per_night: str

class HotelResults(BaseModel):
    city: str
    hotels: List[Hotel]

async def main():
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = """
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Hotels' tab.
    In the city/destination field, type 'Goa' and select it from the dropdown suggestions.
    Keep default check-in and check-out dates (or select any available dates about a week from today).
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
        save_conversation_path="logs/conversation_hotels",
    )

    result = await agent.run()
    final = result.final_result()

    print("\n=== RAW RESULT ===")
    print(final)

    if final:
        try:
            data = json.loads(final) if isinstance(final, str) else final
            print("\n=== STRUCTURED JSON ===")
            print(json.dumps(data, indent=2, ensure_ascii=False))

            with open("hotel_results.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("\n✅ Saved to hotel_results.json")
        except Exception as e:
            print("⚠️ JSON parse error:", e)

if __name__ == "__main__":
    asyncio.run(main())