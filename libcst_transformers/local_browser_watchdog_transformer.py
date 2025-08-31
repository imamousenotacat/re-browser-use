import libcst as cst


class LocalBrowserWatchdogTransformer(cst.CSTTransformer):

  # Ugly but quick and easy to read ...
  def leave_SimpleStatementLine(self, original_node, updated_node):
    target_line = "subprocess = await asyncio.create_subprocess_exec"
    expr_code = cst.Module([]).code_for_node(original_node.body[0]).strip()
    if expr_code.strip().startswith(target_line):
      return cst.FlattenSentinel([
        cst.parse_statement('launch_args.append("about:blank") # To avoid unnecessary redirections ...'),
        updated_node,
      ])

    return updated_node
