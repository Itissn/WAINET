"""Real browser acceptance checks, isolated data and mocked AI. No paid calls.

python browser_smoke.py --channel chrome
CI: python -m playwright install --with-deps chromium; python browser_smoke.py
"""
import argparse
import json
from pathlib import Path
import tempfile
import threading
import sys
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect
from PIL import Image
from server import create_server, process_next
from test_server import analysis
import official_data
import accounts
from manage import export_records


def run(channel=None, screenshot=None):
    with tempfile.TemporaryDirectory(prefix="wainet-browser-") as directory:
        photo = Path(directory) / "synthetic-photo.png"
        Image.new("RGB", (800, 600), "#457f93").save(photo)
        server = create_server(0, Path(directory) / "test.sqlite3")
        server_errors = []
        server.handle_error = lambda *_: server_errors.append(type(sys.exc_info()[1]).__name__)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.object(official_data, "get", side_effect=lambda store, community, *args, **kwargs: official_data.offline(None, community)), sync_playwright() as playwright:
                browser = playwright.chromium.launch(**({"channel": channel} if channel else {}))
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                # Offline acceptance run: exercise community-picker fallback when maps fail.
                context.route("**/*", lambda route: route.continue_() if
                              urlsplit(route.request.url).netloc == urlsplit(base).netloc else route.abort())
                page = context.new_page()
                errors, missing = [], []
                page.on("pageerror", lambda error: errors.append(error.stack))
                page.on("response", lambda response: missing.append(response.url) if
                        response.status >= 400 and urlsplit(response.url).path.endswith((".js", ".css")) else None)
                page.goto(base)
                expect(page.locator("#connection-status")).to_contain_text("saved to the local database")
                page.locator("#header-register").click()
                page.locator('#auth-form [name="display_name"]').fill("Browser Test")
                page.locator('#auth-form [name="email"]').fill("browser@example.test")
                page.locator('#auth-form [name="password"]').fill("A synthetic test password 42!")
                page.locator("#auth-submit").click()
                expect(page.locator("#header-account")).to_be_visible()
                page.locator("#community-picker").select_option("Lyall Bay")
                page.locator("#photo").set_input_files(str(photo))
                expect(page.locator("#photo-preview")).to_be_visible()
                page.locator('#compose-form [name="feelings"]').fill("Synthetic acceptance observation")
                page.locator("#extra-details > summary").click()
                page.locator("#photo-details > summary").click()
                page.locator("#observed-at").fill((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"))
                with page.expect_response(lambda response: response.url.endswith("/api/observations") and
                                          response.request.method == "POST") as upload:
                    page.locator('#compose-form button[type="submit"]').click()
                assert upload.value.status == 201, upload.value.text()
                expect(page.locator("#posts")).to_contain_text("Synthetic acceptance observation")
                with server.store.connect() as db:
                    row = db.execute("SELECT * FROM observations").fetchone()
                    assert row["user_id"] is not None
                    assert row["status"] == "pending"
                # Actual worker and DB, deterministic provider fixture only.
                process_next(server.store, "offline-fixture", "mock-model",
                             analyzer=lambda *_: (analysis(), "fixture"))
                page.reload()
                expect(page.locator("#posts")).to_contain_text("Synthetic acceptance observation")
                page.locator("#header-account").click()
                page.locator("#sign-out").click()
                expect(page.locator("#header-sign-in")).to_be_visible()
                accounts.bootstrap_temporary_admin(server.store, "admin@example.test",
                                                    accounts.hash_password("Temporary test password 42!"))
                page.goto(base + "/admin")
                page.locator('#admin-login-form [name="email"]').fill("admin@example.test")
                page.locator('#admin-login-form [name="password"]').fill("Temporary test password 42!")
                page.locator('#admin-login-form button[type="submit"]').click()
                expect(page.locator("#admin-password-form")).to_be_visible()
                page.locator('#admin-password-form [name="current_password"]').fill("Temporary test password 42!")
                for field in ("new_password", "confirmation"):
                    page.locator(f'#admin-password-form [name="{field}"]').fill("Changed test password 84!")
                page.locator('#admin-password-form button[type="submit"]').click()
                expect(page.locator("#admin-workspace")).to_be_visible()
                assert export_records(server.store)["record_count"] == 0
                page.locator("#admin-records [data-record]").first.click()
                page.locator('#admin-review-form [name="decision"]').select_option("approved")
                page.locator('#admin-review-form [name="note"]').fill("Reviewed synthetic fixture for acceptance testing only.")
                with page.expect_response(lambda response: "/api/admin/reviews/" in response.url):
                    page.locator('#admin-review-form button[type="submit"]').click()
                assert export_records(server.store)["record_count"] == 1
                page.locator("#close-admin-record").click()
                with page.expect_download() as download:
                    page.locator("#export-json").click()
                exported = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
                assert exported
                page.locator("#admin-sign-out").click()
                # A narrow screen must retain a way to choose a community and upload.
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(base)
                expect(page.locator("#community-picker")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile page overflows horizontally"
                if screenshot:
                    page.screenshot(path=screenshot, full_page=True)
                assert not missing, f"Missing assets: {missing}"
                assert not errors, f"Uncaught browser errors: {errors}"
                assert not server_errors, f"Unhandled server errors: {server_errors}"
                context.close()
                browser.close()
                return {"registration": "passed", "member_upload": "passed",
                        "persistence": "passed", "mock_worker": "passed", "sign_out": "passed",
                        "admin_password_setup": "passed", "human_review": "passed", "admin_export": "passed",
                        "mobile_picker": "passed", "missing_assets": missing, "browser_errors": errors,
                        "live_ai": False}
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel")
    parser.add_argument("--screenshot")
    args = parser.parse_args()
    print(json.dumps(run(args.channel, args.screenshot), indent=2))
