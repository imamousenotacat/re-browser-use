<h1 align="center">Enable AI to control your browser 🤖</h1>

This little project was created because I was fed up with getting blocked by Cloudflare's verification and I wanted to do things like this with Browser Use:

![nopecha_cloudflare.py](https://github.com/user-attachments/assets/2f16e2b4-9cef-4b4a-aa2d-e6ebf039cd14)

# Quick start

This is how you can see for yourself how it works:

Install the package using pip (Python>=3.11):

```bash
pip install re-browser-use
```

Install the browser. I'm using Chromium; it works OK for me. The project uses a [tweaked version of patchright](https://github.com/imamousenotacat/re-patchright)

```bash
re-patchright install chromium --with-deps --no-shell
```

Spin up your agent:

```python
import asyncio
from dotenv import load_dotenv
load_dotenv()
from browser_use import Agent
from langchain_google_genai import ChatGoogleGenerativeAI

async def main():
  agent = await Agent.create_stealth_agent(
    task=(
      "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
      "That’s all. If you get redirected, don’t worry."
    ),
    llm=ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite-preview-06-17"),
  )
  await agent.run()

asyncio.run(main())
```

Add your API keys for the provider you want to use to your `.env` file.

```bash
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_KEY=
GOOGLE_API_KEY=
DEEPSEEK_API_KEY=
GROK_API_KEY=
NOVITA_API_KEY=
```
