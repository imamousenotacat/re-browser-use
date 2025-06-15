# TEST TO VERIFY WE ARE OBTAINING THE SAME RESULTS FROM PATCHRIGHT WITH CLOSED SHADOW ROOTS
# AND WITH PLAYWRIGHT AND OPEN SHADOW ROOTS

# import os
# I prefer set DEBUG variables here ...
# os.environ['DEBUG'] = 'pw:browser,pw:api,pw.protocol' # pw:* seems to activate everything
#os.environ['PWDEBUG'] = '0'
# os.environ['DEBUG'] = 'pw:api'

import asyncio
from patchright.async_api import async_playwright, expect
# Corrected import
from patchright.async_api import Locator  # Import Locator type hint

# Explanation:
# This function attempts to recursively find the first input[type=checkbox]
# starting from the given 'locator'. It uses Playwright's API to inspect
# elements and traverse children. Playwright locators inherently handle
# shadow DOM piercing, so this explores the structure Playwright sees.
async def find_checkbox_recursive_python(locator: Locator, depth=0) -> Locator | None:
    indent = '  ' * depth
    # print(f"{indent}Entering function: locator=[{locator}]")
    try:
        count = await locator.count()
        # print(f"{indent}Count in locator=[{locator}]: count=[{count}]")
    except Exception as e:
        print(e)
        return None

    if count == 0:
        print(f"{indent}Locator resolved to no elements.") # Optional debug
        return None
    if count > 1:
        print(f"{indent}Locator resolved to multiple elements ({count}), using first.") # Optional debug
        pass # Use the first element matched by the locator

    el_class, el_id, el_type, element_info, tag_name = await get_element_info(locator)
    print(f"{indent}Checking: <{tag_name}{el_id}{el_class}{el_type}>")

    # Check if the current element is the checkbox
    if tag_name == 'INPUT' and element_info.get('type') == 'checkbox':
        print(f"{indent}>>> Found checkbox locator:", locator)
        return locator # Return the locator itself

    # Recursively check children - Playwright locators handle shadow DOM
    # Using locator('> *') gets direct children, including across shadow boundaries
    children_locator = locator.locator('> *') # THIS IS WORRISOME: Mañana ...
    children_count = await children_locator.count()
    print(f"{indent} Found {children_count} children for <{tag_name}{el_id}>") # Optional debug
    for i in range(0, children_count):
        child_locator = children_locator.nth(i)
        # el_class, el_id, el_type, element_info, tag_name = await get_element_info(child_locator)
        # print(f"{indent}Invoking recursion on: children_locator.nth({i}) = <{tag_name}{el_id}{el_class}{el_type}>")
        found = await find_checkbox_recursive_python(child_locator, depth + 1)
        if found:
            return found # Propagate the found locator up

    return None # Not found in this branch

async def get_element_info(locator):
    # Get element details using evaluate - more robust than multiple get_attribute calls
    element_info = await locator.first.evaluate("""
        element => ({
            tagName: element.tagName,
            id: element.id,
            className: element.className,
            type: element.getAttribute('type') || null
        })
    """, None)  # Pass None as arg
    tag_name = element_info.get('tagName', 'N/A').upper()
    el_id = f"#{element_info.get('id')}" if element_info.get('id') else ""
    el_class = f".{str(element_info.get('className', '')).replace(' ', '.')}" if element_info.get('className') else ""
    el_type = f"[type={element_info.get('type')}]" if element_info.get('type') else ""

    return el_class, el_id, el_type, element_info, tag_name

async def test_cloudflare():
    async with (async_playwright() as playwright):
        chromium = playwright.chromium
        browser = await chromium.launch(headless=False)
        context = await browser.new_context()
        # TODO:pvm14 TESTING IF JUST BY MAKING shadowRoot open WITH THE CALL await context.add_init_script MANUALLY PASSING THE TURNSTILE BREAKS.
        # YEAP, INDEED BREAKS WHICH I THINK IS GOOD NEWS BECAUSE IT MEANS THAT BrowserUse MAY BE BREAKING NOTHING BY ITSELF. WE WILL SEE ...
        # await context.add_init_script(
        #     """
        #     (function () {
        #             const originalAttachShadow = Element.prototype.attachShadow;
        #             Element.prototype.attachShadow = function attachShadow(options) {
        #                     return originalAttachShadow.call(this, { ...options, mode: "open" });
        #             };
        #     })();
        #     """
        # )

        page = await context.new_page()
        await page.goto("https://nopecha.com/demo/cloudflare")
        # This is what I get from playwright codegen https://nopecha.com/demo/cloudflare that obviously does not work because it changes for each interaction ...
        # locator = page.locator("iframe[src=\"https\\:\\/\\/challenges\\.cloudflare\\.com\\/cdn-cgi\\/challenge-platform\\/h\\/b\\/turnstile\\/if\\/ov2\\/av0\\/rcv\\/knz61\\/0x4AAAAAAAAjq6WYeRDKmebM\\/light\\/fbE\\/new\\/normal\\/auto\\/\"]").content_frame.locator("body")
        # This is the selector that Claude suggested => AND COMBINED WITH THE PROPER WAITING IS WORKING ...
        SELECTOR = "iframe[src^='https://challenges.cloudflare.com/cdn-cgi/challenge-platform']"
        await page.wait_for_load_state('load')
        await page.wait_for_timeout(10000)                # FUCK OFF WITHOUT THIS THE AUTOMATIC CLICK DOESN'T GET PERFORMED ???? OK we have to deal with the fact this is a PATCHED playwright ...

        frame_locator = page.frame_locator(SELECTOR)      # Create frame locator
        # locator = frame_locator.locator("body")           # Create body locator
        # Validate frame existence
        # await expect(frame_locator.owner).to_be_attached(timeout=1000)  # Checks iframe exists in DOM
        # Validate frame content
        # await expect(locator).to_have_count(1,timeout=1000) # Throws if not found THIS DOESN'T WORK FOR closed ShadowRoots
        count = await frame_locator.owner.count() # Count here is working ...
        assert count == 1
        # Option 0: After 9 days fighting with this and after patching myself a little bit more patchtight this is the corrrect way
        children = frame_locator.locator("*")
        count = await children.count()
        print(f"ARMAS-PAL-PUEBLO 0: Found {count} children ...")
        # Option 1: Using element_handles()
        children = await frame_locator.locator('> *').element_handles()
        count = len(children)
        print(f"ARMAS-PAL-PUEBLO 1: Found {count} children HEAD and BODY the two elements of the Document in the iframe ...")
        # Option 2: Using all() with a CSS selector
        children = await frame_locator.locator('> *').all()
        count = len(children)
        print(f"ARMAS-PAL-PUEBLO 2: Found {count} children ...")
        # Option 3: Using evaluate_all()
        count = await frame_locator.locator('> *').evaluate_all('(elements) => elements.length')
        print(f"ARMAS-PAL-PUEBLO 3: Found {count} children ...")
        children = frame_locator.locator('*')
        children_count = len(await children.all_inner_texts())
        print(f"ARMAS-PAL-PUEBLO 4: Found {children_count} children ...")
        children_count = await frame_locator.locator(">*").count()
        print(f"ARMAS-PAL-PUEBLO 5: Found {children_count} children ...")
        css = "body > *"
        children_count = await frame_locator.locator(css).count()
        children = await frame_locator.locator(css).element_handles()
        print(f"ARMAS-PAL-PUEBLO 6: Found children_count=[{children_count}] SHOULD BE EQUAL TO len(children)=[{len(children)}] ...")
        css = "body"
        first = frame_locator.locator(css).first
        children_locator = first.locator('> *') 
        children_count = await children_locator.count()
        children = await children_locator.element_handles()
        print(f"ARMAS-PAL-PUEBLO 7: Found children_count=[{children_count}] SHOULD BE EQUAL TO len(children)=[{len(children)}] ...")
        #await locator.click()  # Finally we click ... I can click this or the one below => THIS DOESN'T WORK FOR closed ShadowRoots
        # await frame_locator.owner.click()  # Finally we click ...
        # # await asyncio.sleep(10)  # Waiting for the results of the click
        # await expect(page).to_have_title("NopeCHA - CAPTCHA Demo", timeout=10000) # Better waiting for the results of the click
        # await browser.close()  # Closing the browse ...

        # --- Manually search for the checkbox using Python Playwright API ---
        print("\n--- Starting Manual Recursive Search in Frame (Python API) ---")
        # Start search from the body element within the frame
        # Using .first ensures we start with a single element locator
        # Validate frame existence
        # locator = frame_locator.locator("body")           # Create body locator
        # Validate frame content
        # await expect(locator).to_have_count(1,timeout=1000) # Throws if not found => ITS FAILING
        start_locator = frame_locator.locator('body').first # => I ALREADY TRIED THIS. THIS IS THE PROBLEM I NEED YOUR HELP FIXING
        checkbox_locator = await find_checkbox_recursive_python(start_locator)
        print(f"--- Manual Search Result: {'Found' if checkbox_locator else 'Not Found'} ---")

        # # --- Attempt to click using the found Playwright locator ---
        # if checkbox_locator:
        #     print("Checkbox locator found via Python search, attempting Playwright click...")
        #     # Ensure the found locator still points to an attached element before clicking
        #     await expect(checkbox_locator).to_be_attached(timeout=5000)
        #
        #     for _ in range(1):
        #         # await frame_locator.owner.set_checked(True)  # Finally we click ... - Replaced with checkbox click
        #         await checkbox_locator.set_checked(True) # Click the actual checkbox locator found
        #         print("Attempted click via Playwright locator.")
        #         await asyncio.sleep(5)                       # Waiting for the results of the click
        # else:
        #      print("Checkbox not found via manual Python search. Cannot click.")
        #      # Keep browser open longer if not found, for inspection
        #      await asyncio.sleep(10)

        await browser.close()                            # Closing the browse ...

if __name__ == "__main__":
    asyncio.run(test_cloudflare())
