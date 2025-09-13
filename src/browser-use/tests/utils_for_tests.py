# Work in progress. It could be replaced/complemented by a conftest.py file or completely removed ...
import os

from browser_use.agent.service import Agent
from browser_use.llm.base import BaseChatModel
from browser_use import BrowserProfile, BrowserSession
from browser_use.llm import ChatGoogle

BY_DEFAULT_GOOGLE_MODEL = "gemini-2.5-flash-lite"


def create_llm(model=BY_DEFAULT_GOOGLE_MODEL):
  """Initialize language model for testing"""
  model_from_environment = os.environ.get('BY_DEFAULT_GOOGLE_MODEL', BY_DEFAULT_GOOGLE_MODEL)
  return ChatGoogle(model=model if model != BY_DEFAULT_GOOGLE_MODEL else model_from_environment)


# A couple of dumb functions created not to have to modify another LIBCST transformer
def create_stealth_browser_session(headless: bool = False) -> BrowserSession:
  return BrowserSession(
    browser_profile=BrowserProfile(
      headless=headless,
      # Both options below are needed to pass Cloudflare challenge
      disable_security=False,
      cross_origin_iframes=True,
      highlight_elements=True
    )
  )


def create_stealth_agent(task: str, llm: BaseChatModel, browser_session: BrowserSession) -> Agent:
  return Agent(
    use_vision=False,
    task=task,
    llm=llm,
    browser_session=browser_session
  )
