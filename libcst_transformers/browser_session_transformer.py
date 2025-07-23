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

  def leave_ClassDef(self, original_node, updated_node):
    # Filter for the class named "BrowserSession"
    if original_node.name.value == "BrowserSession":
      method_node = cst.parse_statement(method_code)  # This gives you a SimpleStatementLine or FunctionDef
      # Insert at the end of the class body
      new_body = list(updated_node.body.body) + [method_node]
      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

method_code ='''
@staticmethod
async def create_stealth_browser_session(headless=True) -> BrowserSession:
	# Creating everything clean and pure using patchright and outside the default initialization process  ...
	patchright = await async_patchright().start()

	# I don't care about what they say about CHROMIUM stealthiness, so far it's been good enough for me ...
	browser = await patchright.chromium.launch(headless=headless)
	browser_context = await browser.new_context()
	page = await browser_context.new_page()
	browser_profile = BrowserProfile(
		channel=BrowserChannel.CHROMIUM,
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