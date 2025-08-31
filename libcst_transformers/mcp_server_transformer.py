import libcst as cst

# Simplifying things, this code can be brittle, but it is extremely easy to read ... Definitely a saviour ...
class MCPServerTransformer(cst.CSTTransformer):
  def leave_FunctionDef(self, original_node, updated_node):
    if updated_node.name.value == "run":
      # Identify the target line using a string match
      target_line = "async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):"

      # Determine the matching statement and where to insert above it
      new_body = []
      for stmt in updated_node.body.body:
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if (expr_code.startswith(target_line)):
          # New statements to insert
          new_stmts = [
            cst.EmptyLine(),
            cst.EmptyLine(comment=cst.Comment(
              "# THERE WAS A VERY STRANGE ERROR HERE CAUSED BY 'from . import _multiarray_umath' GETTING FOREVER BLOCKED WHEN numpy WAS IMPORTED AS A RESULT OF")),
            cst.EmptyLine(comment=cst.Comment(
              "# THE USE OF re-cdp-patches. PRE-IMPORTING HERE THE MODULE SEEMS TO AVOID THE PROBLEM ...")),
            cst.parse_statement("import numpy as np"),
          ]
          new_body.extend(new_stmts)
        new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node
