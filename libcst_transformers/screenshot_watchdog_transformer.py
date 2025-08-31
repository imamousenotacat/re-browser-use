import libcst as cst


# Patterns start to emerge about the different types transformations, but I don't want to waste time improving this
class ScreenshotWatchdogTransformer(cst.CSTTransformer):

  def __init__(self):
    self.current_function = None

  def visit_FunctionDef(self, node: cst.FunctionDef):
    self.current_function = node.name.value

  def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
    self.current_function = None
    return updated_node

  # Simplifying things, this code can be brittle, but it is extremely easy to read ...
  def leave_Try(self, original_node, updated_node):
    if self.current_function == "on_ScreenshotEvent":
      # Identify the target line using a string match
      target_line = "await self.browser_session.remove_highlights()"
      BEAUTIFUL_COMMENT = f"""# {target_line}
# MOU14: I don't like it: it removes visual feedback about what is happening: (commented out by transformer)
pass
"""
      # Determine the matching statement and where to insert above it
      new_body = []
      for stmt in updated_node.body.body:
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if (target_line == expr_code):
          new_stmt = cst.parse_statement(BEAUTIFUL_COMMENT)  # This gives you a SimpleStatementLine or FunctionDef
          new_body.append(new_stmt)
        else:
          new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node
