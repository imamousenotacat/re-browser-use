import asyncio
from browser_use import BrowserProfile, BrowserSession
from browser_use.agent.service import Agent
# from browser_use.browser.profile import BrowserChannel
from dotenv import load_dotenv
from browser_use.llm import ChatGoogle

load_dotenv()


async def _create_browser_session(headless=True):
  # Providing the same options as in pre-0.6.0 versions, except those related to Playwright.
  browser_profile = BrowserProfile(
    # According to this https://github.com/browser-use/browser-use/blob/main/docs/customize/browser-settings.mdx#channel 'chrome' (default when stealth=True)
    # channel=BrowserChannel.CHROMIUM,
    headless=headless,
    disable_security=False,
    cross_origin_iframes=True,
  )

  # Providing the same options as in pre-0.6.0 versions, except those related to Playwright.
  browser_session = BrowserSession(
    browser_profile=browser_profile,
  )
  return browser_session


async def _create_agent(task, llm, browser_session):
  agent = Agent(
    task=task,
    llm=llm,
    browser_session=browser_session,
    # I don't want vision or memory ...
    # enable_memory=False, from https://github.com/browser-use/browser-use/blob/main/docs/customize/agent-settings.mdx#memory removed ...
    use_vision=False,
    # I don't want to waste calls to the LLM. I'm using ChatGoogleGenerativeAI ... (IT DOESN'T APPEAR IN THE DOCUMENTATION ANYMORE)
    # tool_calling_method='function_calling'
  )

  return agent


async def main():
  browser_session = await _create_browser_session(headless=False)
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
