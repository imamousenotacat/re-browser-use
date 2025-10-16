import pytest

from browser_use.agent.service import Agent
from browser_use.agent.views import AgentHistoryList
from browser_use import BrowserProfile, BrowserSession
from tests.utils_for_tests import create_llm


@pytest.fixture
def llm():
  return create_llm()


page_titles = []


async def titles_accumulator_hook(agent: Agent):
  current_page_title = await agent.browser_session.get_current_page_title()
  page_titles.append(current_page_title)


@pytest.mark.asyncio
async def test_nopecha(llm):
  """
  Test trying to pass a Cloudflare captcha verification.
  """
  # From https://github.com/browser-use/browser-use/blob/main/docs/customize/real-browser.mdx#method-b-connect-using-existing-playwright-objects
  # Another way of cutting Gordian knots and simplify as much as I can while adapting to the convoluted initialization process ...
  agent = Agent(
    use_vision=False,
    task=(
      # I've had to modify this because I saw this thought:
      # "I was not able to complete the captcha challenge on the cloudflare demo page. I clicked on the wrong element and was redirected to the main demo page.
      # Therefore, the task was not fully completed."
      "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
      "That’s all. If you get redirected, don’t worry."
    ),
    llm=llm,
    browser_session=BrowserSession(
      browser_profile=BrowserProfile(
        headless=False,
        # Both options below are needed to pass Cloudflare challenge
        disable_security=False,
        cross_origin_iframes=True,
        dom_highlight_elements=True
      )
    )
  )

  # Usually 5 steps are enough, but I think there was a bug creating problems with the evaluation of the last action
  history: AgentHistoryList = await agent.run(max_steps=10, on_step_end=titles_accumulator_hook)
  result = history.final_result()

  # Printing the final result and assessing it...
  print(f'FINAL RESULT: {result}')
  assert history.is_done() and history.is_successful()

  # Checking the results of the click. I'm using this: https://github.com/browser-use/browser-use/blob/main/docs/customize/hooks.mdx
  current_title = page_titles[-1]
  assert current_title == "NopeCHA - CAPTCHA Demo"
  # await browser.close()  Closing the browser => NOT NEEDED ANYMORE ...
  # await browser_context.close() => IT WAS MAKING THE TEST FAIL ...
