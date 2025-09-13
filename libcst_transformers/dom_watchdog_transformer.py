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

  target_line = """# Skip JavaScript highlighting injection - Python highlighting will be applied later
self.logger.debug('🔍 DOMWatchdog._build_dom_tree_without_highlights: ✅ COMPLETED DOM tree build (no JS highlights)')
"""

  replacement = """
# Inject highlighting for visual feedback if we have elements
if self.selector_map and self._dom_service and self.browser_session.browser_profile.highlight_elements:
  try:
    self.logger.debug('🔍 DOMWatchdog._build_dom_tree: Injecting highlighting script...')
    from browser_use.dom.debug.highlights import inject_highlighting_script

    await inject_highlighting_script(self._dom_service, self.selector_map)
    self.logger.debug(
      f'🔍 DOMWatchdog._build_dom_tree: ✅ Injected highlighting for {len(self.selector_map)} elements'
    )
  except Exception as e:
    self.logger.debug(f'🔍 DOMWatchdog._build_dom_tree: Failed to inject highlighting: {e}')
elif self.selector_map and self._dom_service and not self.browser_session.browser_profile.highlight_elements:
  self.logger.debug('🔍 DOMWatchdog._build_dom_tree: Skipping highlighting injection - highlight_elements=False')
"""

  def leave_Try(self, original_node, updated_node):
    if self.function_stack and self.function_stack[-1] == "_build_dom_tree_without_highlights":
      new_body = []
      for stmt in original_node.body.body:
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if expr_code.strip() == self.target_line.strip():
          # This is the line we want to replace and replacing it is as simple as this ...
          new_body.append(cst.parse_module(self.replacement))
        else:
          new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node
