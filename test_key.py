import asyncio
from dotenv import load_dotenv
from browser_use import ChatGoogle
from browser_use.llm.messages import UserMessage

load_dotenv()

async def main():
    llm = ChatGoogle(model="gemini-flash-latest")
    try:
        response = await llm.ainvoke([UserMessage(content="Say hello in one word")])
        print("✅ LLM connection successful:", response.completion)
    except Exception as e:
        print("❌ LLM connection FAILED:", type(e).__name__, "-", e)

asyncio.run(main())