import asyncio
from dotenv import load_dotenv
from browser_use import Agent, BrowserProfile, BrowserSession
from langchain_google_genai import ChatGoogleGenerativeAI
from patchright.async_api import async_playwright

load_dotenv()

async def create_agent(task, llm, browser_session):
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

async def create_browser_session(playwright, headless=True):
  # Creating everything clean and pure outside ...
  chromium = playwright.chromium
  browser = await chromium.launch(headless=headless)
  browser_context = await browser.new_context()
  page = await browser_context.new_page()
  browser_profile = BrowserProfile(
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

async def main():

  async with async_playwright() as playwright:  
    browser_session = await create_browser_session(playwright, headless=False)
    agent = await create_agent(
      task=(
        "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
        "That’s all. If you get redirected, don’t worry."
      ),
      llm=ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite-preview-06-17"),
      browser_session=browser_session,
    )
    await agent.run()

asyncio.run(main())
