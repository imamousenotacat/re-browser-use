import libcst as cst


class DomSerializerTransformer(cst.CSTTransformer):
  target_line = "self._clickable_cache: dict[int, bool] = {}"

  def leave_SimpleStatementLine(self, original_node, updated_node):
    expr_code = cst.Module([]).code_for_node(original_node.body[0]).strip()

    if expr_code.strip() == self.target_line.strip():
      # Replacing the line we want is as simple as this (well keeping the existing comment requires a little bit of additional trickery ...)
      comment_text = original_node.leading_lines[0].comment.value
      return cst.SimpleStatementLine(
        body=[cst.parse_statement("self._clickable_cache: dict[str, bool] = {}").body[0]],
        leading_lines=[cst.EmptyLine(comment=cst.Comment(comment_text))]
      )

    return updated_node

  NEW_FUNC_CODE = '''
def _is_interactive_cached(self, node: EnhancedDOMTreeNode) -> bool:
  """Cached version of clickable element detection to avoid redundant calls."""
  # TODO: MOU14 You can't use node_id or backend_node_id as keys because they are not unique in different targets
  _clickable_cache_key = f'{node.node_id}_{node.target_id}'
  if _clickable_cache_key not in self._clickable_cache:
    import time

    start_time = time.time()
    result = ClickableElementDetector.is_interactive(node)
    end_time = time.time()

    if 'clickable_detection_time' not in self.timing_info:
      self.timing_info['clickable_detection_time'] = 0
    self.timing_info['clickable_detection_time'] += end_time - start_time

    self._clickable_cache[_clickable_cache_key] = result

  return self._clickable_cache[_clickable_cache_key]
'''

  def leave_FunctionDef(self, original_node, updated_node):
    if original_node.name.value == "_is_interactive_cached":
      new_func = cst.parse_module(self.NEW_FUNC_CODE)  # parse entire function as module, get first stmt (FunctionDef) => possible saviour
      return new_func

    return updated_node
