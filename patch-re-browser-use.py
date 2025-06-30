import libcst as cst
from libcst.metadata import MetadataWrapper
from libcst import Module

from libcst_transformers.agent_service_transformer import AgentServiceTransformer
from libcst_transformers.browser_session_transformer import BrowserSessionTransformer
from libcst_transformers.dom_service_transformer import DomServiceTransformer
from libcst_transformers.test_controller_transformer import TestControllerTransformer
from libcst_transformers.evaluate_tasks_transformer import EvaluateTaskTransformer

FILES_LOCATION_PREFIX = "files-to-be-patched/"


def open_file(file_path):
  return open(FILES_LOCATION_PREFIX + file_path, encoding="utf-8")


def write_to_disk(file_path: str, tree: Module):
  with open(FILES_LOCATION_PREFIX + file_path, "w", encoding="utf-8", newline="\n") as f:
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
  write_to_disk(file_path, updated_tree)
  print(f"Successfully updated {file_path}")

# Applying all the libcst transformers ...
patch_python_file("browser_use/agent/service.py", AgentServiceTransformer())
patch_python_file("browser_use/browser/session.py", BrowserSessionTransformer())
patch_python_file("browser_use/dom/service.py", DomServiceTransformer())
patch_python_file("tests/ci/test_controller.py", TestControllerTransformer())
patch_python_file("tests/ci/evaluate_tasks.py", EvaluateTaskTransformer())
