import libcst as cst


class DefaultActionWatchdogTransformer(cst.CSTTransformer):
  def __init__(self):
    self.current_function = None

  def visit_FunctionDef(self, node: cst.FunctionDef):
    self.current_function = node.name.value

  def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
    self.current_function = None
    return updated_node

  def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:
    if original_node.name.value != "DefaultActionWatchdog":
      return updated_node

    new_function_code = '''
	# TODO: MOU14 Implement while_holding_ctrl ...
	async def _system_click_element_node_impl(self, element_node, while_holding_ctrl: bool = False) -> dict | None:
		"""Perform OS level mouse left click ..."""
		# Delaying the import to this point not to have trouble with setxkbmap -print Cannot open display "default display"
		from cdp_patches.input import AsyncInput
		try:
			# The absolute_position gives viewport-relative coordinates in CSS pixels.
			# These need to be scaled by the zoom factor to get device pixels for clicking.
			bounding_box = element_node.absolute_position
			x, y, width, height = bounding_box.x, bounding_box.y, bounding_box.width, bounding_box.height
			assert x is not None and y is not None and width is not None and height is not None

			# Get zoom factor (device pixel ratio * page zoom)
			assert self.browser_session.agent_focus is not None
			metrics = await self.browser_session.agent_focus.cdp_client.send.Page.getLayoutMetrics(session_id=self.browser_session.agent_focus.session_id)

			visual_viewport = metrics.get('visualViewport', {})
			css_visual_viewport = metrics.get('cssVisualViewport', {})

			device_width = visual_viewport.get('clientWidth', 1)
			css_width = css_visual_viewport.get('clientWidth', 1)
			zoom_factor = device_width / css_width if css_width > 0 else 1.0

			# Computing the center of the element in viewport-relative CSS pixels and convert to device pixels by applying zoom.
			center_x = (x + width / 2) * zoom_factor
			center_y = (y + height / 2) * zoom_factor

			async_input = await AsyncInput(pid = self.browser_session._local_browser_watchdog._subprocess.pid) # type: ignore
			await async_input.click("left", center_x, center_y)

			self.logger.debug(f'🖱️ Clicked successfully using x=[{center_x:.2f}],y=[{center_y:.2f}] (zoom: {zoom_factor:.2f}) ...')
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

  BEAUTIFUL_IF_ELSE = """
if self.browser_session.browser_profile.headless:
  click_metadata = await self._click_element_node_impl(element_node, while_holding_ctrl=event.while_holding_ctrl)
else:
  click_metadata = await self._system_click_element_node_impl(element_node, while_holding_ctrl=event.while_holding_ctrl)
"""

  # Simplifying things, this code can be brittle, but it is extremely easy to read ...
  def leave_Try(self, original_node, updated_node):
    if self.current_function == "on_ClickElementEvent":
      # Identify the target line using a string match
      target_line = "click_metadata = await self._click_element_node_impl(element_node, while_holding_ctrl=event.while_holding_ctrl)"

      # Determine the matching statement and where to insert above it
      new_body = []
      for stmt in updated_node.body.body:
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if (target_line == expr_code):
          new_stmt = cst.parse_statement(self.BEAUTIFUL_IF_ELSE)  # This gives you a SimpleStatementLine or FunctionDef
          new_body.append(new_stmt)
        else:
          new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node
