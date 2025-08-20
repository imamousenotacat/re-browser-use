import libcst as cst


# Hellish, look at the simplicity of ConfTestTransformer instead ...
class TestControllerTransformer(cst.CSTTransformer):

  def leave_FunctionDef(self, original_node, updated_node):
    # Only target the function named "browser_session"
    if updated_node.name.value != "browser_session":
        return updated_node

    new_decorators = []
    for d in updated_node.decorators:
      dec = d.decorator
      if (
          isinstance(dec, cst.Call) and
          getattr(dec.func, "attr", None) and dec.func.attr.value == "fixture"
      ):
        args = [
          a.with_changes(value=cst.SimpleString("'function'"))
          if (
              getattr(a, "keyword", None) and a.keyword.value == "scope" and
              getattr(a.value, "evaluated_value", None) == "module"
          ) else a
          for a in dec.args
        ]
        d = d.with_changes(decorator=dec.with_changes(args=args))
      new_decorators.append(d)
    return updated_node.with_changes(decorators=new_decorators)
