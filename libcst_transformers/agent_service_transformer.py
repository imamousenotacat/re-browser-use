import libcst as cst
import libcst.matchers as m

# Timeout for LLM API calls in seconds: Gemini is killing me and getting stuck forever ...
class AgentServiceTransformer(cst.CSTTransformer):

  def __init__(self):
    self.in_get_next_action = False
    self.class_stack = []

  def visit_ClassDef(self, node):
    self.class_stack.append(node.name.value)
    # print(f"class_stack={self.class_stack}")

  # visit_FunctionDef is called when entering a function definition node, before visiting its body
  def visit_FunctionDef(self, node):
    # LibCST traverses the entire file and look for any function named get_next_action, regardless of class
    # if node.name.value == "get_next_action" and self.current_class == "Agent":
    if node.name.value == "get_next_action" and self.class_stack and self.class_stack[-1] == "Agent":
      self.in_get_next_action = True

  # leave_FunctionDef is called after visiting all children (body, decorators, etc.) of the function definition node
  def leave_FunctionDef(self, original_node, updated_node):
    if self.in_get_next_action:
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
    return updated_node

  # leave_Await is called after visiting the child of an await expression node
  def leave_Await(self, original_node, updated_node):
    if self.in_get_next_action:
      # Match await self.llm.ainvoke(...) or await structured_llm.ainvoke(...)
      # 'value' is the object before the dot (e.g., structured_llm.ainvoke → structured_llm is the value, ainvoke is the 'attr').
      # the case self.llm.ainvoke is sadly, more complicated: ainvoke is still the 'attr' but self.llm is in itself composed by
      # a 'value' self and 'attr' llm
      if m.matches(
          updated_node.expression,
          m.Call(func=m.Attribute(value=m.OneOf(m.Attribute(value=m.Name("self"), attr=m.Name("llm")), m.Name("structured_llm")),
                                  attr=m.Name("ainvoke")))):
        new_call = cst.parse_expression(
          f"asyncio.wait_for({cst.Module([]).code_for_node(updated_node.expression)}, timeout=LLM_TIMEOUT_SECONDS)"
        )
        return updated_node.with_changes(expression=new_call)

    return updated_node

  # Solving the problem with the tests ValueError: EventBus with name "Agent" already exists. Please choose a unique name or let it auto-generate.
  def leave_Assign(self, original_node, updated_node):
    # Match: self.eventbus = EventBus(name='Agent', wal_path=wal_path)
    pattern = m.Assign(
      targets=[m.AssignTarget(target=m.Attribute(value=m.Name("self"), attr=m.Name("eventbus")))],
      value=m.Call(
        func=m.Name("EventBus"),
        args=[
          m.Arg(keyword=m.Name("name"), value=m.SimpleString("'Agent'")),
          m.Arg(keyword=m.Name("wal_path"), value=m.Name("wal_path")),
        ]
      )
    )
    if m.matches(updated_node, pattern):
      # Construct the new name argument
      new_name_expr = cst.parse_expression("f'Agent_{str(self.id)[-4:]}'")
      new_args = [
        cst.Arg(keyword=cst.Name("name"), value=new_name_expr),
        cst.Arg(keyword=cst.Name("wal_path"), value=cst.Name("wal_path")),
      ]
      new_value = cst.Call(
        func=cst.Name("EventBus"),
        args=new_args
      )
      return updated_node.with_changes(value=new_value)

    return updated_node

  def leave_ClassDef(self, original_node, updated_node):
    self.class_stack.pop()
    # Filter for the class named "Agent"
    if original_node.name.value == "Agent":
      method_node = cst.parse_statement(method_code)  # This gives you a SimpleStatementLine or FunctionDef
      # Insert at the end of the class body
      new_body = list(updated_node.body.body) + [method_node]
      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

method_code = '''
@staticmethod
async def create_stealth_agent(task, llm, headless=False):
  """I want to bypass entirely the by default initialization method."""

  browser_session = await BrowserSession.create_stealth_browser_session(headless=headless)
  agent = Agent(
    task=task,
    llm=llm,
    browser_session=browser_session,
    # I don't want vision or memory ...
    enable_memory=False,
    use_vision=False,
    # I don't want to waste calls to the LLM. I'm using ChatGoogleGenerativeAI ...
    tool_calling_method='function_calling'
  )

  return agent
'''