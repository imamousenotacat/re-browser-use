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
