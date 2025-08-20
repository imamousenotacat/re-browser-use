import libcst as cst


class DefaultActionWatchdogTransformer(cst.CSTTransformer):
  def __init__(self):
    self.current_function = None

  def visit_FunctionDef(self, node: cst.FunctionDef):
    self.current_function = node.name.value

  def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
    self.current_function = None
    return updated_node

  def leave_Module(self, original_node, updated_node):
    target_node = cst.parse_statement("from typing import Any")
    new_import = cst.parse_statement("from cdp_patches.input import AsyncInput")

    new_body = []
    for stmt in updated_node.body:
      if stmt.deep_equals(target_node):
        # Adding new import after the target node ...
        new_body.append(stmt)
        new_body.append(cst.EmptyLine())
        new_body.append(new_import)
        continue

      new_body.append(stmt)

    return updated_node.with_changes(body=new_body)

  def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:
    if original_node.name.value != "DefaultActionWatchdog":
      return updated_node

    new_function_code = '''
# TODO: MOU14 Implement while_holding_ctrl ...
async def _system_click_element_node_impl(self, element_node, while_holding_ctrl: bool = False) -> dict | None:
    """Perform OS level mouse left click ..."""
    try:
        # The coordinates you need are already in the field absolute_position for the node ...
        bounding_box = element_node.absolute_position
        x, y, width, height = bounding_box.x, bounding_box.y, bounding_box.width, bounding_box.height
        assert x and y and width and height
        center_x, center_y = x + width // 2, y + height // 2

        async_input = await AsyncInput(pid = self.browser_session._local_browser_watchdog._subprocess.pid) # type: ignore
        await async_input.click("left", center_x, center_y)

        self.logger.debug('🖱️ Clicked successfully using x,y coordinates')
        # Return coordinates as dict for metadata
        return {"click_x": center_x, "click_y": center_y}
    except Exception as e:
        # Extract key element info for error message
        element_info = f'<{element_node.tag_name or "unknown"}'
        if element_node.element_index:
            element_info += f' index={element_node.element_index}'
        element_info += '>'
        raise Exception(
            f'<llm_error_msg>Failed to click element {element_info}. The element may not be interactable or visible. {type(e).__name__}: {e}</llm_error_msg>'
        )
'''

    # To include the header you must do it like this
    new_stmts_module = cst.parse_module(new_function_code)
    new_stmts = list(new_stmts_module.header) + list(new_stmts_module.body)

    # Find index of _click_element_node_impl function
    insert_at = 0
    for i, stmt in enumerate(updated_node.body.body):
      if (
          isinstance(stmt, cst.FunctionDef)
          and stmt.name.value == "_click_element_node_impl"
      ):
        insert_at = i + 1
        break

    new_body = list(updated_node.body.body)
    for new_stmt in reversed(new_stmts):
      new_body.insert(insert_at, new_stmt)

    return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

  def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.BaseExpression:
    if self.current_function == "on_ClickElementEvent":
      # Match calls to self._click_element_node_impl(...)
      if (
          isinstance(original_node.func, cst.Attribute) and
          isinstance(original_node.func.value, cst.Name) and
          original_node.func.value.value == "self" and
          original_node.func.attr.value == "_click_element_node_impl"
      ):
        # Replace the attribute to _system_click_element_node_impl
        new_func = updated_node.func.with_changes(attr=cst.Name("_system_click_element_node_impl"))
        return updated_node.with_changes(func=new_func)

    return updated_node
