import libcst as cst
from libcst import matchers as m
from libcst.metadata import PositionProvider
from textwrap import dedent

class BrowserSessionTransformer(cst.CSTTransformer):

  METADATA_DEPENDENCIES = (PositionProvider,)

  def __init__(self):
    super().__init__()
    self.function_stack = []

  def visit_FunctionDef(self, node):
    self.function_stack.append(node.name.value)

  def leave_FunctionDef(self, original_node, updated_node):
    self.function_stack.pop()
    return updated_node

  def leave_Try(self, original_node, updated_node):
    target_line = "return cdp_session"
    if self.function_stack and self.function_stack[-1] == "cdp_client_for_node":
      # If the last statement of the try block is not the target_line I add it by ...
      last_stmt_of_try = cst.Module([]).code_for_node(updated_node.body.body[-1]).strip()
      if last_stmt_of_try.strip() != target_line.strip():
        # ... creating a new body with two additional lines.
        new_body=[]
        new_body.extend(updated_node.body.body)
        new_stmts = [
          cst.EmptyLine(comment=cst.Comment("# MOU14: I THINK THERE IS A MISSING 'return cdp_session' HERE. I ADD IT BELOW ...")),
          cst.parse_statement(target_line)
        ]
        new_body.extend(new_stmts)
        return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

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

  def leave_Call(self, original_node, updated_node):
    # TODO: Rewrite this to get rid of
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
async def get_main_page_from_target(self, target_id: TargetID | None = None) -> TargetID | None:
  """Get the main page corresponding to a target_id ."""
  assert self.agent_focus is not None, 'CDP session not initialized - browser may not be connected yet'
  if target_id is None:
    target_id = self.agent_focus.target_id

  all_frames, _ = await self.get_all_frames()

  candidate_frame = all_frames.get(target_id)
  if candidate_frame == None:
    return None

  while candidate_frame.get('parentId'):
    candidate_frame = all_frames[candidate_frame['parentId']]

  return candidate_frame['id']
'''

  def leave_ClassDef(self, original_node, updated_node):
    # Filter for the class named "BrowserSession"
    if original_node.name.value == "BrowserSession":
      method_node = cst.parse_statement(self.method_code)  # This gives you a SimpleStatementLine or FunctionDef
      # Insert at the end of the class body
      new_body = list(updated_node.body.body) + [method_node]
      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

  def leave_Assign(self, original_node: cst.Assign, updated_node: cst.Assign) -> cst.Assign:
    # Ensure target is exactly "domains = ..."
    if (len(updated_node.targets) == 1 and isinstance(updated_node.targets[0].target, cst.Name) and updated_node.targets[0].target.value == "domains"
        and isinstance(updated_node.value, cst.BooleanOperation) and isinstance(updated_node.value.right, cst.List)):
      # Remove Runtime from the list ...
      new_elements = list(updated_node.value.right.elements)
      new_elements.remove(next(el for el in new_elements if el.value.value.strip("'\"") == "Runtime"))
      return updated_node.with_changes(
        value=updated_node.value.with_changes(
          right=updated_node.value.right.with_changes(elements=new_elements)
        )
      )

    return updated_node

  # Ugly but quick and easy to read ...
  def leave_SimpleStatementLine(self, original_node, updated_node):
    target_line = "await session.cdp_client.send.Runtime.runIfWaitingForDebugger(session_id=session.session_id)"
    expr_code = cst.Module([]).code_for_node(original_node.body[0]).strip()
    if expr_code.strip() == target_line:
      return cst.FlattenSentinel([
        cst.parse_statement(dedent("""try:
        await session.cdp_client.send.Runtime.runIfWaitingForDebugger(session_id=session.session_id)
except Exception as e:
        self.logger.warning(
                f'Ignoring exception [{e}] when invoking runIfWaitingForDebugger. It seems to happen only if dom_highlight_elements = False ???'
        )
""")),
        updated_node,
      ])

    return updated_node
