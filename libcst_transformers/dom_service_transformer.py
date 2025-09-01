import libcst as cst
from libcst import Assign


class DomServiceTransformer(cst.CSTTransformer):

  # Kind of hellish but I'm fed up with this crap ...
  def leave_If(self, original_node: cst.If, updated_node: cst.If) -> cst.If:
    # Match the specific if statement with condition float(opacity) <= 0
    condition_code = cst.Module([]).code_for_node(updated_node.test).strip()
    if condition_code == "float(opacity) <= 0":
      # Create the new inner if statement with comment preserved
      inner_if = cst.If(
        test=cst.parse_expression("not (node.node_name.upper() == 'INPUT' and node.ax_node.role.lower() == 'checkbox' and visibility == 'visible')"),
        body=cst.IndentedBlock(body=[cst.parse_statement("return False")]),
        leading_lines=[cst.EmptyLine(comment=cst.Comment("# The very special case of Cloudflare checkbox. It has opacity = 0, but is perfectly visible ..."))],
      )
      # Create the new outer if body with inner if, replacing the return statement
      new_body = cst.IndentedBlock(body=[inner_if])
      return updated_node.with_changes(body=new_body)

    return updated_node
