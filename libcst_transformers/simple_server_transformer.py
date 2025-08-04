import libcst as cst

# Simplifying things, this code can be brittle, but it is extremely easy to read ...
class SimpleServerTransformer(cst.CSTTransformer):
  def leave_FunctionDef(self, original_node, updated_node):
    if updated_node.name.value == "run_simple_browser_automation":
      # Identify the target line using a string match
      target_line = "server_params = StdioServerParameters(command='uvx', args=['browser-use', '--mcp'], env={})"

      # Determine the matching statement and where to insert above it
      new_body = []
      for stmt in updated_node.body.body:
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if (target_line in expr_code):
          # New statements to insert. As the leading comments don't have identity on their own I need to reintroduce them here again
          new_stmts = [
            cst.EmptyLine(),
            cst.EmptyLine(comment=cst.Comment("# Create connection parameters for the browser-use MCP server")),
            cst.EmptyLine(comment=cst.Comment("# server_params = StdioServerParameters(command='uvx', args=['browser-use', '--mcp'], env={}) =>  Error: unhandled errors in a TaskGroup (1 sub-exception)")),
            cst.parse_statement("server_params = StdioServerParameters(command='python', args=['-m', 'browser_use.cli', '--mcp'], env={})"),
            cst.EmptyLine(comment=cst.Comment("# server_params = StdioServerParameters(command='uvx', args=['re-browser-use[cli]', '--mcp'], env={})")),
          ]
          new_body.extend(new_stmts)
        else:
          new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node
