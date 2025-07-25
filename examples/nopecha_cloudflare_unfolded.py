import asyncio
from browser_use import BrowserProfile, BrowserSession
from browser_use.agent.service import Agent
from browser_use.browser.profile import BrowserChannel
from dotenv import load_dotenv
from browser_use.llm import ChatGoogle
from patchright.async_api import async_playwright

load_dotenv()


async def _create_browser_session(playwright, headless=True):
  # Creating everything clean and pure outside ...
  chromium = playwright.chromium
  browser = await chromium.launch(headless=headless)
  browser_context = await browser.new_context()
  page = await browser_context.new_page()
  browser_profile = BrowserProfile(
    channel=BrowserChannel.CHROMIUM,
    headless=headless,
    stealth=True
  )

  # Passing all the objects to the session not to create anything internally ...
  browser_session = BrowserSession(
    playwright=playwright,
    browser=browser,
    browser_context=browser_context,
    page=page,
    browser_profile=browser_profile,
  )
  return browser_session


async def _create_agent(task, llm, browser_session):
  agent = Agent(
    task=task,
    llm=llm,
    browser_session=browser_session,
    # I don't want vision or memory ...
    enable_memory=False,
    use_vision=False,
    # I don't want to waste calls to the LLM. I'm using ChatGoogleGenerativeAI ...
    tool_calling_method='function_calling'
  )

  return agent


async def main():
  async with async_playwright() as playwright:
    browser_session = await _create_browser_session(playwright, headless=False)
    agent = await _create_agent(
      task=(
        "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
        "That’s all. If you get redirected, don’t worry."
      ),
      llm=ChatGoogle(model="gemini-2.5-flash-lite"),
      browser_session=browser_session
    )
    await agent.run(10)


asyncio.run(main())
