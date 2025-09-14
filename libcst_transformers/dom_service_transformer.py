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

    # THEY WERE LEAVING OUT IMPORTANT FRAMES ...
    if "width >= 200 and height >= 200" in condition_code:
      new_test = cst.parse_expression("width >= 1 and height >= 1")
      return updated_node.with_changes(test=new_test)

    return updated_node

  def leave_Comment(self, original_node: cst.Comment, updated_node: cst.Comment) -> cst.Comment:
    if "Only process if iframe is at least 200px in both dimensions" in original_node.value:
      return updated_node.with_changes(value="# Only process if iframe is at least 1px in both dimensions")

    return updated_node
