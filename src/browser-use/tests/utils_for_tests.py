# Work in progress. It could be replaced/complemented by a conftest.py file or completely removed ...
import os
from browser_use.llm import ChatGoogle

BY_DEFAULT_GOOGLE_MODEL = "gemini-2.5-flash-lite"


# async def create_browser_session(playwright, headless=True):
#   return await BrowserSession.create_stealth_browser_session(headless=headless)


def create_llm(model=BY_DEFAULT_GOOGLE_MODEL):
  """Initialize language model for testing"""
  model_from_environment = os.environ.get('BY_DEFAULT_GOOGLE_MODEL', BY_DEFAULT_GOOGLE_MODEL)
  return ChatGoogle(model=model if model != BY_DEFAULT_GOOGLE_MODEL else model_from_environment)


# async def create_agent(task, llm, browser_session):
#   return await Agent.create_stealth_agent(task, llm)
