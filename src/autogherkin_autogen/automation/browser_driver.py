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
            # Attempt to dismiss cookie/consent overlays (e.g., OneTrust) and site banners post navigation
            self._dismiss_blocking_banners()
            # brief settle to allow DOM updates after dismissal
            try:
                self.page.wait_for_timeout(500)
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"Error loading {url}: {e}")
            return False

    def get_page_source(self):
        return self.page.content()

    # Added for DIP/ports compliance
    def get_page_handle(self):
        return self.page

    def _dismiss_blocking_banners(self):
        """
        Best-effort dismissal of common consent/cookie overlays and site banners that intercept pointer events.
        Targets OneTrust (#onetrust-consent-sdk) and the 'indication' banner observed in logs.
        """
        try:
            ot_root = self.page.locator("#onetrust-consent-sdk").first
            try:
                ot_visible = ot_root.is_visible()
            except Exception:
                ot_visible = False

            if ot_visible:
                candidates = [
                    "#onetrust-reject-all-handler",
                    "#onetrust-accept-btn-handler",
                    "#onetrust-close-btn-container",
                    'button:has-text("Reject All")',
                    'button:has-text("Reject")',
                    'button:has-text("Accept All")',
                    'button:has-text("Accept")',
                ]
                for sel in candidates:
                    try:
                        btn = self.page.locator(sel).first
                        if btn.is_visible():
                            btn.click(timeout=1500)
                            break
                    except Exception:
                        continue
                try:
                    ot_root.wait_for(state="hidden", timeout=3000)
                except Exception:
                    # Force-hide OneTrust as a last resort
                    try:
                        self.page.evaluate(
                            '() => { const el = document.querySelector("#onetrust-consent-sdk"); if (el) { el.style.display = "none"; el.setAttribute("aria-hidden", "true"); } }'
                        )
                    except Exception:
                        pass

            # Site-specific indication banner close button
            try:
                indi = self.page.locator("button#indication-close").first
                if indi.is_visible():
                    indi.click(timeout=1000)
            except Exception:
                pass
        except Exception:
            # Ignore any failures in best-effort cleanup
            pass

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
