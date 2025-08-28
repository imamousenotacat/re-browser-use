import asyncio
from browser_use import BrowserProfile, BrowserSession
from browser_use.agent.service import Agent
from dotenv import load_dotenv
from browser_use.llm import ChatGoogle

load_dotenv()


async def main():
  agent = Agent(
    task=(
      "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
      "That’s all. If you get redirected, don’t worry."
    ),
    llm=ChatGoogle(model="gemini-2.5-flash-lite"),
    browser_session=BrowserSession(
      browser_profile=BrowserProfile(
        headless=False,
        # Both options below are needed to pass Cloudflare challenge
        disable_security=False,
        cross_origin_iframes=True,
      )
    )
  )
  await agent.run(10)

asyncio.run(main())
