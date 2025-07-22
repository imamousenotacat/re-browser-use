import libcst as cst

class AgentServiceTransformer(cst.CSTTransformer):

  def leave_ClassDef(self, original_node, updated_node):
    # Filter for the class named "Agent"
    if original_node.name.value == "Agent":
      method_node = cst.parse_statement(method_code)  # This gives you a SimpleStatementLine or FunctionDef
      # Insert at the end of the class body
      new_body = list(updated_node.body.body) + [method_node]
      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

method_code = '''
@staticmethod
async def create_stealth_agent(task, llm, browser_session=None, headless=False):
  """I want to bypass entirely the by default initialization method."""
  if not browser_session:
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