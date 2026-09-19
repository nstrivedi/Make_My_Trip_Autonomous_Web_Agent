import asyncio
from dotenv import load_dotenv
from browser_use import Agent, ChatGoogle

load_dotenv()

async def main():
    llm = ChatGoogle(model="gemini-flash-latest")

    agent = Agent(
        task="Go to makemytrip.com and tell me what tabs/options are visible on the homepage (Flights, Hotels, etc.)",
        llm=llm,
    )

    result = await agent.run()
    print(result.final_result())

if __name__ == "__main__":
    asyncio.run(main())