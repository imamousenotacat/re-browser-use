import libcst as cst


class DomWatchdogTransformer(cst.CSTTransformer):

  def leave_Call(self, original_node, updated_node):
    if (
        isinstance(original_node.func, cst.Attribute) and
        isinstance(original_node.func.value, cst.Name) and
        original_node.func.value.value == "self" and
        original_node.func.attr.value == "_build_dom_tree_without_highlights"
    ):
      new_func = original_node.func.with_changes(attr=cst.Name("_build_dom_tree"))
      return updated_node.with_changes(func=new_func)

    return updated_node
