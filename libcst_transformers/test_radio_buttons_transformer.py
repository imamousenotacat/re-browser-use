import libcst as cst
from libcst import matchers as m
from textwrap import dedent

class TestRadioButtonsTransformer(cst.CSTTransformer):

  def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
    target_line = "from browser_use.browser.profile import BrowserProfile"
    new_body = []

    for stmt in updated_node.body:
      expr_code = cst.Module([]).code_for_node(stmt).strip()
      new_body.append(stmt)
      if expr_code.strip() == target_line.strip():
        new_body.append(cst.parse_statement("from tests.utils_for_tests import create_llm"))
        continue

    return updated_node.with_changes(body=new_body)

  def leave_FunctionDef(self, original_node, updated_node):
    if updated_node.name.value != "test_radio_button_clicking":
      return updated_node

    replacement_code ='''
agent = Agent(
    task=task,
    browser_session=browser_session,
    max_actions_per_step=5,
    flash_mode=True,
    llm=create_llm()
)
'''
    replacement_node = cst.parse_statement(dedent(replacement_code))

    new_body = []
    for stmt in updated_node.body.body:
      if m.matches(stmt, m.SimpleStatementLine(body=[m.Assign(
          targets=[m.AssignTarget(target=m.Name("agent"))],
          value=m.Call(func=m.Name("Agent"))
      )])):
        new_body.append(replacement_node)
      else:
        new_body.append(stmt)

    return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))
