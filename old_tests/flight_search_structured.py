import asyncio
import json
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
from browser_use import Agent, ChatGoogle

load_dotenv()

# Step A: Define karo ke output ma kayo data joiye chhe (schema)
class Flight(BaseModel):
    airline: str
    flight_number: str
    departure_time: str
    price: str

class FlightResults(BaseModel):
    from_city: str
    to_city: str
    flights: List[Flight]

async def main():
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = """
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Flights' tab if not already selected.
    In the 'From' field, type 'Ahmedabad' and select it from the dropdown suggestions.
    In the 'To' field, type 'Delhi' and select it from the dropdown suggestions.
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
        save_conversation_path="logs/conversation_structured",
    )

    result = await agent.run()
    final = result.final_result()

    print("\n=== RAW RESULT ===")
    print(final)

    # Step B: JSON tarike parse karo ane sundar print karo
    if final:
        try:
            data = json.loads(final) if isinstance(final, str) else final
            print("\n=== STRUCTURED JSON ===")
            print(json.dumps(data, indent=2))

            # File ma pan save karo
            with open("flight_results.json", "w") as f:
                json.dump(data, f, indent=2)
            print("\n✅ Saved to flight_results.json")
        except Exception as e:
            print("⚠️ JSON parse error:", e)

if __name__ == "__main__":
    asyncio.run(main())