import asyncio, os
from browser_use import BrowserProfile, BrowserSession
from browser_use.agent.service import Agent
from dotenv import load_dotenv
from browser_use.llm import ChatOpenAI

load_dotenv()


async def main():
  agent = Agent(
    use_vision=False,
    task=(
      "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
      "That’s all. If you get redirected, don’t worry."
    ),
    llm=ChatOpenAI(model="nvidia/nemotron-3-nano-30b-a3b", base_url='https://integrate.api.nvidia.com/v1',
                   api_key=os.getenv('NVIDIA_API_KEY'), add_schema_to_system_prompt=True),
    browser_session=BrowserSession(
      browser_profile=BrowserProfile(
        headless=False,
        cross_origin_iframes=True,
        dom_highlight_elements=True,
      )
    )
  )
  await agent.run(10)

asyncio.run(main())
