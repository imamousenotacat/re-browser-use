import libcst as cst


class DomWatchdogTransformer(cst.CSTTransformer):
  def __init__(self):
    super().__init__()
    self.function_stack = []

  def visit_FunctionDef(self, node):
    self.function_stack.append(node.name.value)

  def leave_FunctionDef(self, original_node, updated_node):
    self.function_stack.pop()
    return updated_node

  target_line = "await self.browser_session.add_highlights(content.selector_map)"

  replacement = """
from browser_use.dom.debug.highlights import inject_highlighting_script
await inject_highlighting_script(self._dom_service, self.selector_map)
"""

  def leave_Try(self, original_node, updated_node):
    if self.function_stack and self.function_stack[-1] == "on_BrowserStateRequestEvent":
      new_body = []
      for stmt in updated_node.body.body:
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if expr_code.strip() == self.target_line.strip():
          # This is the line we want to replace and replacing it is as simple as this ...
          new_body.extend(cst.parse_module(self.replacement).body)
        else:
          new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node
