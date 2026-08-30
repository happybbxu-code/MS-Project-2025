"""
Mobile layout regression test (real browser).

Launches the Flask app on an ephemeral port, then drives the installed Chrome
via puppeteer-core (tests/browser/mobile-layout.test.js) at several iPhone
viewport widths and asserts the mobile-critical layout contract:
no horizontal overflow; full title and restart visible; decorative badge
hidden on phones but visible on desktop; patient bubble not clipped; composer
placeholder, input, and send button visible; disclaimer visible.

Requires:
  - Google Chrome at C:/Program Files/Google/Chrome/Application/chrome.exe
  - node + puppeteer-core installed under tests/browser (npm install)
  - swipl is NOT required (only the static page + /start are exercised)
"""
import os
import subprocess
import threading
import time

import pytest

import app as app_module

BASE = os.path.dirname(os.path.abspath(__file__))
BROWSER_DIR = os.path.join(BASE, "tests", "browser")
NODE_TEST = os.path.join(BROWSER_DIR, "mobile-layout.test.js")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

pytestmark = pytest.mark.skipif(
    not os.path.exists(CHROME),
    reason="Google Chrome not found; cannot run real-browser layout test",
)


@pytest.fixture(scope="module")
def live_server():
    """Start the Flask app on an ephemeral port in a background thread."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = app_module.app
    thread = threading.Thread(
        target=server.run,
        kwargs={"host": "127.0.0.1", "port": port, "debug": False, "use_reloader": False},
        daemon=True,
    )
    thread.start()

    # Wait for the server to accept connections.
    import urllib.request

    url = f"http://127.0.0.1:{port}/"
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("Flask server did not start in time")

    yield url
    # daemon thread dies with the process


def test_mobile_layout_no_overflow(live_server):
    """Real-browser check: no horizontal overflow and all mobile-critical
    elements visible at iPhone widths (320/375/390/430)."""
    result = subprocess.run(
        ["node", NODE_TEST, live_server],
        cwd=BROWSER_DIR,
        capture_output=True,
        text=True,
    )
    print("\n" + result.stdout)
    if result.stderr:
        print("STDERR:\n" + result.stderr)
    assert result.returncode == 0, (
        f"mobile layout test failed (exit {result.returncode})\n"
        f"{result.stdout}\n{result.stderr}"
    )
