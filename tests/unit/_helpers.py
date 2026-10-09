"""Reusable offline fixtures for Python unit tests."""

import base64
import importlib.util
import json
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread


def load_script(name, path):
    """Load a .py script by path without modifying sys.path."""
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def stub_http(handler):
    """Serve a test HTTP handler on loopback; always close its socket."""
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def fake_jwt(payload, signature='not-a-signature', header=None):
    """Produce an unsigned fixture JWT; never use for authentication."""
    if header is None:
        header = {'alg': 'RS256', 'typ': 'JWT'}

    def segment(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()

    return f'{segment(header)}.{segment(payload)}.{signature}'
