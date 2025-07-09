<h1 align="center">Enable AI to control your browser 🤖</h1>

This little project was created because I was fed up with getting blocked by Cloudflare's verification and I wanted to do things like this with Browser Use:

```bash
python examples\nopecha_cloudflare.py
```

![nopecha_cloudflare.py](https://raw.githubusercontent.com/imamousenotacat/re-browser-use/main/images/nopecha_cloudflare.py.gif)

or this one:

```bash
python tests/ci/evaluate_tasks.py --task tests/agent_tasks/captcha_cloudflare.yaml
```

![captcha_cloudflare.yaml](https://raw.githubusercontent.com/imamousenotacat/re-browser-use/main/images/captcha_cloudflare.yaml.gif)

If it looks slow, it is because I'm using a small and free LLM and an old computer worth $100. 

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

Create a minimalistic `.env` file. This is what I use. I'm a poor mouse and I can afford only free things. 🙂

```bash
GOOGLE_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ANONYMIZED_TELEMETRY=false
SKIP_LLM_API_KEY_VERIFICATION=true
HEADLESS_EVALUATION=false
```

And finally tell your agent to pass Cloudflare's verification:

```bash
python examples\nopecha_cloudflare.py
```

This is the code of the example file 

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
  await agent.run(10)

asyncio.run(main())
```

I have in the same directory an 'unfolded' version of the code named _nopecha_cloudflare_unfolded.py_.   
By _"unfolded"_ I mean that my simple helper static method _'Agent.create_stealth_agent'_ is not used. So we can test it with _"regular"_ patchright and browser-use:

Uninstall re-patchright (including the browsers, to be thorough) and re-browser-use and install patchright and browser-use instead: 

```bash
re-patchright uninstall --all 
pip uninstall re-patchright -y
pip uninstall re-browser-use -y

pip install patchright
patchright install chromium --with-deps --no-shell
uv pip install browser-use==0.4.5 # This is the last version I've patched so far
```

Now execute the program 

```bash
python examples\nopecha_cloudflare_unfolded.py
```

![nopecha_cloudflare_unfolded.py KO](https://raw.githubusercontent.com/imamousenotacat/re-browser-use/main/images/nopecha_cloudflare_unfolded.py.KO.gif)

With the current versions of patchright and browser-use, this won't work.

They can't detect the checkbox (well, to be precise, patchright can see it, but it needs a little extra push).

## Why is this project not a PR?

I don't want to ruffle any feathers, but we, humble but rebellious mice 😜, don't like signing CLAs or working for free for someone who, 
[by their own admission](https://browser-use.com/careers), is here to "dominate". I do this just for fun. 

Besides, the code provided by this patch won't work if it's not accompanied by [re-patchright-python](https://github.com/imamousenotacat/re-patchright-python).

I just wanted to make this work public. If someone finds this useful, they can incorporate it into their own projects. 

------

## Citation

If you use Browser Use in your research or project, please cite:

```bibtex
@software{browser_use2024,
  author = {Müller, Magnus and Žunič, Gregor},
  title = {Browser Use: Enable AI to control your browser},
  year = {2024},
  publisher = {GitHub},
  url = {https://github.com/browser-use/browser-use}
}
```

<div align="center">
Made with ❤️ in Zurich and San Francisco
 </div>
