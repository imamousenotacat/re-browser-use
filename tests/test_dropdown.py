"""
Test dropdown interaction functionality.
"""
import os
import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from browser_use import BrowserSession, BrowserProfile
from browser_use.agent.service import Agent
from browser_use.agent.views import AgentHistoryList

@pytest.fixture
def llm():
	"""Initialize language model for testing"""
	api_key = os.getenv('GEMINI_API_KEY','')
	return ChatGoogleGenerativeAI(model='gemini-2.0-flash', api_key=SecretStr(api_key))

@pytest.fixture
async def browser_session():
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(
			headless=False,
			stealth=True
		)
	)
	await browser_session.start()
	yield browser_session
	await browser_session.stop()

async def test_dropdown(llm, browser_session):
	"""Test selecting an option from a dropdown menu."""
	agent = Agent(
		task=(
			# 'go to https://codepen.io/geheimschriftstift/pen/mPLvQz and first get all options for the dropdown and then select the 5th option'
      # I'M NOT DETECTED EVEN WITH stealth=False
      # "go to https://fingerprint.com/products/bot-detection/ and stay there for 120 seconds"
      "go to https://nopecha.com/demo/cloudflare and stay there for 120 seconds" # I DON'T PASS CLICKING MANUALLY
		),
		llm=llm,
		browser_session=browser_session,
		enable_memory=False,
		use_vision=False
	)

	try:
		history: AgentHistoryList = await agent.run(10)
		result = history.final_result()

		# Verify dropdown interaction
		assert result is not None
		assert 'Duck' in result, "Expected 5th option 'Duck' to be selected"

		# Verify dropdown state
		page = await browser_session.get_current_page()
		element = await page.query_selector('select')
		assert element is not None, 'Dropdown element should exist'

		value = await element.evaluate('el => el.value')
		assert value == '5', 'Dropdown should have 5th option selected'

	except Exception as e:
		pytest.fail(f'Dropdown test failed: {str(e)}')
