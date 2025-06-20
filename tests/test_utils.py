from browser_use import BrowserProfile, BrowserSession


async def create_browser_session(playwright):
  # Creating everything clean and pure outside ...
  chromium = playwright.chromium
  browser = await chromium.launch(headless=False)
  browser_context = await browser.new_context()
  page = await browser_context.new_page()
  browser_profile = BrowserProfile(
    stealth=True
  )

  # Passing all the objects to the session not to create anything internally ...
  browser_session = BrowserSession(
    playwright=playwright,
    browser=browser,
    browser_context=browser_context,
    page=page,
    browser_profile=browser_profile,
  )

  return browser_session
