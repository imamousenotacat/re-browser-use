import asyncio
from browser_use import BrowserProfile, BrowserSession
from browser_use.agent.service import Agent
from dotenv import load_dotenv
from browser_use.llm import ChatGoogle

load_dotenv()


async def main():
  agent = Agent(
    task=(
    "Go to https://nopecha.com/demo/cloudflare, and always wait 10 seconds for the verification checkbox to appear."
    "Once it appears, click it once, and wait 5 more seconds. That’s all. Your job is done. Don't check anything. If you get redirected, don’t worry."
    ),
    llm=ChatGoogle(model="gemini-2.5-flash-lite"),
    browser_session=BrowserSession(
      browser_profile=BrowserProfile(
        headless=False,
        # Both options below are needed to pass Cloudflare challenge
        disable_security=False,
        cross_origin_iframes=True,
        highlight_elements=True
      )
    )
  )
  await agent.run(10)

asyncio.run(main())
