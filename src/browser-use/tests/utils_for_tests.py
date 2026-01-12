# Work in progress. It could be replaced/complemented by a conftest.py file or completely removed ...
import os

from browser_use.agent.service import Agent
from browser_use.llm.base import BaseChatModel
from browser_use import BrowserProfile, BrowserSession
from browser_use.llm import ChatOpenAI

BY_DEFAULT_MODEL = "nvidia/nemotron-3-nano-30b-a3b"


# From https://github.com/browser-use/browser-use/blob/main/examples/models/openrouter.py
def create_llm(model=BY_DEFAULT_MODEL):
  """Initialize language model for testing"""
  return ChatOpenAI(model=model, base_url='https://integrate.api.nvidia.com/v1',
                    api_key=os.getenv('NVIDIA_API_KEY'), add_schema_to_system_prompt=True)

# A couple of dumb functions created not to have to modify another LIBCST transformer
def create_stealth_browser_session(headless: bool = False) -> BrowserSession:
  return BrowserSession(
    browser_profile=BrowserProfile(
      headless=headless,
      # Both options below are needed to pass Cloudflare challenge
      disable_security=False,
      cross_origin_iframes=True,
      dom_highlight_elements=True,
      # if you set this value to True captcha_cloudflare.yaml won't work ... NOT TRUE ANYMORE
      paint_order_filtering=True,
    )
  )


def create_stealth_agent(task: str, llm: BaseChatModel, browser_session: BrowserSession) -> Agent:
  return Agent(
    use_vision=False,
    task=task,
    llm=llm,
    browser_session=browser_session
  )
