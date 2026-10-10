"""Local web server for the editor. Binds to 127.0.0.1 only."""

import base64
import hashlib
import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, codegen, deps, doctor, profiler
from .build import BuildError
from .project import FONT_FILE
from .install import InstallError, install_all, install_emulator, install_rgbds

EDITOR_DIR = Path(__file__).resolve().parent.parent / "editor"


def _hash_files(files):
    h = hashlib.sha256()
    for f in sorted(files):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


# The engine code this server process actually imported (it only changes on restart).
ENGINE_STAMP = _hash_files(list(Path(__file__).parent.glob("*.py")) + list(Path(__file__).parent.glob("*.asm")) + [FONT_FILE])


def code_stamp():
    """Fingerprint of the code a page gets: the editor files as they are on disk right now (that's what
    gets served), plus the engine this server is running. An open page whose stamp differs is out of date."""
    return _hash_files(EDITOR_DIR.glob("*")) + ENGINE_STAMP
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
_install_lock = threading.Lock()


def status():
    try:
        rgbds = deps.rgbds_info()
    except RuntimeError as e:
        rgbds = {"found": False, "error": str(e)}
    return {"app": {"name": "gbstage", "version": __version__, "stamp": code_stamp()},
            "python": deps.python_info(), "rgbds": rgbds, "emulator": deps.emulator_info()}


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".wasm": "application/wasm", ".js": "text/javascript"}

    def log_message(self, fmt, *args):
        pass

    def _host_ok(self):
        # Rejects DNS-rebinding requests that reach us under some other hostname.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            self.send_error(403, "Bad host")
            return False
        return True

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Gbstage-Stamp", code_stamp())
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass                    # the editor moved on (a newer build replaced this one)

    def _file(self, root, rel):
        root = root.resolve()
        path = (root / rel).resolve()
        if root not in path.parents or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok():
            return
        path = urlparse(self.path).path
        if path == "/api/status":
            return self._json(status())
        if path == "/api/doctor":
            checks = doctor.run_checks()
            return self._json({"overall": doctor.overall(checks), "checks": checks})
        if path == "/api/selftest.gb":
            try:
                rom = doctor.build_selftest(deps.rgbds_info())
            except BuildError as e:
                return self._json({"error": f"{e.step} failed: {e.output}"}, 500)
            except Exception as e:
                return self._json({"error": f"couldn't build the test ROM: {e}"}, 500)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(rom)))
            self.end_headers()
            self.wfile.write(rom)
            return
        if path in ("/api/font.txt", "/api/font-bold.txt"):
            return self._file(FONT_FILE.parent, path[len("/api/"):])
        if path.startswith("/emulator/"):
            return self._file(deps.emulator_dir(), path[len("/emulator/"):])
        if path == "/":
            path = "/index.html"
        return self._file(EDITOR_DIR, path.lstrip("/"))

    def do_POST(self):
        if not self._host_ok():
            return
        # A custom header can't be sent cross-origin without a CORS preflight, which we never
        # approve, so other websites can't trigger installs.
        if self.headers.get("X-Gbstage") != "1":
            return self.send_error(403)
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"ok": False, "errors": ["Request body isn't valid JSON."]}, 400)
        if path == "/api/build":
            return self._build(body)
        if path != "/api/install":
            return self.send_error(404)
        what = body.get("what", "all")
        log = []
        if not _install_lock.acquire(blocking=False):
            return self._json({"ok": False, "log": ["An install is already running."]}, 409)
        try:
            {"rgbds": install_rgbds, "emulator": install_emulator}.get(what, install_all)(log=log.append)
            return self._json({"ok": True, "log": log})
        except InstallError as e:
            return self._json({"ok": False, "log": log + [f"error: {e}"]}, 500)
        finally:
            _install_lock.release()


    def _build(self, project):
        try:
            build, asm, stats, normalized = codegen.build_project(project)
        except codegen.ProjectError as e:
            return self._json({"ok": False, "errors": e.errors}, 400)
        except BuildError as e:
            return self._json({"ok": False, "errors": [f"{e.step} failed: {e.output}"]}, 500)
        return self._json({"ok": True, "rom": base64.b64encode(build.rom).decode(), "asm": asm, "stats": stats,
                           "report": profiler.profile(build, codegen.auto_session(normalized))})


def serve(port=8765, open_browser=True):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print(f"gbstage {__version__} running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
