import libcst as cst


class DomViewsTransformer(cst.CSTTransformer):

  NEW_FUNC_CODE = '''
@property
def children_and_shadow_roots(self) -> list['EnhancedDOMTreeNode']:
  """
  Returns all children nodes, including shadow roots
  """
  # MOU14. The fix is to change the property to create a new list, preventing the modification of the original node. THANKS GEMINI ...
  # children = self.children_nodes or []
  # if self.shadow_roots:
  # 	children.extend(self.shadow_roots)
  # return children
  return (self.children_nodes or []) + (self.shadow_roots or [])
'''

  def leave_FunctionDef(self, original_node, updated_node):
    if original_node.name.value == "children_and_shadow_roots":
      new_func = cst.parse_module(self.NEW_FUNC_CODE).body[0]  # parse entire function as module, get first stmt (FunctionDef) => possible saviour
      return new_func

    return updated_node
