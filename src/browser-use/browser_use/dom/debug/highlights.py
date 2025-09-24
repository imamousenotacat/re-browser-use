# 100% vibe coded. NOT ANYMORE. LONG LIVE TO VIBE CODE CLEANERS ;-P !!!!

import asyncio
import json
import logging
import traceback

from dataclasses import dataclass
from typing import Optional

from browser_use.dom.service import DomService
from browser_use.dom.views import DOMSelectorMap, EnhancedDOMTreeNode, NodeType
from browser_use.browser.session import CDPSession

logger = logging.getLogger(__name__)

FrameId = str
@dataclass
class CloseShadowRoot:
	object_id: str                                          # returned by DOM.resolveNode
	interactive_elements: Optional[DOMSelectorMap] = None   # interactive elements owned by the closed shadow root


@dataclass
class FrameDescriptor:
	frame_info: dict                                        # frame_info filled in the method 'get_all_frames'
	closed_shadow_roots: list[CloseShadowRoot]              # list of closed shadow roots present in the frame
	interactive_elements: Optional[DOMSelectorMap] = None   # interactive elements owned by the iframe

FramesDescriptorDict = dict[FrameId, FrameDescriptor]


def convert_dom_selector_map_to_highlight_format(selector_map: DOMSelectorMap, is_main_page: bool) -> list[dict]:
	"""Convert DOMSelectorMap to the format expected by the highlighting script."""
	elements = []

	for interactive_index, node in selector_map.items():
		bbox = None
		if is_main_page:
			# For elements in the main page, `absolute_position` is correct as it's relative to the main viewport.
			if node.absolute_position:
				rect = node.absolute_position
				bbox = {'x': rect.x, 'y': rect.y, 'width': rect.width, 'height': rect.height}
		else:
			# For elements inside an iframe get bounding box using local snapshot bounds (relative to frame viewport)
			if node.snapshot_node and node.snapshot_node.bounds:
				rect = node.snapshot_node.bounds
				bbox = {'x': rect.x, 'y': rect.y, 'width': rect.width, 'height': rect.height}

		# Only include elements with valid bounding boxes
		if bbox and bbox.get('width', 0) > 0 and bbox.get('height', 0) > 0:
			element = {
				'x': bbox['x'],
				'y': bbox['y'],
				'width': bbox['width'],
				'height': bbox['height'],
				'interactive_index': interactive_index,
				'element_name': node.node_name,
				'is_clickable': node.snapshot_node.is_clickable if node.snapshot_node else True,
				'is_scrollable': getattr(node, 'is_scrollable', False),
				'attributes': node.attributes or {},
				'frame_id': getattr(node, 'frame_id', None),
				'node_id': node.node_id,
				'backend_node_id': node.backend_node_id,
				'uuid': node.uuid,
				'text_content': node.get_all_children_text()[:50]
				if hasattr(node, 'get_all_children_text')
				else node.node_value[:50],
				'reasoning': getattr(node, "reasoning", {}),
			}

			elements.append(element)
		else:
			# Skip elements without valid bounding boxes for now
			# Could add fallback positioning here if needed
			pass

	return elements


async def remove_highlighting_script(dom_service: DomService, frames_descriptor_dict: FramesDescriptorDict | None = None) -> None:
	"""Remove all browser-use highlighting elements from all frames."""
	try:
		logger.debug('🧹 Removing browser-use highlighting elements from all frames ...')
		if not frames_descriptor_dict:
			frames_descriptor_dict = await build_frames_descriptor_dict(dom_service)

		# Removing the IIFE (Immediately Invoked Function Expression) part "(function(){...})();" and adding a needed function name ...
		removal_js_func = (
			f"function removeHighlights() {{ {HIGHLIGHTING_REMOVAL_JS[HIGHLIGHTING_REMOVAL_JS.find('{') + 1:HIGHLIGHTING_REMOVAL_JS.rfind('}')]} }}"
		)

		for frame_id, frame_descriptor in frames_descriptor_dict.items():
			try:
				frame_target_id = frame_descriptor.frame_info.get('frameTargetId')
				cdp_session_for_frame = await dom_service.browser_session.get_or_create_cdp_session(target_id=frame_target_id, focus=False)
				# In the iframe the function can be called using  Runtime.evaluate ...
				await cdp_session_for_frame.cdp_client.send.Runtime.evaluate(
					params={'expression': HIGHLIGHTING_REMOVAL_JS, 'returnByValue': True}, session_id=cdp_session_for_frame.session_id)
				# In the closed_shadow_roots we need to resort to callFunctionOn ...
				for closed_shadow_root in frame_descriptor.closed_shadow_roots:
					await cdp_session_for_frame.cdp_client.send.Runtime.callFunctionOn(
						params={'functionDeclaration': removal_js_func, 'objectId': closed_shadow_root.object_id, 'awaitPromise': False, 'returnByValue': True},
						session_id=cdp_session_for_frame.session_id)

				logger.debug(f"Highlight elements removed for frame {frame_id}...")
			except Exception as e:
				logger.warning(f"Failed to clean frame {frame_id}: {e}")

	except Exception as e:
		logger.exception(f'Error removing highlighting elements: {e}', exc_info=True)


# I hate having this polluting the logic of the functions ...
HIGHLIGHTING_REMOVAL_JS = """
(function() {
	// It seems that removing the container is not enough ...
	const DATA_HIGHLIGHTNING_ATTRIBUTE = 'data-browser-use-highlight';
	const initialRootNode = (this === window) ? window.document : this;

	// Removing elements containing this attribute which is set for the container, the highlights, the tooltips and the labels. 
	const highlights = initialRootNode.querySelectorAll(`[${DATA_HIGHLIGHTNING_ATTRIBUTE}]`);
	console.log('Removing', highlights.length, `elements with the attribute [${DATA_HIGHLIGHTNING_ATTRIBUTE}] ...`);
	highlights.forEach(el => el.remove());

	// Remove the container, just in case in fact this shouldn't be necessary ...
	const highlightContainers = initialRootNode.querySelectorAll('[id^="browser-use-debug-highlights-"]');
	if (highlightContainers.length > 0) {
		console.log('Removing', highlightContainers.length, 'highlightContainers ...');
		highlightContainers.forEach(el => el.remove());
	}

	// Remove scroll/resize listeners and cleanup functions
	if (window._browserUseThrottledUpdate) {
		console.log(`Removing 'scroll' and 'resize' window listeners ...`);
		window.removeEventListener('scroll', window._browserUseThrottledUpdate, true);
		window.removeEventListener('resize', window._browserUseThrottledUpdate);
		delete window._browserUseThrottledUpdate;
	}
	if (window._browserUseHighlightUpdaters) {
		// This also serves as a flag to stop any pending updates
		console.log(`Removing array of 'updatePosition' functions ...`);
		delete window._browserUseHighlightUpdaters;
	}
	
	return { removed: highlights.length };
})();
"""

async def inject_highlighting_script(dom_service: DomService, interactive_elements: DOMSelectorMap) -> None:
	"""Inject JavaScript to highlight interactive elements with detailed hover tooltips that work around CSP restrictions."""
	# Quick and dirty solution to filter already present highlighting elements (if any) ...
	interactive_elements= filter_highlighted_elements(interactive_elements)

	if not interactive_elements:
		logger.debug('⚠️ No interactive elements to highlight')
		return

	try:
		logger.debug(f'Creating CSP-safe highlighting for {len(interactive_elements)} elements')
		# Get all frames that have an associated CDP session ...
		all_frames_with_cdp_session = await _get_all_frames_with_cdp_session(dom_service)
		# This is the target id corresponding to the main page ...
		main_page_target_id = _get_main_page_target_id(all_frames_with_cdp_session)

		# Getting for each frame the corresponding list of ShadowRootObjectId ...
		frames_descriptor_dict: FramesDescriptorDict = await build_frames_descriptor_dict(dom_service, interactive_elements, all_frames_with_cdp_session)

		# ALWAYS remove any existing highlights first to prevent double-highlighting
		await remove_highlighting_script(dom_service, frames_descriptor_dict)
		await asyncio.sleep(0.05) # Add a small delay to ensure removal completes

		# Set unique IDs on all elements first, across all frames. This is to be able to get a handle to the real highlighted DOM node in
		# order to create an 'updatePosition' function. I tried xpath too but I think that this method is clearer and more direct ...
		interactive_elements = await _set_unique_ids_on_elements(dom_service, interactive_elements)
		if not interactive_elements:
			return

		# Now, inject a dedicated highlighting script into each target as I did in <= 0.5.11 versions ...
		for frame_id, frame_descriptor in frames_descriptor_dict.items():
			try:
				# Get a CDP session for the specific frame ... 'frameTargetId' is the target that can access a frame
				frame_target_id = frame_descriptor.frame_info.get('frameTargetId')
				cdp_session_for_frame = await dom_service.browser_session.get_or_create_cdp_session(target_id=frame_target_id, focus=False)

				if frame_descriptor.interactive_elements:
					converted_elements = convert_dom_selector_map_to_highlight_format(frame_descriptor.interactive_elements, frame_id == main_page_target_id )
					if converted_elements:
						script = make_script(converted_elements)
						# Get document.body objectId for the frame
						evaluate_result = await cdp_session_for_frame.cdp_client.send.Runtime.evaluate(
								params={'expression': 'document.body', 'returnByValue': False}, session_id=cdp_session_for_frame.session_id)
						window_object_id = evaluate_result['result']['objectId'] # type: ignore

						# I could use 'evaluate' here as for 'removal_js_func', but I want to avoid the same manoeuvre ...
						await cdp_session_for_frame.cdp_client.send.Runtime.callFunctionOn(
							params={
							'functionDeclaration': script,
							'objectId': window_object_id,
							# 'arguments': call_arguments,
							'awaitPromise': False,
							'returnByValue': True,
							},
							session_id=cdp_session_for_frame.session_id,
						)

				# We execute the script in the shadow roots corresponding to the iframe
				for closed_shadow_root in frame_descriptor.closed_shadow_roots:
					if closed_shadow_root.interactive_elements:
						converted_elements = convert_dom_selector_map_to_highlight_format(closed_shadow_root.interactive_elements,
																			frame_id == main_page_target_id)
					if converted_elements:
							script = make_script(converted_elements)
							await cdp_session_for_frame.cdp_client.send.Runtime.callFunctionOn(
								params={
								'functionDeclaration': script,
								'objectId': closed_shadow_root.object_id,
								# 'arguments': [argument],
								'awaitPromise': False,
								'returnByValue': True,
								},
								session_id=cdp_session_for_frame.session_id,
							)

			except Exception as e:
				logger.warning(f"Failed to inject highlights into frame {frame_id}: {e}")
				traceback.print_exc()

    # Set the focus in the main page again to avoid problems with disappearing iframes ...
		await dom_service.browser_session.get_or_create_cdp_session(main_page_target_id)

		logger.debug('Finished injecting all highlighting scripts.')

	except Exception as e:
		logger.debug(f'❌ Error injecting enhanced highlighting script: {e}')
		traceback.print_exc()


def _get_main_page_target_id(all_frames_with_cdp_session):
  # Getting the main page target id ...
  main_frames = [f for f in all_frames_with_cdp_session.values() if not f.get('parentFrameId')]
  if len(main_frames) != 1: raise ValueError(f"There should be just one main iframe. There are [{len(main_frames)}]...")

  return main_frames[0]['id']


def filter_highlighted_elements(interactive_elements: DOMSelectorMap) -> DOMSelectorMap:
	# In reality all these 'data-browser-use-highlight' are remanents in the DOM of previous executions that should not be there
	# because now they are ignored when constructing the DOM tree in get_dom_tree ...
	filtered_items = [node for node in interactive_elements.values() if 'data-browser-use-highlight' not in node.attributes]
	logger.debug(f"Filtered out [{len(interactive_elements) - len(filtered_items)}] 'data-browser-use-highlight' elements that were in DOMSelectorMap ...")
	return {i+1: node for i, node in enumerate(filtered_items)}

#  This humongous horror in the middle of a function was making me cry ...
def make_script(converted_elements):
	return f"""
function(...args) {{
	const DATA_HIGHLIGHTNING_ATTRIBUTE = 'data-browser-use-highlight';
	// Interactive elements data with reasoning, specific to this frame
	const interactiveElements = {json.dumps(converted_elements)};
	// Starting search point ...
	const initialRootNode = (this === window) ? window.document : this;
	
	// Use a unique ID for the container in this frame to avoid collisions.
	const containerId = 'browser-use-debug-highlights-' + (Math.random().toString(36).substring(2, 9));

	console.log(`=== BROWSER-USE HIGHLIGHTING (Frame: ${{window.location.href.substring(0, 50)}}) ===`);
	console.log('Highlighting', interactiveElements.length, 'interactive elements in this frame.');
	
	// Double-check: Remove any existing highlight container first to prevent duplicates. TODO: STUPIDITY THIS WON'T EVER HAPPEN
	const existingContainer = document.getElementById(containerId);
	if (existingContainer) {{
		console.log('⚠️ Found existing highlight container, removing it first');
		existingContainer.remove();
	}}
	
	// Also remove any stray highlight elements already contained in this initialRootNode ...
	const strayHighlights = initialRootNode.querySelectorAll(`[${{DATA_HIGHLIGHTNING_ATTRIBUTE}}]`);
	if (strayHighlights.length > 0) {{
		console.log('⚠️ Found', strayHighlights.length, 'stray highlight elements, removing them');
		strayHighlights.forEach(el => el.remove());
	}}
	
	// Use a high but reasonable z-index to be visible without covering important content
	// High enough for most content but not maximum to avoid blocking critical popups/modals
	const HIGHLIGHT_Z_INDEX = 2147483647; // Maximum z-index for CSS (2^31-1)
	
	// Create container for all highlights - use fixed positioning relative to this frame's viewport
	const container = document.createElement('div');
	container.id = containerId;
	container.setAttribute(DATA_HIGHLIGHTNING_ATTRIBUTE, 'container');
	const originalElements = [];
	
	container.style.cssText = `
		position: fixed;
		top: 0;
		left: 0;
		width: 100vw;
		height: 100vh;
		pointer-events: none;
		z-index: ${{HIGHLIGHT_Z_INDEX}};
		overflow: visible;
		margin: 0;
		padding: 0;
		border: none;
		outline: none;
		box-shadow: none;
		background: none;
		font-family: inherit;
	`;
	
	// Helper function to create text nodes safely (CSP-friendly)
	function createTextElement(tag, text, styles) {{
		const element = document.createElement(tag);
		element.textContent = text;
		if (styles) element.style.cssText = styles;
		return element;
	}}

	// Helper function to find an element by unique ID, searching through all frames and shadow roots.
	function findElementByUniqueId(uuid) {{
		const query = `[data-browser-use-id="${{uuid}}"]`;

		// Start with the contexts we received from CDP (closed shadow roots for this frame)
		const searchContexts = [];

		// Recursively collect all accessible frame documents and OPEN shadow roots within THIS frame's world
		function collectOpenContexts(node) {{
			try {{
				searchContexts.push(node);

				// Collect open shadow roots
				node.querySelectorAll('*').forEach(el => {{
					if (el.shadowRoot && el.shadowRoot.mode === 'open') {{
						searchContexts.push(el.shadowRoot);
					}}
				}});

				// Recurse into same-origin sub-frames
				for (let i = 0; i < win.frames.length; i++) {{
					collectOpenContexts(win.frames[i])
				}}
			}} catch (e) {{ /* Ignore cross-origin frames */ }}
		}}

		// Start search from initial root node ... 
		collectOpenContexts(initialRootNode);

		// De-duplicate contexts to avoid searching the same place twice
		const uniqueContexts = [...new Set(searchContexts)];

		for (const context of uniqueContexts) {{
			if (context && typeof context.querySelector === 'function') {{
				const element = context.querySelector(query);
				if (element) return element;
			}}
		}}
		return null;
	}}

	// Add enhanced highlights with detailed tooltips
	interactiveElements.forEach((element, index) => {{
		// --- Logic to keep highlight attached to element on scroll/resize ---
		try {{
			// Find the original DOM element using its unique ID, searching across all frames and shadow roots
			const originalElement = findElementByUniqueId(element.uuid);

			if (!originalElement) {{
				console.warn('Could not find original element=', element,' for highlight update. UUID:', element.uuid,' in this context. Ignoring it ...');
				return;
			}}

			const highlight = document.createElement('div');
			highlight.setAttribute(DATA_HIGHLIGHTNING_ATTRIBUTE, 'element');
			highlight.setAttribute('data-element-id', element.interactive_index);
			highlight.style.cssText = `
				position: absolute;
				left: ${{element.x}}px;
				top: ${{element.y}}px;
				width: ${{element.width}}px;
				height: ${{element.height}}px;
				outline: 2px solid #4a90e2;
				outline-offset: -2px;
				background: transparent;
				pointer-events: none; /* Let clicks pass through to the underlying element */
				box-sizing: content-box;
				transition: outline 0.2s ease;
				margin: 0;
				padding: 0;
				border: none;
			`;
			
			// Enhanced label with interactive index
			const label = createTextElement('div', element.interactive_index, `
				position: absolute;
				top: -20px;
				left: 0;
				background-color: #4a90e2;
				color: white;
				padding: 2px 6px;
				font-size: 11px;
				font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
				font-weight: bold;
				border-radius: 3px;
				white-space: nowrap;
				z-index: ${{HIGHLIGHT_Z_INDEX + 1}};
				box-shadow: 0 2px 4px rgba(0,0,0,0.3);
				border: none;
				outline: none;
				margin: 0;
				line-height: 1.2;
				pointer-events: auto; /* This is crucial for the label to be hoverable */
				cursor: pointer; /* Indicate that the label is interactive */
			`);
			label.setAttribute(DATA_HIGHLIGHTNING_ATTRIBUTE, 'label');
			
			// Enhanced tooltip with detailed reasoning (CSP-safe)
			const tooltip = document.createElement('div');
			tooltip.setAttribute(DATA_HIGHLIGHTNING_ATTRIBUTE, 'tooltip');
			tooltip.style.cssText = `
				position: absolute;
				top: -160px;
				left: 50%;
				transform: translateX(-50%);
				background-color: rgba(0, 0, 0, 0.95);
				color: white;
				padding: 12px 16px;
				font-size: 12px;
				font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
				border-radius: 8px;
				white-space: nowrap;
				z-index: ${{HIGHLIGHT_Z_INDEX + 2}};
				opacity: 0;
				visibility: hidden;
				transition: all 0.3s ease;
				box-shadow: 0 6px 20px rgba(0,0,0,0.5);
				border: 1px solid #666;
				max-width: 400px;
				white-space: normal;
				line-height: 1.4;
				min-width: 200px;
				margin: 0;
			`;
			
			// Build detailed tooltip content with reasoning (CSP-safe DOM creation)
			const reasoning = element.reasoning || {{}};
			const confidence = reasoning.confidence || 'UNKNOWN';
			const primaryReason = reasoning.primary_reason || 'unknown';
			const reasons = reasoning.reasons || [];
			const elementType = reasoning.element_type || element.element_name || 'UNKNOWN';
			
			// Determine confidence color and styling
			let confidenceColor = '#4a90e2';
			let confidenceIcon = '🔍';
			let outlineColor = '#4a90e2';
			let shadowColor = '#4a90e2';
			
			if (confidence === 'HIGH') {{
				confidenceColor = '#28a745';
				confidenceIcon = '✅';
				outlineColor = '#28a745';
				shadowColor = '#28a745';
			}} else if (confidence === 'MEDIUM') {{
				confidenceColor = '#ffc107';
				confidenceIcon = '⚠️';
				outlineColor = '#ffc107';
				shadowColor = '#ffc107';
			}} else {{
				confidenceColor = '#fd7e14';
				confidenceIcon = '❓';
				outlineColor = '#fd7e14';
				shadowColor = '#fd7e14';
			}}
			
			// Create tooltip header
			const header = createTextElement('div', `${{confidenceIcon}} [${{element.interactive_index}}] ${{elementType.toUpperCase()}}`, `
				color: ${{confidenceColor}};
				font-weight: bold;
				font-size: 13px;
				margin-bottom: 8px;
				border-bottom: 1px solid #666;
				padding-bottom: 4px;
			`);
			
			// Create confidence indicator
			const confidenceDiv = createTextElement('div', `${{confidence}} CONFIDENCE`, `
				color: ${{confidenceColor}};
				font-size: 11px;
				font-weight: bold;
				margin-bottom: 8px;
			`);
			
			// Create primary reason
			const primaryReasonDiv = createTextElement('div', `Primary: ${{primaryReason.replace('_', ' ').toUpperCase()}}`, `
				color: #fff;
				font-size: 11px;
				margin-bottom: 6px;
				font-weight: bold;
			`);
			
			// Create reasons list
			const reasonsContainer = document.createElement('div');
			reasonsContainer.style.cssText = `
				font-size: 10px;
				color: #ccc;
				margin-top: 4px;
			`;
			
			if (reasons.length > 0) {{
				const reasonsTitle = createTextElement('div', 'Evidence:', `
					color: #fff;
					font-size: 10px;
					margin-bottom: 4px;
					font-weight: bold;
				`);
				reasonsContainer.appendChild(reasonsTitle);
				
				reasons.slice(0, 4).forEach(reason => {{
					const reasonDiv = createTextElement('div', `• ${{reason}}`, `
						color: #ccc;
						font-size: 10px;
						margin-bottom: 2px;
						padding-left: 4px;
					`);
					reasonsContainer.appendChild(reasonDiv);
				}});
				
				if (reasons.length > 4) {{
					const moreDiv = createTextElement('div', `... and ${{reasons.length - 4}} more`, `
						color: #999;
						font-size: 9px;
						font-style: italic;
						margin-top: 2px;
					`);
					reasonsContainer.appendChild(moreDiv);
				}}
			}} else {{
				const noReasonsDiv = createTextElement('div', 'No specific evidence found', `
					color: #999;
					font-size: 10px;
					font-style: italic;
				`);
				reasonsContainer.appendChild(noReasonsDiv);
			}}
			
			// Add bounding box info
			const boundsDiv = createTextElement('div', `Position: (${{Math.round(element.x)}}, ${{Math.round(element.y)}}) Size: ${{Math.round(element.width)}}×${{Math.round(element.height)}}`, `
				color: #888;
				font-size: 9px;
				margin-top: 8px;
				border-top: 1px solid #444;
				padding-top: 4px;
			`);
			
			// Assemble tooltip
			tooltip.appendChild(header);
			tooltip.appendChild(confidenceDiv);
			tooltip.appendChild(primaryReasonDiv);
			tooltip.appendChild(reasonsContainer);
			tooltip.appendChild(boundsDiv);
			
			// Set highlight colors based on confidence (outline only)
			highlight.style.outline = `2px solid ${{outlineColor}}`;
			label.style.backgroundColor = outlineColor;

			// Add subtle hover effects (outline only, no background) to the LABEL, so the highlight itself doesn't block clicks.
			label.addEventListener('mouseenter', () => {{
				highlight.style.outline = '3px solid #ff6b6b';
				highlight.style.outlineOffset = '-1px';
				tooltip.style.opacity = '1';
				tooltip.style.visibility = 'visible';
				label.style.backgroundColor = '#ff6b6b';
				label.style.transform = 'scale(1.1) translateY(-1px)';
			}});
			
			label.addEventListener('mouseleave', () => {{
				highlight.style.outline = `2px solid ${{outlineColor}}`;
				highlight.style.outlineOffset = '-2px';
				tooltip.style.opacity = '0';
				tooltip.style.visibility = 'hidden';
				label.style.backgroundColor = outlineColor;
				label.style.transform = 'scale(1)';
			}});
			
			highlight.appendChild(tooltip);
			highlight.appendChild(label);
			container.appendChild(highlight);

			// console.log('Found original DOM node for element =', originalElement, ` for UUID=[${{element.uuid}}] ...`);
			originalElements.push(originalElement);
			const updatePosition = () => {{
				// Since this script runs inside the correct frame and the highlight container
				// is position:fixed, getBoundingClientRect() gives the correct coordinates
				// relative to the frame's viewport. No cross-frame offset calculation is needed.
				const rect = originalElement.getBoundingClientRect();
				if (rect.width === 0 || rect.height === 0) {{
					highlight.style.display = 'none';
				}} else {{
					highlight.style.display = 'block';
					highlight.style.left = `${{rect.left}}px`;
					highlight.style.top = `${{rect.top}}px`;
					highlight.style.width = `${{rect.width}}px`;
					highlight.style.height = `${{rect.height}}px`;
				}}
			}};
			// Store the updater function to be called on scroll/resize
			(window._browserUseHighlightUpdaters = window._browserUseHighlightUpdaters || []).push(updatePosition);
		}} catch (e) {{
			console.warn('Could not find or create updater for element with uuid:', element.uuid, e);
		}}

	}});
	
	// Add container to document. Adding the child to document.body doesn't work when that document.body is the host of a ShadowRoot
	const rootNode = originalElements?.[0]?.getRootNode();
	if (rootNode?.host === document.body) {{
		rootNode.appendChild(container);
	}} else {{
		document.body.appendChild(container);
	}}

	// --- Add scroll and resize listeners to run all position updaters ---
	const throttleFunction = (func, delay) => {{
		let lastCall = 0;
		return (...args) => {{
			const now = performance.now();
			if (now - lastCall < delay) return;
			lastCall = now;
			return func(...args);
		}};
	}};

	const runAllUpdaters = () => {{
		if (window._browserUseHighlightUpdaters) {{
			window._browserUseHighlightUpdaters.forEach(fn => fn());
		}}
	}};

	// Store throttled function on window to allow for proper removal
	window._browserUseThrottledUpdate = throttleFunction(runAllUpdaters, 16); // ~60fps

	window.addEventListener('scroll', window._browserUseThrottledUpdate, true);
	window.addEventListener('resize', window._browserUseThrottledUpdate);

	console.log('Highlighting complete for this frame.');
}}
"""


async def _set_unique_ids_on_elements(dom_service: DomService, interactive_elements: DOMSelectorMap) -> DOMSelectorMap:
	logger.debug(f'Setting unique IDs for {len(interactive_elements)} elements across all frames.')

	successful_elements = {}
	for index, node in interactive_elements.items():
		try:
			# Get the correct CDP session for the node, which may be in an iframe.
			node_cdp_session = await _cdp_client_for_node(dom_service, node)
			# If you have the proper nodeId, this will cross closed shadow roots ...
			await node_cdp_session.cdp_client.send.DOM.setAttributeValue(
				params={'nodeId': node.node_id, 'name': 'data-browser-use-id', 'value': node.uuid},
				session_id=node_cdp_session.session_id,
			)
			# TODO: I'm pretty sure about this filtering but not completely ...
			successful_elements[index] = node
		except Exception as e:
			logger.warning(f'Could not set unique ID for element {index} (uuid: {node.uuid}): {e}')

	return successful_elements

# This is a pruned version of the BrowserSession.cdp_client_for_node method which I think doesn't work correctly for iframes.
# It incorrectly uses node.frame_id to determine the CDP session for an <iframe> element. An <iframe> element itself exists in the parent document, so commands # must be sent to the parent's session, which is correctly identified by node.target_id. The current logic sends the command to the child frame's session, 
# causing the Cannot edit pseudo elements error when the nodeId is misinterpreted.
async def _cdp_client_for_node(dom_service: DomService, node: EnhancedDOMTreeNode) -> CDPSession:
	"""Get CDP client for a specific DOM node based on its frame."""
	if node.target_id:
		try:
			cdp_session = await dom_service.browser_session.get_or_create_cdp_session(target_id=node.target_id, focus=False)
			result = await cdp_session.cdp_client.send.DOM.resolveNode(
				params={'backendNodeId': node.backend_node_id},
				session_id=cdp_session.session_id,
			)
			object_id = result.get('object', {}).get('objectId')
			if not object_id:
				raise ValueError(
					f'Could not find #{node.element_index} backendNodeId={node.backend_node_id} in target_id={cdp_session.target_id}'
				)
			# MOU14: I THINK THERE IS A MISSING 'return cdp_session' HERE. I ADD IT BELOW ...
			return cdp_session
		except Exception as e:
			dom_service.browser_session.logger.debug(f'Failed to get CDP client for target {node.target_id}: {e}, using main session')

	return await dom_service.browser_session.get_or_create_cdp_session()


async def build_frames_descriptor_dict(dom_service: DomService,
									   interactive_elements: DOMSelectorMap = {},
									   all_frames_with_cdp_session: dict[str, dict] | None = None) -> FramesDescriptorDict:
	# Getting here a dictionary of frames with their corresponding closed shadow roots ...
	frames_descriptor_dict: FramesDescriptorDict = {}
	if not all_frames_with_cdp_session:
		all_frames_with_cdp_session = await _get_all_frames_with_cdp_session(dom_service)

	# Initialize the dictionary
	for frame_id, frame_info in all_frames_with_cdp_session.items():
		frames_descriptor_dict[frame_id] = FrameDescriptor(frame_info=frame_info, closed_shadow_roots=[], interactive_elements={})
	# A map to avoid re-resolving the same closed shadow root
	resolved_shadow_roots: dict[str, CloseShadowRoot] = {} # key is shadow root uuid

	for index, node in interactive_elements.items():
		owning_shadow_root = _get_owning_closed_shadow_root(node)

		if owning_shadow_root:
			# Element is inside a closed shadow root
			shadow_root_uuid = owning_shadow_root.uuid
			owning_frame_id = _get_owning_frame_id(owning_shadow_root, all_frames_with_cdp_session)
			if shadow_root_uuid not in resolved_shadow_roots:
				# First time seeing this shadow root, resolve its objectId
				cdp_session = await _cdp_client_for_node(dom_service, owning_shadow_root)
				resolved_node = await cdp_session.cdp_client.send.DOM.resolveNode(params={'nodeId': owning_shadow_root.node_id},
                                                                      session_id=cdp_session.session_id)
				object_id = resolved_node.get('object', {}).get('objectId')
				if not object_id: raise ValueError("Could not resolve objectId for shadow root")

				new_csr = CloseShadowRoot(object_id=object_id, interactive_elements={})
				resolved_shadow_roots[shadow_root_uuid] = new_csr
				frames_descriptor_dict[owning_frame_id].closed_shadow_roots.append(new_csr) # type: ignore

			# Add the element to the correct CloseShadowRoot's interactive_elements
			resolved_shadow_roots[shadow_root_uuid].interactive_elements[index] = node # type: ignore
		else:
			# Element is in a regular frame context
			owning_frame_id = _get_owning_frame_id(node, all_frames_with_cdp_session)
			frames_descriptor_dict[owning_frame_id].interactive_elements[index] = node # type: ignore

	return frames_descriptor_dict


async def _get_all_frames_with_cdp_session(dom_service: DomService) -> dict[str, dict]:
	# Using the general get_all_frames method ...
	all_frames, target_sessions = await dom_service.browser_session.get_all_frames()
	# ... but just returning the frames with associated session
	return { k: v for k, v in all_frames.items() if v.get("id") in target_sessions }


def _get_owning_closed_shadow_root(node: EnhancedDOMTreeNode) -> EnhancedDOMTreeNode | None:
	"""
	Traverse up the DOM hierarchy from the given node to find if it belongs to a closed shadow root.

	Args:
		node: The starting DOM node.

	Returns:
		The EnhancedDOMTreeNode representing the closed shadow root if found, otherwise None.
	"""
	current = node
	while current.parent_node:
		current = current.parent_node
		# A shadow root is represented as a DOCUMENT_FRAGMENT_NODE
		if current.node_type == NodeType.DOCUMENT_FRAGMENT_NODE and current.shadow_root_type == 'closed':
			return current
	
	return None


def _get_owning_frame_id(node: EnhancedDOMTreeNode, all_frames_with_cdp_session:dict[str, dict]) -> str | None:
	"""Traverse up the DOM tree to find the frame ID that owns this node."""
	current = node
	while current:
		if current.frame_id and (not all_frames_with_cdp_session or current.frame_id in all_frames_with_cdp_session):			
			return current.frame_id
		current = current.parent_node
	
	return None
