import libcst as cst
from libcst import matchers as m
from libcst.metadata import PositionProvider


class HighlightsTransformer(cst.CSTTransformer):

  def __init__(self):
    super().__init__()
    self.function_stack = []

  def visit_FunctionDef(self, node):
    self.function_stack.append(node.name.value)

  def leave_FunctionDef(self, original_node, updated_node):
    self.function_stack.pop()
    return updated_node

  get_main_page_from_target_str = '''
# Getting the main page corresponding to the current target_id. The highlighting script needs to be evaluated in the main page
# If this is slow it could be eliminated because not seeing the highlighting doesn't affect the elements interactability (they get clicked anyway)
main_page_target_id = await dom_service.browser_session.get_main_page_from_target()
cdp_session = await dom_service.browser_session.get_or_create_cdp_session(main_page_target_id)
'''

  def leave_Try(self, original_node, updated_node):
    if self.function_stack and self.function_stack[-1] == "inject_highlighting_script":
      # We are in the correct function ...
      target_line = "cdp_session = await dom_service.browser_session.get_or_create_cdp_session()"

      new_body=[]
      for stmt in original_node.body.body:
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if expr_code.strip() == target_line.strip():
          # This is the line we want to replace and replacing it is as simple as this ...
          new_body.append(cst.parse_module(self.get_main_page_from_target_str))
        else:
          new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node
