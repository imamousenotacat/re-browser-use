<h1 align="center">Enable AI to control your browser 🤖</h1>

___A patched, drop-in replacement for [browser-use](https://github.com/browser-use/browser-use), capable of defeating Cloudflare's verification.___

```diff
- NOTE: 
- It seems that after getting rid of Playwright and having done an amazing piece of work developing 
- their own event bus and SafeType CDP client, this use case is still not being contemplated by
- browser-use, so I had to do it myself... 😎

- Pre 0.6.1 versions of this project used to depend on a tweaked version of patchright 
- (https://github.com/imamousenotacat/re-patchright) but not anymore.
```

This little project was created because I was fed up with getting blocked by Cloudflare's verification and I wanted to do things like this with Browser Use:

<a id="nopecha_cloudflare_no_playwright.py.gif"></a>
```bash
python examples\nopecha_cloudflare_no_playwright.py
```

![nopecha_cloudflare.py](https://raw.githubusercontent.com/imamousenotacat/re-browser-use/main/images/nopecha_cloudflare_no_playwright.py-0.7.7.1.gif)

I have added OS-level clicks in headful mode to enable the use of ProtonVPN. Once again, credit goes to [Vinyzu](https://github.com/Vinyzu),
as I used a pruned and slightly modified version of his [CDP-Patches](https://github.com/imamousenotacat/re-cdp-patches) project for this.

_**I restored and completed the JavaScript highlighting system that was removed in version 0.7.1 and only partially reincorporated in 0.8.1.**_ I find it extremely useful for my use case.

The one below is a long-awaited browser-use test that was chased for quite a while 😜:

```bash
python tests/ci/evaluate_tasks.py --task tests/agent_tasks/captcha_cloudflare.yaml
```

![captcha_cloudflare.yaml](https://raw.githubusercontent.com/imamousenotacat/re-browser-use/main/images/captcha_cloudflare.yaml-post-0.7.7.1.gif)

```diff
- NOTE:
- This test, captcha_cloudflare.yaml, was removed in version 0.7.6. The browser-use team seems fixated
- on not addressing the Cloudflare challenge 😲. I got it restored here. If you apply the patch
- using the commands in .github/workflows/apply-patches.yaml, you can get it back and successfully
- execute it.
```

If it looks slow, it is because I'm using a small and free LLM and an old computer worth $100. 

# Quick start

This is how you can see for yourself how it works:

Clone this repository and using [uv](https://docs.astral.sh/uv/getting-started/installation/) install the pip package (Python>=3.11):

```bash
git clone https://github.com/imamousenotacat/re-browser-use
cd re-browser-use\
uv venv
.venv\Scripts\activate
uv pip install re-browser-use
```

Install the browser as described in the [browse-use](https://github.com/browser-use/browser-use) repository.

```bash
uvx playwright install chromium --with-deps --no-shell
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
python examples\nopecha_cloudflare_no_playwright.py
```

You will get something very similar to the [animated gif above](#nopecha_cloudflare_no_playwright.py.gif). This is the code of the example file:

```python
import asyncio
from browser_use import BrowserProfile, BrowserSession
from browser_use.agent.service import Agent
from dotenv import load_dotenv
from browser_use.llm import ChatGoogle

load_dotenv()


async def main():
  agent = Agent(
    use_vision=False,
    task=(
      "Go to https://nopecha.com/demo/cloudflare, wait for the verification checkbox to appear, click it once, and wait for 10 seconds."
      "That’s all. If you get redirected, don’t worry."
    ),
    llm=ChatGoogle(model="gemini-2.5-flash-lite"),
    browser_session=BrowserSession(
      browser_profile=BrowserProfile(
        headless=False,
        cross_origin_iframes=True,
        dom_highlight_elements=True
      )
    )
  )
  await agent.run(10)

asyncio.run(main())
```

If you want to run the same code with _"regular"_ browser-use to compare the results, uninstall re-browser-use and install browser-use instead:

```bash
uv pip uninstall re-browser-use
uv pip install --upgrade --force-reinstall browser-use["all"]==0.8.1 # This is the last version I've patched so far
```

Now run again the script

```bash
python examples\nopecha_cloudflare_no_playwright.py
```

![nopecha_cloudflare_unfolded.py KO](https://raw.githubusercontent.com/imamousenotacat/re-browser-use/main/images/nopecha_cloudflare_no_playwright.py.KO-0.8.1.gif)

With the current versions of browser-use, this still won't work.

## Why is this project not a PR?

I don't want to ruffle any feathers, but we, humble but rebellious mice 😜, don't like signing CLAs or working for free for someone who, 
[by their own admission](https://browser-use.com/careers), is here to "dominate". I do this just for fun. 

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
