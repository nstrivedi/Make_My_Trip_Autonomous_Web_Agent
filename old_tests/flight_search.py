import asyncio
from dotenv import load_dotenv
from browser_use import Agent, ChatGoogle

load_dotenv()

async def main():
    llm = ChatGoogle(model="gemini-flash-lite-latest")

    task = """
    Go to makemytrip.com.
    If any popup or login modal appears, close it first.
    Click on the 'Flights' tab if not already selected.
    In the 'From' field, type 'Ahmedabad' and select it from the dropdown suggestions.
    In the 'To' field, type 'Delhi' and select it from the dropdown suggestions.
    Click the Search button.
    Extract the top 5 flight results with airline name, departure time, and price.
    Do NOT proceed to booking or payment.
    """

    agent = Agent(
        task=task,
        llm=llm,
        max_steps=60,
        use_vision=True,
        save_conversation_path="logs/conversation",
    )

    result = await agent.run()
    print(result.final_result())

asyncio.run(main())