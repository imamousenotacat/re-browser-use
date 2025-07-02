import asyncio
import logging
import re

from browser_use.dom.views import DOMElementNode, DOMBaseNode
from browser_use.logging_config import addLoggingLevel
from dataclasses import dataclass
from patchright.async_api import Error, Frame, Page, CDPSession, JSHandle
from typing import List, Tuple, Dict, Any, Protocol, Optional
from urllib.parse import urlparse

addLoggingLevel('TRACE', logging.DEBUG - 5) # to see TRACE level: pytest -v -rA -s --log-cli-level=5 tests\test_boot_detection.py

logger = logging.getLogger(__name__)

@dataclass
class ClosedShadowRootDescriptor:
  xpath_to_host: str
  element_handle_to_shadow_root: JSHandle


FramesDescriptorDict = Dict[Frame, List[ClosedShadowRootDescriptor]]


class FilterCallable(Protocol):
  async def __call__(self, node: DOMElementNode, *args: Any, **kwargs: Any) -> bool:
    ...


# TODO: I created this class to gather, for the moment, the functionality I'm writing. The methods in this class could probably be
#       declared as either @classmethod or @staticmethod. A) DISPOSE ALL THE HANDLES B) IS IT POSSIBLE TO MAKE THIS CLASS QUICKER? ...
class DomUtils:
  def _get_closed_shadow_roots_from_node(self, node: Dict, current_node_xpath: str, results: List[str]) -> List[str]:
    if not node or not isinstance(node, dict):
      return results

    # Check for shadow roots in the current node ...
    # Only elements (which have a localName) can host shadow roots. TODO: ???
    if node.get('localName') and 'shadowRoots' in node and isinstance(node.get('shadowRoots'), list):
      for shadow_root_item in node['shadowRoots']:
        if shadow_root_item.get('shadowRootType') == 'closed' and shadow_root_item.get('backendNodeId'):
          # 'current_node_xpath' is the XPath of 'node' (the host). This is what we record.
          logger.trace(f"DETECTED closed ShadowRoot. Host XPath: {current_node_xpath}. Host nodeName: {node.get('nodeName')}")
          results.append(current_node_xpath)
        # Recursively search *within* this shadow_root_item.
        self._get_closed_shadow_roots_from_node(shadow_root_item, current_node_xpath, results)

    # IFRAMEs HAVE children = [] THEY HAVE contentDocument INSTEAD ...
    if node.get('localName') and node.get('contentDocument'):
      # For content_doc_node, the XPath effectively resets. Its children (e.g. <html>) start from "/". TODO: I'M NOT SO SURE
      self._get_closed_shadow_roots_from_node(node['contentDocument'], "", results)

    # Process children nodes of 'node' 'node' can be an element, a #document, or a #document-fragment (shadow root)
    if 'children' in node and isinstance(node.get('children'), list):
      for child_dict in node['children']:
        # Calculate XPath segment for child_dict relative to 'node'
        child_segment = self._get_xpath_segment(child_dict, node)
        # Construct the full XPath for the child node => The XPath generated here must be exactly the same as the one obtained in buildDomTree.js.
        # That's the reason for the ugly line below (THIS IS NOT TRUE ANYMORE BUT FOR THE MOMENT I KEEP IT LIKE THIS)
        path_to_child_node = f"{current_node_xpath}/{child_segment}" if current_node_xpath and child_segment \
          else child_segment if child_segment else current_node_xpath
        self._get_closed_shadow_roots_from_node(child_dict, path_to_child_node, results)

    return results

  def _get_xpath_segment(self, child_dict: Dict, parent_dict: Dict) -> str:
    child_segment = ""
    tag_name = child_dict.get('localName', '').lower()
    if tag_name:  # It's an element
      # Indexing among siblings with the same tag name
      siblings_with_same_tag = [
        s for s in parent_dict['children']
        if s.get('localName', '').lower() == tag_name and s.get('nodeType') == 1  # Ensure it's an element node
      ]
      idx = 0
      for s_node in siblings_with_same_tag:
        idx += 1  # XPath indices are 1-based
        if s_node.get('backendNodeId') == child_dict.get('backendNodeId'):
          break

      child_segment = tag_name if idx == 1 else f"{tag_name}[{idx}]"

    return child_segment

  @staticmethod
  async def traverse_and_filter(root_node: DOMElementNode, filter_func: FilterCallable,
                                *args: Any, just_first_found: bool = False, **kwargs: Any) -> List[DOMElementNode]:
    """
    Traverses a DOMElementNode tree and returns elements matching a filter function.
    If just_first_found is True, returns a list with the first element found.
    """
    filtered_elements: List[DOMElementNode] = []

    async def _traverse(node: DOMBaseNode) -> bool:
      """Returns True if traversal should stop, False otherwise."""
      if isinstance(node, DOMElementNode):
        if await filter_func(node, *args, **kwargs):
          filtered_elements.append(node)
          if just_first_found:
            return True  # Stop traversal
        for child in node.children:
          if await _traverse(child):
            if just_first_found:  # Propagate stop signal
              return True
      # Text nodes do not have children to traverse
      return False  # Continue traversal

    await _traverse(root_node)
    return filtered_elements

  # There is a pretty similar function _convert_simple_xpath_to_css_selector
  def xpath_to_css(self, xpath: str) -> str:
    if not xpath:  # Handles None or empty string
      return ""

    stripped_xpath = xpath.strip('/')
    if not stripped_xpath:  # Handles cases like "/" or "//" which become empty after strip
      return ""

    segments = stripped_xpath.split('/')
    css_parts = []

    start_index = 0
    # Handle leading /html and /html/body based on the example's desired output
    if segments[0].lower() == 'html':
      if len(segments) > 1 and segments[1].lower() == 'body':
        css_parts.append('body')  # Add 'body' literally
        start_index = 2
      else:
        css_parts.append('html')  # Add 'html' literally
        start_index = 1

    # If xpath was just "/html" or "/html/body", the loop below will not run,
    # and css_parts will correctly be ['html'] or ['body'].
    # ' > '.join will then return 'html' or 'body'.

    # Process the remaining segments
    for i in range(start_index, len(segments)):
      segment_str = segments[i]
      # Regex to capture tag_name and optional [index]
      match = re.match(r'([a-zA-Z0-9_-]+)(?:\[(\d+)])?', segment_str)

      if not match:
        # This segment is not in 'tag' or 'tag[index]' format. TODO: I don't like it
        return f"Error: Unparseable XPath segment '{segment_str}' in '{xpath}'"

      tag_name = match.group(1)
      index_str = match.group(2)

      # Construct the CSS part for the current segment
      current_css_part = tag_name
      if index_str:
        current_css_part += f":nth-of-type({index_str})"
      css_parts.append(current_css_part)

    return ' > '.join(css_parts)

  def _get_all_frames_recursively(self, initial_frame: Frame) -> List[Frame]:
    frames = [initial_frame]
    # print(*main_frame.child_frames[1].child_frames,sep='\n')
    # TODO: THIS IS CRAZY YOU GET MORE THAN 15 FOR https://nopecha.com/demo/cloudflare
    for child_frame in initial_frame.child_frames:
      frames.extend(self._get_all_frames_recursively(child_frame))
    return frames

  # This is not returning all frames but those that can be reached through CDP
  async def _get_target_frames_and_cdp_sessions(self, page: Page) -> List[Tuple[Frame, CDPSession]]:
    # https://playwright.dev/python/docs/api/class-page#page-main-frame:
    # Page is guaranteed to have a main frame which persists during navigation.
    main_frame = page.main_frame
    logger.info(f"Page's main_frame={main_frame} ...")
    target_frames_and_cdp_sessions: List[Tuple[Frame, CDPSession]] = []
    all_frames = self._get_all_frames_recursively(main_frame)

    # Frames without content different from the main frame are irrelevant ...
    for frame in (f for f in all_frames if f.url != 'about:blank' or f == page.main_frame):
      cdp_session = await self._get_cdp_session_for_frame(page, frame)
      if cdp_session:
        target_frames_and_cdp_sessions.append((frame, cdp_session))

    return target_frames_and_cdp_sessions

  async def _get_cdp_session_for_frame(self, page: Page, frame: Frame) -> CDPSession | None:
    logger.trace(f"Trying to create CDPSession for frame={frame} ...")
    try:
      cdp_session = await page.context.new_cdp_session(frame)
      logger.trace(f"{type(cdp_session)} object created for Frame={frame} ...")
      return cdp_session
    except Error as e:
      # Avoiding the Error: BrowserContext.new_cdp_session:
      # This frame does not have a separate CDP session, it is a part of the parent frame's session
      # "This could probably be avoided by inspecting the URLs, but I’ll pass."
      logger.trace(f"Error [{e.message}] while creating CDPSession for frame={frame} ...")
      return None

  async def _get_xpaths_to_closed_shadow_roots_from_frame(self, cdp_session: CDPSession, frame: Frame) -> List[str]:
    # Get all in one go ...
    document_result = await cdp_session.send('DOM.getDocument', {
      'depth': -1,
      'pierce': True  # This 'true' really pierces through closed shadowRoots but not through iframes security
    })
    # print(f"document_result=\n {json.dumps(document_result, indent=2)}")
    await cdp_session.detach()  # You don't need the CDPSession anymore ...

    # Get closed ShadowRoot from the document
    xpaths = []
    # Initial call: document_result['root'] is the document node (e.g. #document).
    # Its XPath is effectively empty string, children will build from "/"
    self._get_closed_shadow_roots_from_node(document_result['root'], "", xpaths)
    if xpaths:
      for xpath_item in xpaths:
        logger.debug(f"Found closed ShadowRoot using CDP at XPath: {xpath_item} in frame {frame}")
    else:
      logger.trace(f"Found 0 closed ShadowRoot using CDP in frame {frame}")

    return xpaths

  async def _find_shadow_root_in_frames_recursively(self, frame: Frame, xpath_of_host: str) -> Tuple[JSHandle | None, Frame | None]:
    # First we look for the host in the current frame ...
    css_of_host = self.xpath_to_css(xpath_of_host)
    host_locator = frame.locator(css_of_host)
    children = []  # Initialize to ensure it's defined for disposal logic later
    if await host_locator.count() > 0:  # Check if the host element exists in the current frame
      # You don't want the host, you need one of its direct children ...
      element_locator_for_host_children = frame.locator(css_of_host + " > *")
      # It seems the returned handles are usable ...
      children = await element_locator_for_host_children.element_handles()
      # Proceed to child frames if handles can't be obtained
      if children:
        logger.trace(f"  (Frame: {frame}) Found [{len(children)}] children for host xpath = [{xpath_of_host}] ... ")
        for child_handle in children:
          if logger.isEnabledFor(logging.TRACE):
            logger.trace(await self.get_js_handle_description(child_handle, f"    Child Node"))
          # I'm trying to get the closed ShadowRoot by using element => element.getRootNode()
          shadow_root_candidate = await child_handle.evaluate_handle("element => element.getRootNode()")
          node_type_js_handle = await shadow_root_candidate.get_property('nodeType')
          node_type = await node_type_js_handle.json_value()
          await node_type_js_handle.dispose()  # Dispose the nodeType handle
          if node_type == 11:  # ShadowRoot nodes are #document-fragment
            if logger.isEnabledFor(logging.TRACE):
              logger.trace(await self.get_js_handle_description(shadow_root_candidate, f"    ShadowRoot"))
            # Found the shadow root. Dispose all child_handles obtained in this frame.
            for child in children:
              await child.dispose()
            return shadow_root_candidate, frame
          else:
            # Not the shadow root, dispose this candidate
            await shadow_root_candidate.dispose()

    # If this point is reached, no shadow root was returned from the current frame's direct children.
    # Dispose all child_handles obtained in this frame (if any).
    for child_handle_to_dispose in children:
      await child_handle_to_dispose.dispose()

    for child_frame in frame.child_frames:
      if child_frame.url == 'about:blank':  # Skip blank iframes
        continue

      found_in_descendant = await self._find_shadow_root_in_frames_recursively(child_frame, xpath_of_host)
      if found_in_descendant:
        return found_in_descendant

    return None, None

  async def _get_closed_shadow_root_descriptor_list(self, frame: Frame, cdp_session: CDPSession, frames_descriptor_dict: FramesDescriptorDict):
    # There is no API bridge between CDP API and Playwright ElementHandle. I mean, I can't use DOM.ResolveNode returned RemoteObjectId
    # to get a JSHandle/ElementHandle. I need to locate all the children of the host using a piercing CSS locator (TODO: Xpath doesn't seem to work)
    # and from that children a little bit of trickery to get the ElementHandle to the parent closed shadow root ...
    frames_descriptor_dict[frame] = []
    for xpath in await self._get_xpaths_to_closed_shadow_roots_from_frame(cdp_session, frame):
      logger.trace(f"Attempting to find ShadowRoot for host XPath: [{xpath}] (identified in frame: {frame.url})")
      # Start search in the frame whose associated CDPSession found the shadow root and computed its XPath ...
      shadow_root_handle, frame_container = await self._find_shadow_root_in_frames_recursively(frame, xpath)
      if shadow_root_handle:
        assert frame_container is not None, "If shadow_root_handle is found, frame_container must also be a valid Frame."
        closed_shadow_root_descriptor = ClosedShadowRootDescriptor(xpath, shadow_root_handle)
        logger.info(f"  Successfully found ShadowRoot for host XPath: [{xpath}] in frame: {frame_container} ...")
        closed_shadow_root_descriptor_list = frames_descriptor_dict.get(frame_container)
        if not closed_shadow_root_descriptor_list:
          closed_shadow_root_descriptor_list = []
          frames_descriptor_dict[frame_container] = closed_shadow_root_descriptor_list
        closed_shadow_root_descriptor_list.append(closed_shadow_root_descriptor)
      else:
        error_msg = (f"Could not find closed shadow root handle for host XPath: [{xpath}] "
                     f"(originally identified in frame {frame.url}) after checking this frame and all its descendant frames.")
        logger.error(error_msg)
        raise RuntimeError(error_msg)

  @staticmethod
  async def get_js_handle_description(child_handle: JSHandle, description: str) -> str:
    node_name = await child_handle.get_property('nodeName')
    node_type = await child_handle.get_property('nodeType')
    description = f"{description}: Name='{await node_name.json_value()}', Type='{await node_type.json_value()}'"
    await node_name.dispose()
    await node_type.dispose()

    return description

  @staticmethod
  def is_matching_iframe(frame: 'Frame', element: DOMElementNode | None) -> bool:
    """
    Tries to match a DOMElementNode with tag_name == "iframe" with a Frame Playwright/Patchright object.
    If you pass a None obeject is because you are looking for the main frame.
    """
    if not element:
      return frame.page.main_frame == frame

    if element.tag_name != "iframe":
      raise ValueError(f'Not an iframe but a {element.tag_name} element has been provided to check ...')

    # Try matching by name/id first
    if frame.name == element.attributes.get('name') or frame.name == element.attributes.get('id'):
      return True

    # Try URL similarity (path and query) because they don't always match completely ...
    element_src_attr = element.attributes.get('src')
    if frame.url and element_src_attr:
      try:
        parsed_frame_url = urlparse(frame.url)
        parsed_element_url = urlparse(element_src_attr)

        if (parsed_frame_url.path == parsed_element_url.path and
            parsed_frame_url.query == parsed_element_url.query):
          return True
      except ValueError:
        pass  # Malformed URLs, treat as no match for URL part.

    return False

  @staticmethod
  def _parse_params_string(params_str: Optional[str]) -> Dict[str, str]:
    params_dict = {}
    if not params_str:
      return params_dict
    for item in params_str.split(';'):
      if not item:
        continue
      if '=' in item:
        key, value = item.split('=', 1)
        params_dict[key] = value
      else:
        # Handle param without value, e.g. "flagparam"
        params_dict[item] = ""
    return params_dict

  @staticmethod
  def _is_matching_iframe_stricter(frame: 'Frame', candidate_iframes: List[DOMElementNode]) -> DOMElementNode | None:
    if not candidate_iframes:
      return None

    frame_url_parsed = urlparse(frame.url)

    scheme_netloc_matches = []
    for iframe_node in candidate_iframes:
      src_attr = iframe_node.attributes.get('src')
      if not src_attr:
        continue

      src_parsed = urlparse(src_attr)
      if src_parsed.scheme == frame_url_parsed.scheme and \
         src_parsed.netloc == frame_url_parsed.netloc:
        scheme_netloc_matches.append(iframe_node)

    if not scheme_netloc_matches:
      return None
    if len(scheme_netloc_matches) == 1:
      return scheme_netloc_matches[0]

    frame_params_dict = DomUtils._parse_params_string(frame_url_parsed.params)
    best_match_iframe = None
    max_matching_params_count = -1

    for iframe_node in scheme_netloc_matches:
      src_attr = iframe_node.attributes.get('src')
      src_parsed = urlparse(src_attr)
      src_params_dict = DomUtils._parse_params_string(src_parsed.params)
      current_matching_params_count = sum(1 for k, v in frame_params_dict.items() if k in src_params_dict and src_params_dict[k] == v)
      if current_matching_params_count > max_matching_params_count:
        max_matching_params_count = current_matching_params_count
        best_match_iframe = iframe_node

    return best_match_iframe

  @staticmethod
  def copy_children(donor: DOMElementNode, new_parent: DOMElementNode):
    for child in donor.children:
      child.parent = new_parent
      new_parent.children.append(child)

  @staticmethod
  async def find_parent_iframe(element: DOMElementNode) -> DOMElementNode | None:
    current_element: DOMElementNode | None = element.parent
    while current_element:
      if current_element.tag_name == "iframe":
        return current_element
      current_element = current_element.parent
    return None

  @staticmethod
  async def get_insertion_point_for_body(final_dom_element_node: Optional[DOMElementNode], frame : Frame) -> DOMElementNode|None:
    if not final_dom_element_node:
      return None

    iframe_elements: list[DOMElementNode] = \
      await DomUtils.traverse_and_filter(final_dom_element_node,
                                         lambda node: asyncio.sleep(0, result=(node.tag_name == "iframe")))

    # TODO: The real problem is how to match the iframe_elements with the corresponding Frame object.
    #       This is ugly as hell, but I can't think of anything better for the moment ...
    if len(iframe_elements) > 1:
      iframe_elements = [iframe for iframe in iframe_elements if DomUtils.is_matching_iframe(frame, iframe)]
      if len(iframe_elements) > 1:
        _stricter_candidate = DomUtils._is_matching_iframe_stricter(frame, iframe_elements)
        iframe_elements = [_stricter_candidate] if _stricter_candidate else iframe_elements

    # It can happen that the Frame exists but the visual element is out of the viewportExpansion
    if len(iframe_elements) == 0:
      logger.warning(f"Not found DOMElementNode to attach body for frame [{frame}] ...")
      return None

    assert len(iframe_elements) == 1, f"There should be one and only one frame matching the body and there are {len(iframe_elements)} ..."
    return iframe_elements[0]

  async def build_frames_descriptor_dict(self, page: Page) -> FramesDescriptorDict:
    frames_descriptor_dict = {}
    for frame, cdp_session in await self._get_target_frames_and_cdp_sessions(page):
      await self._get_closed_shadow_root_descriptor_list(frame, cdp_session, frames_descriptor_dict)

    return frames_descriptor_dict
