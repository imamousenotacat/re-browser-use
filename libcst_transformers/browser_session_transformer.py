import libcst as cst
from libcst import matchers as m
from libcst.metadata import PositionProvider


class BrowserSessionTransformer(cst.CSTTransformer):
  """
  Applies 8 specific changes to browser/session.py as per the diff.
  """
  METADATA_DEPENDENCIES = (PositionProvider,)

  def __init__(self):
    super().__init__()
    self.function_stack = []

  def visit_FunctionDef(self, node):
    self.function_stack.append(node.name.value)

  # 1. Update typing import: add Optional
  def leave_ImportFrom(self, original_node, updated_node):
    if (
        updated_node.module.value == "typing" and
        isinstance(updated_node.names, cst.ImportStar) is False
    ):
      names = list(updated_node.names)
      if not any(n.name.value == 'Optional' for n in names):
        names.append(cst.ImportAlias(name=cst.Name('Optional')))
        return updated_node.with_changes(names=names)
    return updated_node

  # 2. Define types to be Union[Patchright, Playwright]"
  def leave_Module(self, original_node, updated_node):
    body = list(updated_node.body)
    insert_idx = None

    # Find _GLOB_WARNING_SHOWN
    for i, stmt in enumerate(body):
      if (
          isinstance(stmt, cst.SimpleStatementLine)
          and any(
        isinstance(expr, cst.Assign)
        and any(
          isinstance(t.target, cst.Name)
          and t.target.value == "_GLOB_WARNING_SHOWN"
          for t in expr.targets
        )
        for expr in stmt.body
      )
      ):
        insert_idx = i
        break

    # If not found use after last import as inserting point ...
    if insert_idx is None:
      for i, stmt in enumerate(body):
        if (
            isinstance(stmt, cst.SimpleStatementLine)
            and isinstance(stmt.body[0], cst.ImportFrom)
        ):
          insert_idx = i + 1

    if insert_idx is None:
      insert_idx = 0

    # Prepare new statements
    new_stmts = [
      cst.parse_statement("from patchright.async_api import Frame as PatchrightFrame"),
      cst.parse_statement("from playwright.async_api import Frame as PlaywrightFrame"),
      cst.parse_statement("Frame = PatchrightFrame | PlaywrightFrame"),
    ]
    # Attach comment to first statement
    new_stmts[0] = new_stmts[0].with_changes(
      leading_lines=[
        cst.EmptyLine(),  # This is the empty line
        cst.EmptyLine(comment=cst.Comment("# Define types to be Union[Patchright, Playwright]"))
      ]
    )

    # Check if already present
    already_present = False
    for i in range(len(body) - len(new_stmts) + 1):
      if all(
          isinstance(body[i + j], cst.SimpleStatementLine)
          and str(body[i + j]).strip() == str(new_stmts[j]).strip()
          for j in range(len(new_stmts))
      ):
        already_present = True
        break

    if not already_present:
      body = body[:insert_idx] + new_stmts + body[insert_idx:]

    return updated_node.with_changes(body=body)

  # NOT TO BE REMOVED BECAUSE IT'S AN INTERESTING TEST
  # def visit_If(self, node):
  #   if m.matches(
  #       node.test,
  #       m.Comparison(
  #         left=m.Attribute(value=m.Name("page"), attr=m.Name("url")),
  #         comparisons=[
  #           m.ComparisonTarget(
  #             operator=m.Equal(),
  #             comparator=m.SimpleString("'about:blank'")
  #           )
  #         ]
  #       )
  #   ):
  #     pos = self.get_metadata(PositionProvider, node)
  #     func = self.function_stack[-1] if self.function_stack else None
  #     print(f"Found at line: {pos.start.line}, in function: {func}")

  # 3. Comment out DVD screensaver animation code (two lines) => Removing in this case
  # 16:49 11/07/2025 THANKS TO A "hacky" IMPLEMENTATION I NEED TO INVOKE THE BLOODY FUNCTION SEE BELOW leave_Call
  # def leave_SimpleStatementLine(self, original_node, updated_node):
  #   # Match: await self._show_dvd_screensaver_loading_animation(...)
  #   if (
  #       len(updated_node.body) == 1 and
  #       m.matches(
  #         updated_node.body[0],
  #         m.Expr(
  #           value=m.Await(
  #             expression=m.Call(
  #               func=m.Attribute(
  #                 value=m.Name("self"),
  #                 attr=m.Name("_show_dvd_screensaver_loading_animation"),
  #               )
  #             )
  #           )
  #         )
  #       )
  #   ):
  #     return cst.SimpleStatementLine(
  #       [cst.Pass()],
  #       leading_lines=[
  #         cst.EmptyLine(comment=cst.Comment("# Invocation commented out by transformer")),
  #         cst.EmptyLine(comment=cst.Comment("# await self._show_dvd_screensaver_loading_animation(...)")),
  #       ]
  #     )
  #
  #   return updated_node

  # 4. Update remove_highlights method signature to accept Optional[Frame]
  def leave_FunctionDef(self, original_node, updated_node):
    self.function_stack.pop()
    if (
        updated_node.name.value == "remove_highlights" and
        isinstance(updated_node.params, cst.Parameters)
    ):
      # Add Optional[Frame] parameter
      params = list(updated_node.params.params)
      if not any(p.name.value == "target_frame" for p in params):
        params.append(
          cst.Param(
            name=cst.Name("target_frame"),
            annotation=cst.Annotation(
              annotation=cst.Subscript(
                value=cst.Name("Optional"),
                slice=[
                  cst.SubscriptElement(
                    slice=cst.Index(value=cst.Name("Frame"))
                  )
                ]
              )
            ),
            default=cst.Name("None"),
          )
        )
        return updated_node.with_changes(
          params=updated_node.params.with_changes(params=params)
        )

    if original_node.name.value == "_click_element_node":
      # The two functions and the lambda to insert, no leading indentation
      new_funcs_code = """
# Depending on the 'headless' value, we perform a different kind of click
click_func = (lambda: element_handle.click(timeout=1_500)) if self.browser_profile.headless else (lambda: click_element_handle(element_handle))
      
async def get_element_handle_pos(element_handle: ElementHandle):
    bounding_box = await element_handle.bounding_box()
    assert bounding_box

    x, y, width, height = bounding_box.get("x"), bounding_box.get("y"), bounding_box.get("width"), bounding_box.get("height")
    assert x and y and width and height

    x, y = x + width // 2, y + height // 2
    return x, y

async def click_element_handle(element_handle: ElementHandle):
    # Delaying the import to this point not to have trouble with setxkbmap -print Cannot open display "default display"
    from cdp_patches.input import AsyncInput

    # MOU14: Probably do something similar to what I saw in CDP-Patches tests and associate this object to the page
    if not hasattr(page, 'async_input'):
        browser_context: BrowserContext = page.context
        page.async_input = await AsyncInput(browser=browser_context) # type: ignore
    
    x, y = await get_element_handle_pos(element_handle)
    await page.async_input.click("left", x, y) # type: ignore
  """
      # Parse the new functions and assignment
      new_stmts_module = cst.parse_module(new_funcs_code.strip())
      new_stmts = list(new_stmts_module.header) + list(new_stmts_module.body)

      def insert_before_perform_click(body_list):
        for i, stmt in enumerate(body_list):
          if isinstance(stmt, cst.FunctionDef) and stmt.name.value == "perform_click":
            # Insert statements in reverse order to maintain original order
            for new_stmt in reversed(new_stmts):
                body_list.insert(i, new_stmt)
            # Insert one EmptyLine before all inserted statements
            body_list.insert(i, cst.EmptyLine())
            return True
        return False

      body_list = list(updated_node.body.body)

      # Try inside try-block body if not found
      for idx, stmt in enumerate(body_list):
        if isinstance(stmt, cst.Try):
          try_body = list(stmt.body.body)
          inserted = insert_before_perform_click(try_body)
          if inserted:
            new_try = stmt.with_changes(body=stmt.body.with_changes(body=try_body))
            body_list[idx] = new_try
            break

      return updated_node.with_changes(body=updated_node.body.with_changes(body=body_list))

    return updated_node

  # 5. Update remove_highlights body to use target_frame or get_current_page
  def leave_Assign(self, original_node, updated_node):
    if (
        isinstance(updated_node.targets[0].target, cst.Name) and
        updated_node.targets[0].target.value == "page" and
        isinstance(updated_node.value, cst.Await) and
        isinstance(updated_node.value.expression, cst.Call) and
        isinstance(updated_node.value.expression.func, cst.Attribute) and
        updated_node.value.expression.func.attr.value == "get_current_page"
        and self.function_stack[-1] == "remove_highlights"
    ):
      # Replace with: target = target_frame if target_frame else await self.get_current_page()
      new_value = cst.parse_expression(
        "target_frame if target_frame else await self.get_current_page()"
      )
      # Return a new Assign node, updating the target and value
      return updated_node.with_changes(
        targets=[updated_node.targets[0].with_changes(target=cst.Name("target"))],
        value=new_value,
      )

    return updated_node

  # 6. Update page.evaluate to target.evaluate in remove_highlights
  def leave_Attribute(self, original_node, updated_node):
    if (
        updated_node.attr.value == "evaluate" and
        isinstance(updated_node.value, cst.Name) and
        updated_node.value.value == "page" and
        self.function_stack[-1] == "remove_highlights"
    ):
      return updated_node.with_changes(value=cst.Name("target"))

    return updated_node

  SHOW_DVD_SCREENSAVER_LOADING_ANIMATION_JS = '''"""(browser_session_label) => {
  const animated_title = `Starting agent ${browser_session_label}...`;
  if (document.title === animated_title) {
      return;      // already run on this tab, dont run again
  }
  document.title = animated_title;
  }
  """'''

  # 7. Update get_clickable_elements to get_multitarget_clickable_elements and add remove_highlights parameter
  def leave_Call(self, original_node, updated_node):
    if (
        isinstance(updated_node.func, cst.Attribute) and
        updated_node.func.attr.value == "get_clickable_elements" and
        self.function_stack[-1] == "_get_updated_state"
    ):
      # Change method name
      new_func = updated_node.func.with_changes(attr=cst.Name("get_multitarget_clickable_elements"))
      # Add remove_highlights parameter
      args = list(updated_node.args)
      args.append(
        cst.Arg(
          keyword=cst.Name("remove_highlights"),
          value=cst.Attribute(value=cst.Name("self"), attr=cst.Name("remove_highlights")),
        )
      )
      return updated_node.with_changes(func=new_func, args=args)

    # 3. Go to hell screensaver => _show_dvd_screensaver_loading_animation replacing the javascript invoked because
    # the title set is used somewhere else ...
    if (
        self.function_stack
        and self.function_stack[-1] == "_show_dvd_screensaver_loading_animation"
        and m.matches(
      original_node,
      m.Call(
        func=m.Attribute(
          value=m.Name("page"),
          attr=m.Name("evaluate"),
        )
      )
    )
    ):
      new_args = [cst.Arg(value=cst.SimpleString(self.SHOW_DVD_SCREENSAVER_LOADING_ANIMATION_JS))]
      if len(updated_node.args) > 1:
        new_args.extend(updated_node.args[1:])
      return updated_node.with_changes(args=new_args)

    return updated_node

  method_code = '''
@staticmethod
async def create_stealth_browser_session(headless=True) -> BrowserSession:
	# Creating everything clean and pure using patchright and outside the default initialization process  ...
	patchright = await async_patchright().start()

	# I don't care about what they say about CHROMIUM stealthiness, so far it's been good enough for me ...
	browser = await patchright.chromium.launch(headless=headless)
	browser_context = await browser.new_context()
	page = await browser_context.new_page()
	if not headless:
		# Adding this new attribute here to perform real clicks ...
		from cdp_patches.input import AsyncInput
		page.async_input = await AsyncInput(browser=browser_context) # type: ignore[attr-defined]

	browser_profile = BrowserProfile(
		channel=BrowserChannel.CHROMIUM,
		headless=headless,
		stealth=True
	)

	# Passing all the objects to the session, not to create anything internally ...
	browser_session = BrowserSession(
		playwright=patchright,
		browser=browser,
		browser_context=browser_context,
		agent_current_page=page,
		browser_profile=browser_profile,
	)

	return browser_session
'''

  def leave_ClassDef(self, original_node, updated_node):
    # Filter for the class named "BrowserSession"
    if original_node.name.value == "BrowserSession":
      method_node = cst.parse_statement(self.method_code)  # This gives you a SimpleStatementLine or FunctionDef
      # Insert at the end of the class body
      new_body = list(updated_node.body.body) + [method_node]
      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

  def leave_Return(self, original_node: cst.Return, updated_node: cst.Return) -> cst.Return:
    """
    Target this:
    return await perform_click(lambda: element_handle and element_handle.click(timeout=1_500))
    and replace lambda body with:
    element_handle and click_element_handle(element_handle)
    """
    # Check if it's a return await perform_click(...)
    if not (
        isinstance(updated_node.value, cst.Await)
        and isinstance(updated_node.value.expression, cst.Call)
        and isinstance(updated_node.value.expression.func, cst.Name)
        and updated_node.value.expression.func.value == "perform_click"
        and len(updated_node.value.expression.args) >= 1
    ):
      return updated_node

    lambda_arg = updated_node.value.expression.args[0].value
    if not isinstance(lambda_arg, cst.Lambda):
      return updated_node

    def replace_lambda_body(lambda_arg, new_lambda_body, updated_node):
      new_lambda = lambda_arg.with_changes(body=new_lambda_body)
      new_args = [updated_node.value.expression.args[0].with_changes(value=new_lambda), ] + list(updated_node.value.expression.args[1:])
      new_call = updated_node.value.expression.with_changes(args=new_args)
      new_value = updated_node.value.with_changes(expression=new_call)
      return new_value

    # Inspect the lambda body to check if it's exactly: element_handle and element_handle.click(timeout=1_500)
    expected_body_node = cst.parse_expression("element_handle and element_handle.click(timeout=1_500)")
    if lambda_arg.body.deep_equals(expected_body_node):
      return updated_node.with_changes(
        value=replace_lambda_body(lambda_arg, cst.parse_expression("element_handle and click_func()"), updated_node))

    # Inspect the lambda body to check if it's exactly: element_handle.click(timeout=1_500)
    expected_body_node = cst.parse_expression("element_handle.click(timeout=1_500)")
    if lambda_arg.body.deep_equals(expected_body_node):
      return updated_node.with_changes(
        value=replace_lambda_body(lambda_arg, cst.parse_expression("click_func()"), updated_node))

    return updated_node
