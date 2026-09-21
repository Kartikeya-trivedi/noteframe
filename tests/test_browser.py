import io
import threading

from noteframe.browser import open_when_ready


def test_browser_waits_for_noteframe(monkeypatch):
    responses = iter([b'{"app":"another-server"}', b'{"app":"noteframe"}'])
    opened = []

    class Opener:
        def open(self, url, timeout):
            assert url.endswith("/api/health")
            return io.BytesIO(next(responses))

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            return False

    monkeypatch.setattr("noteframe.browser.urllib.request.build_opener", lambda *args: Opener())
    monkeypatch.setattr("noteframe.browser.webbrowser.open", lambda url: opened.append(url) or True)
    open_when_ready(8767, Stop())
    assert opened == ["http://127.0.0.1:8767"]


def test_no_browser_after_server_stops(monkeypatch):
    stopped = threading.Event()
    stopped.set()
    opened = []
    monkeypatch.setattr("noteframe.browser.webbrowser.open", lambda url: opened.append(url))
    open_when_ready(8767, stopped)
    assert not opened
