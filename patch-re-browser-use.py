import libcst as cst
from libcst.metadata import MetadataWrapper
from libcst import Module
from libcst_transformers.browser_session_transformer import BrowserSessionTransformer
from libcst_transformers.dom_service_transformer import DomServiceTransformer
from libcst_transformers.conf_test_transformer import ConfTestTransformer
from libcst_transformers.test_radio_buttons_transformer import TestRadioButtonsTransformer
from libcst_transformers.evaluate_tasks_transformer import EvaluateTaskTransformer
from libcst_transformers.chat_google_transformer import ChatGoogleTransformer
from libcst_transformers.mcp_server_transformer import MCPServerTransformer
from libcst_transformers.simple_server_transformer import SimpleServerTransformer
from libcst_transformers.default_action_watchdog_transformer import DefaultActionWatchdogTransformer
# from libcst_transformers.highlights_transformer import HighlightsTransformer
from libcst_transformers.dom_serializer_transformer import DomSerializerTransformer
from libcst_transformers.dom_views_transformer import DomViewsTransformer
from libcst_transformers.screenshot_watchdog_transformer import ScreenshotWatchdogTransformer
from libcst_transformers.aboutblank_watchdog_transformer import AboutBlankWatchdogTransformer
from libcst_transformers.local_browser_watchdog_transformer import LocalBrowserWatchdogTransformer
from libcst_transformers.dom_watchdog_transformer import DomWatchdogTransformer
from ruamel.yaml import YAML
from tomlkit import parse, dumps, array, inline_table

FILES_LOCATION_PREFIX = "browser-use/"


def open_file(file_path, mode="r"):
  return open(FILES_LOCATION_PREFIX + file_path, mode, encoding="utf-8", newline="\n")


def write_cst_to_disk(file_path: str, tree: Module):
  with open_file(file_path, "w") as f:
    f.write(tree.code)


def patch_python_file(file_path: str, transformer: cst.CSTTransformer):
  # Step 1: Read the source file
  with open_file(file_path) as f:
    source = f.read()

  # Step 2: Parse the source code into a CST tree
  tree = MetadataWrapper(cst.parse_module(source))

  # Step 3: Apply the transformer
  updated_tree = tree.visit(transformer)

  # Step 4: Write the result to a new file or overwrite the original
  write_cst_to_disk(file_path, updated_tree)
  print(f"Successfully updated {file_path}")


# TODO: MOU14 THESE EXECUTIONS AREN'T IDEMPOTENT FOR THE MOMENT ...
# Pre 0.6.1 transformers still valid
patch_python_file("tests/ci/conftest.py", ConfTestTransformer())
patch_python_file("tests/ci/test_radio_buttons.py", TestRadioButtonsTransformer())
patch_python_file("tests/ci/evaluate_tasks.py", EvaluateTaskTransformer())
patch_python_file("browser_use/llm/google/chat.py", ChatGoogleTransformer())
patch_python_file("browser_use/mcp/server.py", MCPServerTransformer())
patch_python_file("examples/mcp/simple_server.py", SimpleServerTransformer())

# # Post 0.6.1 transformers ... (some of them were present in the pre 0.6.1 versions
patch_python_file("browser_use/browser/watchdogs/default_action_watchdog.py", DefaultActionWatchdogTransformer())
patch_python_file("browser_use/browser/session.py", BrowserSessionTransformer())
patch_python_file("browser_use/dom/serializer/serializer.py", DomSerializerTransformer())
patch_python_file("browser_use/dom/service.py", DomServiceTransformer())
patch_python_file("browser_use/dom/views.py", DomViewsTransformer())
patch_python_file("browser_use/browser/watchdogs/screenshot_watchdog.py", ScreenshotWatchdogTransformer())
patch_python_file("browser_use/browser/watchdogs/aboutblank_watchdog.py", AboutBlankWatchdogTransformer())
patch_python_file("browser_use/browser/watchdogs/local_browser_watchdog.py", LocalBrowserWatchdogTransformer())
patch_python_file("browser_use/browser/watchdogs/dom_watchdog.py", DomWatchdogTransformer())

# Step 1: Parse TOML and replace the dependency ...
with open_file("pyproject.toml") as f:
  doc = parse(f.read())

deps = doc["project"]["dependencies"]

# Add the dependency to the library enabling real clicks ...
deps.append("re-cdp-patches>=0.9.1")

# and remove the required-environments key from [tool.uv]
if "tool" in doc and "uv" in doc["tool"]:
  doc["tool"]["uv"].pop("required-environments", None)

# Rest of pyproject.toml modifications:
PROJECT_NAME = "re-browser-use"

doc["project"]["name"] = PROJECT_NAME
# TODO: MOU14
doc["project"]["description"] = "Patching Browser Use to make it work with more websites and URLs ..."
# Changing the author is not so straightforward
authors_arr = array()
author = inline_table()
author["name"] = "Gregor Zunic, patched by github.com/imamousenotacat/"
authors_arr.append(author)
authors_arr.multiline(False)
doc["project"]["authors"] = authors_arr
doc["project"]["version"] = "0.7.2"

all_deps = doc["project"]["optional-dependencies"]["all"]
for i, dep in enumerate(all_deps):
    if dep.startswith("browser-use["):
        all_deps[i] = dep.replace("browser-use[", f"{PROJECT_NAME}[")
doc["project"]["optional-dependencies"]["all"] = all_deps

doc["project"]["urls"]["Repository"] = "https://github.com/imamousenotacat/re-browser-use"

# Disappeared in 0.7.0 ???
# scripts = doc["project"]["scripts"]
# scripts["re-browseruse"] = scripts.pop("browseruse")
# scripts[PROJECT_NAME] = scripts.pop("browser-use")

# Step 2: Dump TOML back to string (preserving formatting)
new_content = dumps(doc)

# Step 3: Write back to file
with open_file("pyproject.toml", "w") as f:
  f.write(new_content)

print(f"Successfully updated pyproject.toml")

# Changing some details in a couple of YAML files to avoid unsolvable problems with Google CAPTCHA and stupid problems with the judge saying
# from time to time that "example.com" is not a valid name ...
yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096  # disables line wrapping
yaml.indent(mapping=0, sequence=0, offset=2)

browser_use_pip_yaml = "tests/agent_tasks/browser_use_pip.yaml"
with open_file(browser_use_pip_yaml) as f:
  data = yaml.load(f)

data['task'] = 'Find the pip installation command for the browser-use repo, if you find a Google CAPTCHA search instead in duckduckgo.com'

with open_file(browser_use_pip_yaml, 'w') as f:
  yaml.dump(data, f)

print(f"Successfully updated {browser_use_pip_yaml}")


captcha_cloudflare_yaml = "tests/agent_tasks/captcha_cloudflare.yaml"
with open_file(captcha_cloudflare_yaml) as f:
  data = yaml.load(f)

data['task'] = 'Go to https://2captcha.com/demo/cloudflare-turnstile and ALWAYS wait 10 seconds patiently without scrolling or doing anything for the verification checkbox to appear. Click that checkbox. Wait a few seconds, then click on Check button, wait a few more seconds for it to complete, then extract the "hostname" value from the displayed dictionary under "Captcha is passed successfully!"'
data['max_steps'] = 10
data['judge_context'][1] = 'The hostname returned should be "example.com" which will always be considered a valid name'

with open_file(captcha_cloudflare_yaml, 'w') as f:
  yaml.dump(data, f)

print(f"Successfully updated {captcha_cloudflare_yaml}")
