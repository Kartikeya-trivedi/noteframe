"""Open the UI after the local server answers, not before it is listening."""

import json
import threading
import urllib.error
import urllib.request
import webbrowser


def open_when_ready(port: int, stopped: threading.Event):
    url = f"http://127.0.0.1:{port}"
    # Bypass outbound HTTP proxies for the loopback readiness check.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(120):
        if stopped.is_set():
            return
        try:
            with opener.open(url + "/api/health", timeout=1) as response:
                ready = json.loads(response.read(4096)).get("app") == "noteframe"
            if ready:
                if not webbrowser.open(url):
                    print(f"Open {url} in your browser.", flush=True)
                return
        except (OSError, urllib.error.URLError, ValueError):
            pass
        if stopped.wait(0.5):
            return
    print(f"Browser launch timed out. Check the server output, then open {url}.", flush=True)
