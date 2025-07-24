import libcst as cst
from libcst import matchers as m


class ChatGoogleTransformer(cst.CSTTransformer):

  def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
    new_body = []
    for stmt in updated_node.body:
      # Insert import logging after import json once
      if (
          isinstance(stmt, cst.SimpleStatementLine)
          and len(stmt.body) == 1
          and isinstance(stmt.body[0], cst.Import)
          and any(alias.name.value == "json" for alias in stmt.body[0].names)
      ):
        new_body.append(stmt)
        import_logging = cst.SimpleStatementLine(
          body=[cst.Import(names=[cst.ImportAlias(name=cst.Name("logging"))])]
        )
        new_body.append(import_logging)
        continue
      # Insert logger assignment before the target function definition once
      if (
          isinstance(stmt, cst.FunctionDef)
          and stmt.name.value == "_is_retryable_error"
      ):
        logger_assign = cst.parse_statement(
          "\nlogger = logging.getLogger(__name__)"
        )
        new_body.append(logger_assign)

      new_body.append(stmt)

    return updated_node.with_changes(body=new_body)

  def leave_SimpleStatementLine(self, original_node, updated_node):
    if (len(updated_node.body) == 1
        and m.matches(
          updated_node.body[0],
          m.Assign(
            targets=[m.AssignTarget(target=m.Name("delay"))],
            value=m.Call(func=m.Name("min")))
        )
    ):
      return cst.FlattenSentinel([
        updated_node,
        cst.parse_statement("error_msg = str(e)"),
        cst.parse_statement("prefix = f'❌ Invocation to LLM number {attempt} failed. Waiting for {delay} seconds before retrying:\\n '"),
        cst.parse_statement("logger.error(f'{prefix}{error_msg}')"),
      ])

    return updated_node

  NEW_FUNC_CODE = '''
def get_client(self) -> genai.Client:
    """
    Returns a genai.Client instance.

    Returns:
        genai.Client: An instance of the Google genai client.
    """
    # This was suggested to me by Perplexity and, empirically, it seems to reduce the number of 429 RESOURCE_EXHAUSTED errors.
    if not self.client:
        client_params = self._get_client_params()
        self.client = genai.Client(**client_params)
        
    return self.client
'''

  def leave_FunctionDef(self, original_node, updated_node):
    if updated_node.name.value == "_make_api_call":
      body = list(updated_node.body.body)
      insert_at = 0

      # Insert after docstring if present
      if (
          body
          and isinstance(body[0], cst.SimpleStatementLine)
          and isinstance(body[0].body[0], cst.Expr)
          and isinstance(body[0].body[0].value, cst.SimpleString)
      ):
        insert_at = 1

      # Use parse_statement for valid statements only:
      stmts = [
        cst.parse_statement("import asyncio"),
        cst.parse_statement("LLM_TIMEOUT_SECONDS = 20"),
      ]

      # Attach comment as leading comment on the assignment stmt
      stmts[1] = stmts[1].with_changes(
        leading_lines=[cst.EmptyLine(comment=cst.Comment("# Timeout for LLM API calls in seconds: Gemini is killing me and getting stuck forever ..."))]
      )

      for stmt in reversed(stmts):
        body.insert(insert_at, stmt)

      updated_node = updated_node.with_changes(body=updated_node.body.with_changes(body=body))

    if original_node.name.value == "get_client":
      new_func = cst.parse_module(self.NEW_FUNC_CODE).body[0]  # parse entire function as module, get first stmt (FunctionDef)
      return new_func

    return updated_node

  # leave_Await is called after visiting the child of an await expression node
  def leave_Await(self, original_node, updated_node):
    # Get code string of the expression safely
    expr_code = cst.Module([]).code_for_node(updated_node.expression)

    if expr_code.startswith("self.get_client().aio.models.generate_content"):
      new_call = cst.parse_expression(
        f"asyncio.wait_for({expr_code}, timeout=LLM_TIMEOUT_SECONDS)"
      )
      return updated_node.with_changes(expression=new_call)

    return updated_node

  def leave_ClassDef(self, original_node, updated_node):
    if original_node.name.value == "ChatGoogle":
      target_line = "http_options: types.HttpOptions | types.HttpOptionsDict | None = None"

      new_stmts = [
        cst.EmptyLine(),
        cst.EmptyLine(comment=cst.Comment(
          "# This was suggested to me by Perplexity and, empirically, it seems to reduce the number of 429 RESOURCE_EXHAUSTED errors.")),
        cst.parse_statement("client: genai.Client | None = None\n"),
        cst.EmptyLine()
      ]

      old_body = list(updated_node.body.body)

      idx = None
      for i, stmt in enumerate(old_body):
        # Use Module([]).code_for_node(node)
        if cst.Module([]).code_for_node(stmt).strip() == target_line:
          idx = i
          break

      new_body = old_body[:idx + 1] + new_stmts + old_body[idx + 1:]

      return updated_node.with_changes(
        body=updated_node.body.with_changes(body=tuple(new_body))
      )

    return updated_node
