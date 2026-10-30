"""Reusable offline fixtures for Python unit tests."""

import base64
import importlib.machinery
import importlib.util
import json
import sys
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread


def load_script(name, path):
    """Load a Python source file by path, including extensionless bin/ scripts.

    Replaces SourceFileLoader.load_module(), removed in Python 3.15. Like that
    API, the module is registered in sys.modules while it executes (dataclasses
    and pickling resolve classes through it); a failed load restores the prior
    entry so a broken script cannot leave a half-initialised module behind.
    sys.path is never modified.
    """
    loader = importlib.machinery.SourceFileLoader(name, str(Path(path)))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    missing = object()
    previous = sys.modules.get(name, missing)
    sys.modules[name] = module
    try:
        loader.exec_module(module)
    except BaseException:
        if previous is missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
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
