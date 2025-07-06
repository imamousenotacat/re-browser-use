import asyncio
from dotenv import load_dotenv
load_dotenv()
from browser_use import Agent
from langchain_google_genai import ChatGoogleGenerativeAI

async def main():
  agent = await Agent.create_stealth_agent(
    task=(
      "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
      "That’s all. If you get redirected, don’t worry."
    ),
    llm=ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite-preview-06-17"),
  )
  await agent.run()

asyncio.run(main())
