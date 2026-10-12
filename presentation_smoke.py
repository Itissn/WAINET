"""Check the packaged, read-only site in a browser before GitHub Pages deployment."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def run(channel=None, url=None):
    server = None
    if not url:
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(Path(__file__).parent / "docs")))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**({"channel": channel} if channel else {}))
            context = browser.new_context()
            context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).netloc == urlsplit(url).netloc else route.abort())
            page = context.new_page()
            errors, missing, writes = [], [], []
            page.on("pageerror", lambda error: errors.append(error.stack))
            page.on("response", lambda response: missing.append(response.url) if response.status >= 400 and response.url.endswith((".css", ".js", ".json")) else None)
            page.on("request", lambda request: writes.append(request.url) if request.method not in ("GET", "HEAD") else None)
            page.goto(url)
            expect(page.locator(".synthetic-banner")).to_contain_text("READ ONLY")
            expect(page.locator("#connection-status")).to_contain_text("Synthetic demonstration")
            page.locator("#community-picker").select_option("Lyall Bay")
            expect(page.locator("#posts")).not_to_be_empty()
            page.goto(url.rstrip("/") + "/demo.html")
            expect(page.locator(".synthetic-banner")).to_contain_text("SYNTHETIC")
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(url)
            expect(page.locator("#community-picker")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile overflow"
            assert not errors, errors
            assert not missing, missing
            assert not writes, writes
            context.close()
            browser.close()
            return {"read_only_presentation": "passed", "community_feed": "passed",
                    "dataset_explorer": "passed", "mobile_layout": "passed", "writes": 0}
    finally:
        if server:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel")
    parser.add_argument("--url", help="Optional deployed presentation URL; checks are read-only.")
    args = parser.parse_args()
    print(json.dumps(run(args.channel, args.url), indent=2))
