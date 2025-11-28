# Author: MARRI NITHISH
from playwright.sync_api import sync_playwright
from autogherkin_autogen.config import config

class BrowserDriver:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.setup_driver()

    def setup_driver(self):
        self.playwright = sync_playwright().start()
        browser_type = config['browser'].get('type', 'chromium')
        self.browser = getattr(self.playwright, browser_type).launch(headless=config['browser']['headless'])
        self.context = self.browser.new_context(viewport={"width": 1920, "height": 1080})
        self.page = self.context.new_page()
        self.page.set_default_timeout(config['browser']['timeout'])

    def load_page(self, url):
        try:
            self.page.goto(url, wait_until="networkidle")
            return True
        except Exception as e:
            print(f"Error loading {url}: {e}")
            return False

    def get_page_source(self):
        return self.page.content()

    # Added for DIP/ports compliance
    def get_page_handle(self):
        return self.page

    def close(self):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

# Example usage (for testing)
if __name__ == "__main__":
    driver = BrowserDriver()
    driver.load_page("https://example.com")
    print(driver.get_page_source()[:500])  # Print first 500 chars
    driver.close()
