import os
from playwright.sync_api import sync_playwright, TimeoutError
import time

class FeeCrawler:
    def __init__(self, headless=True):
        self.headless = headless

    def _dismiss_overlays(self, page):
        """Dismiss common cookie banners, overlays, and popups."""
        overlay_selectors = [
            "button[id*='cookie']", "button[class*='cookie']", 
            "button:has-text('Accept')", "button:has-text('I Agree')",
            "button[class*='close']", "div[class*='modal'] button",
            "button[aria-label='Close']"
        ]
        for selector in overlay_selectors:
            try:
                elements = page.locator(selector)
                if elements.count() > 0:
                    for i in range(elements.count()):
                        if elements.nth(i).is_visible():
                            elements.nth(i).click(timeout=2000)
            except Exception:
                pass

    def _expand_accordions(self, page):
        """Finds and expands accordions that might hide fee data."""
        accordion_selectors = [
            "button[aria-expanded='false']",
            "div[class*='accordion']",
            "div[class*='toggle']",
            "span:has-text('+')",
            "span:has-text('Expand')"
        ]
        for selector in accordion_selectors:
            try:
                elements = page.locator(selector)
                for i in range(elements.count()):
                    if elements.nth(i).is_visible():
                        elements.nth(i).scroll_into_view_if_needed()
                        # Hover before click to stabilize dropdowns
                        elements.nth(i).hover(timeout=1000)
                        elements.nth(i).click(timeout=2000)
                        page.wait_for_timeout(500)  # Wait for animation
            except Exception:
                pass

    def crawl_fee_page(self, url, output_dir="screenshots"):
        """
        Crawls a URL to extract fee information.
        Returns a dictionary with extracted text, HTML, and status.
        """
        os.makedirs(output_dir, exist_ok=True)
        result = {
            "url": url,
            "text_content": "",
            "html_content": "",
            "screenshot_path": None,
            "success": False,
            "error": None
        }

        # Check if URL is actually a PDF
        if url.lower().endswith(".pdf"):
            result["success"] = True
            result["is_pdf"] = True
            return result

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = context.new_page()
                page.set_default_timeout(30000)
                
                try:
                    page.goto(url, wait_until="networkidle")
                except TimeoutError:
                    # Fallback if networkidle takes too long
                    pass

                # Handle overlays
                self._dismiss_overlays(page)

                # Scroll down slowly to trigger lazy loading
                for _ in range(3):
                    page.mouse.wheel(0, 1000)
                    page.wait_for_timeout(1000)
                
                # Scroll back to top
                page.evaluate("window.scrollTo(0, 0)")

                # Expand accordions/dropdowns
                self._expand_accordions(page)

                # Grab the visible text after stabilization
                result["text_content"] = page.evaluate("document.body.innerText")
                result["html_content"] = page.content()
                
                # Take screenshot for debugging/audit
                filename = "".join([c if c.isalnum() else "_" for c in url])[:50] + f"_{int(time.time())}.png"
                screenshot_path = os.path.join(output_dir, filename)
                page.screenshot(path=screenshot_path, full_page=True)
                result["screenshot_path"] = screenshot_path
                
                result["success"] = True
                browser.close()
        except Exception as e:
            result["error"] = str(e)
            print(f"FeeCrawler failed for {url}: {e}")

        return result

if __name__ == "__main__":
    # Test crawler
    crawler = FeeCrawler(headless=True)
    res = crawler.crawl_fee_page("https://example.com")
    print(res["success"], res.get("screenshot_path"))
