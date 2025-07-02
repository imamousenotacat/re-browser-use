import libcst as cst
import libcst.matchers as m
from libcst.metadata import PositionProvider


class DomServiceTransformer(cst.CSTTransformer):
  """
  Transformer to apply the following changes:
  - Add new imports as specified.
  - Update function signatures with new parameters.
  - Add new keys to argument dict.
  - Modify evaluation logic to use target_frame if present.
  """
  METADATA_DEPENDENCIES = (PositionProvider,)

  def __init__(self):
    super().__init__()
    self.function_stack = []

  def visit_FunctionDef(self, node):
    self.function_stack.append(node.name.value)

  # This function gets invoked once after the entire module and all its children have been visited.
  def leave_Module(self, original_node, updated_node):
    # Insert import asyncio at the very top
    asyncio_import = cst.SimpleStatementLine(
      body=[cst.Import(names=[cst.ImportAlias(name=cst.Name("asyncio"))])]
    )

    # Only add if not already present
    body = list(updated_node.body)
    for stmt in body:
      if (
          isinstance(stmt, cst.SimpleStatementLine)
          and len(stmt.body) == 1
          and isinstance(stmt.body[0], cst.Import)
          and any(alias.name.value == "asyncio" for alias in stmt.body[0].names)
      ):
        asyncio_import = None

    # Insert the rest of the imports after the last one
    insert_idx = 0
    for i, stmt in enumerate(body):
      if (
          isinstance(stmt, cst.SimpleStatementLine)
          and isinstance(stmt.body[0], cst.ImportFrom)
      ):
        insert_idx = i + 1

    # Prepare new statements
    new_stmts = [
      cst.parse_statement("from browser_use.dom.dom_utils import DomUtils, FramesDescriptorDict"),
      cst.parse_statement("from playwright.async_api import Frame, JSHandle"),
    ]
    # Check if already present
    for i in range(len(body) - len(new_stmts) + 1):
      if all(
          isinstance(body[i + j], cst.SimpleStatementLine)
          and str(body[i + j]).strip() == str(new_stmts[j]).strip()
          for j in range(len(new_stmts))
      ):
        new_stmts = []
        break

    body = ([asyncio_import] if asyncio_import else []) + body[:insert_idx] + new_stmts + body[insert_idx:]

    return updated_node.with_changes(body=body)

  # from typing import TYPE_CHECKING, Optional, Callable, Awaitable
  def leave_ImportFrom(self, original_node, updated_node):
    if (
        isinstance(updated_node.module, cst.Name)
        and updated_node.module.value == "typing"
        and any(alias.name.value == "TYPE_CHECKING" for alias in updated_node.names)
        and len(updated_node.names) == 1
    ):
      return updated_node.with_changes(
        names=[
          cst.ImportAlias(name=cst.Name("TYPE_CHECKING")),
          cst.ImportAlias(name=cst.Name("Optional")),
          cst.ImportAlias(name=cst.Name("Callable")),
          cst.ImportAlias(name=cst.Name("Awaitable")),
        ]
      )

    return updated_node

  # Update function signatures with new parameters.
  # I haven't found a way to set each parameter in a different line. I give up for the moment
  def leave_FunctionDef(self, original_node, updated_node):
    self.function_stack.pop()
    if (original_node.name.value == "_build_dom_tree" and
        isinstance(updated_node.params, cst.Parameters)
    ):
      # Add parameters
      params = list(updated_node.params.params)
      if not any(p.name.value == "target_frame" for p in params):
        params.extend(
          [cst.Param(
            name=cst.Name("target_frame"),
            annotation=cst.Annotation(
              annotation=cst.Subscript(
                value=cst.Name("Optional"),
                slice=[
                  cst.SubscriptElement(
                    slice=cst.Index(value=cst.Name("Frame"))
                  )
                ]
              )
            ),
            default=cst.Name("None"),
          ),
            cst.Param(
              name=cst.Name("highlight_index"),
              annotation=cst.Annotation(cst.Name("int")),
              default=cst.Integer("0")
            ),
            cst.Param(
              name=cst.Name("initial_root_node"),
              annotation=cst.Annotation(
                annotation=cst.Subscript(
                  value=cst.Name("Optional"),
                  slice=[
                    cst.SubscriptElement(
                      slice=cst.Index(value=cst.Name("JSHandle"))
                    )
                  ]
                )
              ),
              default=cst.Name("None"),
            )]
        )
        return updated_node.with_changes(params=updated_node.params.with_changes(params=params))

    return updated_node

  # Add new keys to the dictionary being built
  # I haven't found a way to set each new key in a different line. I give up for the moment
  def leave_Assign(self, original_node, updated_node):
    if (
        self.function_stack and
        self.function_stack[-1] == "_build_dom_tree" and
        isinstance(original_node.targets[0].target, cst.Name) and
        original_node.targets[0].target.value == "args" and
        isinstance(original_node.value, cst.Dict)
    ):
      keys = [k.key for k in updated_node.value.elements if isinstance(k.key, cst.SimpleString) or isinstance(k.key, cst.Name)]
      new_elements = list(updated_node.value.elements)
      key_names = set()
      for k in keys:
        if isinstance(k, cst.SimpleString):
          key_names.add(k.value.strip("'").strip('"'))
        elif isinstance(k, cst.Name):
          key_names.add(k.value)
      # Add 'initialRootNode' and 'highlightIndex' if not present
      if "initialRootNode" not in key_names:
        new_elements.append(
          cst.DictElement(
            key=cst.SimpleString("'initialRootNode'"),
            value=cst.Name("initial_root_node")
          )
        )
      if "highlightIndex" not in key_names:
        new_elements.append(
          cst.DictElement(
            key=cst.SimpleString("'highlightIndex'"),
            value=cst.Name("highlight_index")
          )
        )
      return updated_node.with_changes(
        value=updated_node.value.with_changes(elements=new_elements)
      )

    return updated_node

  # Modify evaluation logic to use target_frame if present.
  def leave_SimpleStatementLine(self, original_node, updated_node):
    # Only handle lines with a single AnnAssign
    if (
        len(updated_node.body) == 1
        and isinstance(updated_node.body[0], cst.AnnAssign)
    ):
      annassign = updated_node.body[0]
      # Match your assignment: eval_page: dict = await self.page.evaluate(self.js_code, args)
      if (self.function_stack and self.function_stack[-1] == "_build_dom_tree" and
          isinstance(annassign.target, cst.Name)
          and annassign.target.value == "eval_page"
          and isinstance(annassign.annotation.annotation, cst.Name)
          and annassign.annotation.annotation.value == "dict"
          and isinstance(annassign.value, cst.Await)
          and isinstance(annassign.value.expression, cst.Call)
          and isinstance(annassign.value.expression.func, cst.Attribute)
          and isinstance(annassign.value.expression.func.value, cst.Attribute)
          and annassign.value.expression.func.value.attr.value == "page"
          and annassign.value.expression.func.attr.value == "evaluate"
      ):
        # Build the assignment for target_frame
        target_frame_eval = annassign.with_changes(
          value=cst.Await(
            expression=annassign.value.expression.with_changes(
              func=annassign.value.expression.func.with_changes(
                value=cst.Name("target_frame")
              )
            )
          )
        )
        # Return an If node (not a list)
        return cst.If(
          test=cst.Name("target_frame"),
          body=cst.IndentedBlock([
            cst.SimpleStatementLine([target_frame_eval])
          ]),
          orelse=cst.Else(
            body=cst.IndentedBlock([
              cst.SimpleStatementLine([annassign])
            ])
          )
        )

    return updated_node

  def leave_ClassDef(self, original_node, updated_node):
    # Filter for the class named "DomService"
    if original_node.name.value == "DomService":
      method_node = cst.parse_statement(method_code)  # This gives you a SimpleStatementLine or FunctionDef
      # Insert at the end of the class body
      new_body = list(updated_node.body.body) + [method_node]
      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

method_code = '''
@time_execution_async('--get_multitarget_clickable_elements')
async def get_multitarget_clickable_elements(
  self,
  highlight_elements: bool = True,
  focus_element: int = -1,
  viewport_expansion: int = 0,
  remove_highlights: Optional[Callable[..., Awaitable[None]]] = None,
) -> DOMState:
  dom_utils = DomUtils()

  frames_descriptor_dict:FramesDescriptorDict = await dom_utils.build_frames_descriptor_dict(self.page)

  if remove_highlights:
    tasks = [] # Trying to minimize the ugly visual effect by parallelizing the execution ...
    for frame in frames_descriptor_dict.keys():
      tasks.append(remove_highlights(frame))
    await asyncio.gather(*tasks)

  final_dom_element_node, dom_element_node, final_selector_map, highlight_index = None, None, {}, 0
  for frame, closed_shadow_roots in frames_descriptor_dict.items():
    # look in 'final_dom_element_node' for the point to link this new 'document.body' ...
    iframe_element = await DomUtils.get_insertion_point_for_body(final_dom_element_node, frame)
    if frame == self.page.main_frame or iframe_element:
      # If there is no iframe_element there is no point in doing anything ...
      # Always evaluating in document.body ...
      self.logger.info(f"Evaluating in frame with url=[{frame.url}] using document.body ...")
      dom_element_node, selector_map = \
        await self._build_dom_tree(highlight_elements, focus_element, viewport_expansion, frame, highlight_index)
      highlight_index += len(selector_map)
      final_selector_map.update(selector_map)
      if frame == self.page.main_frame:
        final_dom_element_node = dom_element_node
      else:
        assert final_dom_element_node is not None
        if iframe_element:
          # Verify if iframe_element has a 'html' child, which in turn has a 'body' child.
          body = await DomUtils.traverse_and_filter(iframe_element,
                                                    lambda node: asyncio.sleep(0, result=(node.xpath == "html/body")),
                                                    just_first_found=True)
        if body:
          DomUtils.copy_children(dom_element_node, body[0])
        else:
          # We link here the document.body itself ... it's more elegant ;-|
          dom_element_node.parent = iframe_element
          iframe_element.children.append(dom_element_node)

      # Dealing with closed ShadowRoot objects in the Frame ...
      for closed_shadow_root in closed_shadow_roots:
        self.logger.info(f"Evaluating in frame with url=[{frame.url}] using specific root node {closed_shadow_root.element_handle_to_shadow_root} ...")
        dom_element_node, selector_map = \
          await self._build_dom_tree(highlight_elements, focus_element, viewport_expansion, frame, highlight_index,
                        closed_shadow_root.element_handle_to_shadow_root)
        highlight_index += len(selector_map)
        final_selector_map.update(selector_map)
        # Look in 'final_dom_element_node' for the point to link the 'dom_element_node' corresponding to the closed ShadowRoot
        # HERE THE MATCHING IS EASY: LOOK FOR A MATCHING "xpath" IN 'final_dom_element_node' AND ADD TO THE FOUND
        # DOMElementNode THE CHILDREN OF 'dom_element_node'
        host_elements: list[DOMElementNode] = \
          await DomUtils.traverse_and_filter(final_dom_element_node,
                          lambda node, target_xpath: asyncio.sleep(0, result=(node.xpath == target_xpath)),
                          # This is passed as an argument to the lambda (not needed it's here as an example)
                          dom_element_node.xpath)
        if host_elements and len(host_elements) > 1:
          # If there is more than one matching xpath the Frame must match also ...
          host_elements = [host for host in host_elements if DomUtils.is_matching_iframe(frame, await DomUtils.find_parent_iframe(host))]
        assert len(host_elements) == 1, (
            f"There should be one and only one element matching the xpath [{dom_element_node.xpath}] for the closed shadow root...")
        host = host_elements[0]
        host.shadow_root = True
        DomUtils.copy_children(dom_element_node, host)
        await closed_shadow_root.element_handle_to_shadow_root.dispose()

  # After connecting the different element trees we return the root one ...
  assert final_dom_element_node is not None
  return DOMState(element_tree=final_dom_element_node, selector_map=final_selector_map)
'''
