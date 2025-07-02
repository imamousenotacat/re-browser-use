# Work in progress. It could be replaced/complemented by a conftest.py file ...
import os

from browser_use.agent.service import Agent
from browser_use import BrowserProfile, BrowserSession
from langchain_google_genai import ChatGoogleGenerativeAI

BY_DEFAULT_GOOGLE_MODEL = "gemini-2.5-flash-lite-preview-06-17"


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


def create_llm(model=BY_DEFAULT_GOOGLE_MODEL):
  """Initialize language model for testing"""
  model_from_environment = os.environ.get('BY_DEFAULT_GOOGLE_MODEL', BY_DEFAULT_GOOGLE_MODEL)
  return ChatGoogleGenerativeAI(model=model if model != BY_DEFAULT_GOOGLE_MODEL else model_from_environment)


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
