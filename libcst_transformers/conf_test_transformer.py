import libcst as cst

# possible saviour 
class ConfTestTransformer(cst.CSTTransformer):
  def leave_FunctionDef(self, original_node, updated_node):
    # Only transform the function named "browser_session"
    if updated_node.name.value != "browser_session":
      return updated_node

    target_code = "pytest.fixture(scope='module')"
    replacement_code = "pytest.fixture(scope='function')"

    # Parse expressions once
    target_node = cst.parse_expression(target_code)
    replacement_node = cst.parse_expression(replacement_code)

    new_decorators = []
    for decorator in updated_node.decorators:
      # Compare nodes structurally
      if decorator.decorator.deep_equals(target_node):
        # Replace with the new decorator node
        new_decorator = decorator.with_changes(decorator=replacement_node)
        new_decorators.append(new_decorator)
      else:
        new_decorators.append(decorator)

    return updated_node.with_changes(decorators=new_decorators)
