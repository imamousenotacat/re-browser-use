import libcst as cst


class AboutBlankWatchdogTransformer(cst.CSTTransformer):

  def leave_SimpleStatementLine(self, original_node, updated_node):
    target_line = "await temp_session.cdp_client.send.Runtime.evaluate(params={'expression': script}, session_id=temp_session.session_id)"
    expr_code = cst.Module([]).code_for_node(original_node.body[0]).strip()
    if expr_code.strip() == target_line.strip():
      return cst.FlattenSentinel([
        # I thought that I would need a 'pass' sentence here, but I don't
        cst.EmptyLine(comment=cst.Comment(f"# {target_line}")),
      ])

    return updated_node
