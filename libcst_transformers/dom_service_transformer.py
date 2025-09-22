import libcst as cst
from textwrap import dedent


class DomServiceTransformer(cst.CSTTransformer):

  def __init__(self):
    super().__init__()
    self.target_line_2_replaced = False

  # TODO: GLOBAL SAVIOUR FUNCTION
  #  The initial comments in a block of code were being ignored when used in a replacement operation
  def _parse_and_fix_leading_comments(self, replacement_code):
    replacement_module = cst.parse_module(dedent(replacement_code))
    first_stmt = replacement_module.body[0]
    comments = []
    # LibCST >=0.4.0: module-level comments are in .header (older versions: not available)
    if hasattr(replacement_module, "header"):
      for leading_line in replacement_module.header:
        if isinstance(leading_line, cst.EmptyLine) or leading_line.comment:
          comments.append(leading_line)
    if comments:
      first_stmt = first_stmt.with_changes(leading_lines=comments + list(first_stmt.leading_lines))
      new_body = (first_stmt,) + replacement_module.body[1:]
    else:
      new_body = replacement_module.body

    return new_body

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

  def leave_FunctionDef(self, original_node, updated_node):
    if updated_node.name.value == "is_element_visible_according_to_all_parents":
      avoiding_mutable_modification = '''
# Make a copy of the bounds to avoid modifying the original object in-place.
# DOMRect is a mutable dataclass, so direct assignment is a reference.
current_bounds = DOMRect(x=current_bounds.x, y=current_bounds.y, width=current_bounds.width, height=current_bounds.height)
'''
      target_line = "if not current_bounds:"

      new_body = []
      for stmt in updated_node.body.body:
        new_body.append(stmt)
        # Determine the matching statement and where to insert below it ...
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if target_line in expr_code:
          body_including_comments = self._parse_and_fix_leading_comments(avoiding_mutable_modification)
          new_body.extend(body_including_comments)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    if original_node.name.value == "_construct_enhanced_node":
      ignoring_highlighting_nodes ='''
# The Node objects added by the highlighting are left out ...
if attributes and 'data-browser-use-highlight' in attributes:
  return None
'''
      target_line = "shadow_root_type = None"

      new_body = []
      for stmt in updated_node.body.body:
        # Determine the matching statement and where to insert avobt it ...
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if target_line in expr_code:
          body_including_comments = self._parse_and_fix_leading_comments(ignoring_highlighting_nodes)
          new_body.extend(body_including_comments)
        new_body.append(stmt)

      return updated_node.with_changes(
        body=updated_node.body.with_changes(body=new_body),
        returns=cst.Annotation(annotation=cst.parse_expression("EnhancedDOMTreeNode | None")))

    return updated_node

  def leave_SimpleStatementLine(self, original_node, updated_node):
    target_line_1 = "attributes[node['attributes'][i]] = node['attributes'][i + 1]"
    replacement_line_1 = '''# The attributes added by the highlighting are left out ...
if not node['attributes'][i].startswith("data-browser-use-id"): 
  attributes[node['attributes'][i]] = node['attributes'][i + 1]
'''
    # It's not worth doing anything more sophisticated ...
    target_line_2 = "dom_tree_node.content_document.parent_node = dom_tree_node"
    replacement_line_2 = "if dom_tree_node.content_document: dom_tree_node.content_document.parent_node = dom_tree_node"
    target_line_3 = "dom_tree_node.children_nodes.append("
    replacement_line_3="if child_node := await _construct_enhanced_node(child, updated_html_frames, total_frame_offset): dom_tree_node.children_nodes.append(child_node)"
    target_line_4=("return enhanced_dom_tree_node")

    expr_code = cst.Module([]).code_for_node(original_node.body[0]).strip()
    # print(f"PVM14 =>\n {expr_code} ")
    # Replacing the line we want is as simple as this ...
    if expr_code.strip() == target_line_1.strip():
      return cst.parse_statement(replacement_line_1)
    if expr_code.strip() == target_line_2.strip() and not self.target_line_2_replaced:
      self.target_line_2_replaced = True
      return cst.parse_statement(replacement_line_2)
    if target_line_3.strip() in expr_code.strip():
      return cst.parse_statement(replacement_line_3)
    if expr_code.strip() == target_line_4.strip():
      # To get the lining I want I have to do this crap
      return cst.FlattenSentinel([cst.EmptyLine(),
                                  cst.parse_statement("assert enhanced_dom_tree_node"),
                                  cst.parse_statement(target_line_4)])

    return updated_node

  def leave_IndentedBlock(self, original_node, updated_node):
    body = updated_node.body
    for i in range(len(body) - 1):
      line1_code = cst.Module([]).code_for_node(body[i]).strip()
      line2_code = cst.Module([]).code_for_node(body[i + 1]).strip()
      if ("shadow_root_node.parent_node = dom_tree_node" in line1_code and
          "dom_tree_node.shadow_roots.append(shadow_root_node)" == line2_code):
        new_if = cst.If(test=cst.Name("shadow_root_node"), body=cst.IndentedBlock(body=[body[i], body[i + 1]]))
        new_body = body[:i] + (new_if,) + body[i + 2:]
        return updated_node.with_changes(body=new_body)

    return updated_node
