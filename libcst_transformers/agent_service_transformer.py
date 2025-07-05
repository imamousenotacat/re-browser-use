import libcst as cst
import libcst.matchers as m

# Timeout for LLM API calls in seconds: Gemini is killing me and getting stuck forever ...
class AgentServiceTransformer(cst.CSTTransformer):

  def __init__(self):
    self.in_get_next_action = False
    self.in__run_planner = False
    self.class_stack = []

  def visit_ClassDef(self, node):
    self.class_stack.append(node.name.value)
    # print(f"class_stack={self.class_stack}")

  def leave_ClassDef(self, original_node, updated_node):
    self.class_stack.pop()
    return updated_node

  # visit_FunctionDef is called when entering a function definition node, before visiting its body
  def visit_FunctionDef(self, node):
    # LibCST traverses the entire file and look for any function named get_next_action, regardless of class
    # if node.name.value == "get_next_action" and self.current_class == "Agent":
    if node.name.value == "get_next_action" and self.class_stack and self.class_stack[-1] == "Agent":
      self.in_get_next_action = True
    if node.name.value == "_run_planner" and self.class_stack and self.class_stack[-1] == "Agent":
      self.in__run_planner = True

  # leave_FunctionDef is called after visiting all children (body, decorators, etc.) of the function definition node
  def leave_FunctionDef(self, original_node, updated_node):
    if self.in_get_next_action or self.in__run_planner:
      # Insert LLM_TIMEOUT_SECONDS after the docstring (if present)
      # .body (of FunctionDef) is a cst.IndentedBlock (the function’s code block)..body (of IndentedBlock) is a list of statements inside the block.
      # So, .body.body accesses the list of statements inside the function.
      body = list(updated_node.body.body)
      insert_at = 0
      # If first line is a docstring, insert after it
      if (body and isinstance(body[0], cst.SimpleStatementLine) and
          isinstance(body[0].body[0], cst.Expr) and
          isinstance(body[0].body[0].value, cst.SimpleString)):
        insert_at = 1

      # Minimal idempotency check: only insert if not already present
      already_present = any(
        isinstance(stmt, cst.SimpleStatementLine) and
        any(
          isinstance(expr, cst.Assign) and
          any(
            isinstance(target.target, cst.Name) and target.target.value == "LLM_TIMEOUT_SECONDS"
            for target in expr.targets
          )
          for expr in stmt.body if isinstance(expr, cst.Assign)
        )
        for stmt in body
      )

      if not already_present:
        # Parse the assignment statement with comment
        assign = cst.parse_statement("# Timeout for LLM API calls in seconds: Gemini is killing me and getting stuck forever ...\n"
                                     "LLM_TIMEOUT_SECONDS = 20")
        body.insert(insert_at, assign)
        updated_node = updated_node.with_changes(body=updated_node.body.with_changes(body=body))

    self.in_get_next_action = False
    self.in__run_planner = False
    return updated_node

  # leave_Await is called after visiting the child of an await expression node
  def leave_Await(self, original_node, updated_node):
    # Match self.llm.ainvoke(...) or structured_llm.ainvoke(...) or self.settings.planner_llm.ainvoke(...)
    # 'value' is the object before the dot (e.g., structured_llm.ainvoke → structured_llm is the value, ainvoke is the 'attr').
    # the case self.llm.ainvoke is sadly, more complicated: ainvoke is still the 'attr' but self.llm is in itself composed by
    # a 'value' self and 'attr' llm
    if m.matches(
        updated_node.expression,
        m.Call(
          func=m.Attribute(
            value=m.OneOf(
              m.Attribute(value=m.Name("self"), attr=m.Name("llm")),
              m.Name("structured_llm"),
              m.Attribute(value=m.Attribute(value=m.Name("self"), attr=m.Name("settings")),attr=m.Name("planner_llm"))
            ),
            attr=m.Name("ainvoke")
          )
        )
    ):
      new_call = cst.parse_expression(
        f"asyncio.wait_for({cst.Module([]).code_for_node(updated_node.expression)}, timeout=LLM_TIMEOUT_SECONDS)"
      )
      return updated_node.with_changes(expression=new_call)

    return updated_node
