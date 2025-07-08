import asyncio
from dotenv import load_dotenv
load_dotenv()
from browser_use import Agent
from browser_use.browser import BrowserSession
from browser_use.llm import ChatGoogle

async def main():
  browser_session = await BrowserSession.create_stealth_browser_session(headless=False)
  browser_session.browser_profile.keep_alive = False

  agent = await Agent.create_stealth_agent(
    task=(
      "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
      "That’s all. If you get redirected, don’t worry."
    ),
    llm=ChatGoogle(model="gemini-2.5-flash-lite-preview-06-17"),
    browser_session=browser_session,
  )
  await agent.run(10)
  

asyncio.run(main())
