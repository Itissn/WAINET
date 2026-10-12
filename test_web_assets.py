"""Catch HTML references that exist in a checkout but fail in the running site."""
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit
from urllib.request import urlopen

from server import ROOT, create_server
from build_presentation import ASSETS


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        path = attrs.get("src") if tag == "script" else attrs.get("href") if tag == "link" and attrs.get("rel") == "stylesheet" else None
        if path and not urlsplit(path).netloc:
            self.paths.add(path)


class WebAssetTests(unittest.TestCase):
    def test_all_html_scripts_and_styles_are_served_with_the_right_type(self):
        with tempfile.TemporaryDirectory() as directory:
            server = create_server(0, Path(directory) / "test.sqlite3")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for page in ("index.html", "admin.html"):
                    parser = Assets()
                    parser.feed((ROOT / page).read_text(encoding="utf-8"))
                    for path in sorted(parser.paths):
                        with self.subTest(page=page, asset=path):
                            with urlopen(f"http://127.0.0.1:{server.server_port}/" + path.lstrip("/"), timeout=3) as response:
                                self.assertEqual(response.status, 200)
                                self.assertIn("javascript" if path.endswith(".js") else "text/css", response.headers["Content-Type"])
                                self.assertTrue(response.read())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_static_builder_includes_every_homepage_script_and_style(self):
        parser = Assets()
        parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
        self.assertFalse(parser.paths - set(ASSETS))
