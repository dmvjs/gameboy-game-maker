"""Locating external dependencies (RGBDS, the browser emulator) and checking their versions.

Nothing here is bundled with gbstage. RGBDS is found from, in order:
  1. the GBSTAGE_RGBDS environment variable (a directory containing rgbasm/rgblink/rgbfix)
  2. "rgbds.path" in the config file
  3. "rgbds.version" in the config file, as a managed install under <home>/rgbds/<version>
  4. the newest supported managed install
  5. the system PATH
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# RGBDS versions we accept. Anything inside the range should work; only TESTED versions
# have been run through the self-test. Bump TESTED after verifying a new release.
RGBDS_MIN = (0, 9, 0)
RGBDS_MAX_EXCLUSIVE = (2, 0, 0)
RGBDS_TESTED = ["0.9.4", "1.0.4"]
RGBDS_RECOMMENDED = "1.0.4"
RGBDS_TOOLS = ["rgbasm", "rgblink", "rgbfix"]

# The browser emulator is pinned to an exact commit and verified by hash.
EMULATOR = {
    "name": "binjgb",
    "repo": "binji/binjgb",
    "commit": "4fd2ad0e01cbb9bfdb1b7e10c4ad177a78912dd3",
    "files": {
        "binjgb.js": ("docs/binjgb.js", "a68e5854b5d68339a34c0aa0b6dbeacd615ed316657ee17b63dafa5e00561b09"),
        "binjgb.wasm": ("docs/binjgb.wasm", "52c165069441a09180b4bd63464318aa7b861b1d36e0d05e8047b48619fd2f0b"),
        "LICENSE": ("LICENSE", "5a7b61a51a5efb789721b3480b502f324094911aeca46937956c561b52638009"),
    },
}

MIN_PYTHON = (3, 9)
EXE = ".exe" if os.name == "nt" else ""


def home():
    return Path(os.environ.get("GBSTAGE_HOME") or Path.home() / ".gbstage")


def config_path():
    return home() / "config.json"


def load_config():
    try:
        return json.loads(config_path().read_text())
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Config file {config_path()} is not valid JSON: {e}")


def save_config(cfg):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(cfg, indent=2) + "\n")


# ---- versions --------------------------------------------------------------

_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)([-+.\w]*)")


def parse_version(text):
    """'rgbasm v1.0.2+hotfix' -> ((1, 0, 2), '+hotfix'); None if no version found."""
    m = _VERSION_RE.search(text or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))), m.group(4)


def fmt_version(v):
    return ".".join(map(str, v))


def supported_range_text():
    return f">={fmt_version(RGBDS_MIN)}, <{fmt_version(RGBDS_MAX_EXCLUSIVE)}"


def compatibility(version_tuple, suffix=""):
    """Return (status, message). status is 'tested', 'untested', or 'unsupported'."""
    v = fmt_version(version_tuple)
    if not (RGBDS_MIN <= version_tuple < RGBDS_MAX_EXCLUSIVE):
        return "unsupported", f"v{v} is outside the supported range ({supported_range_text()})"
    if v in RGBDS_TESTED and not suffix.startswith("-"):
        return "tested", f"v{v}{suffix} is a tested version"
    return "untested", f"v{v}{suffix} is in the supported range but hasn't been tested (tested: {', '.join(RGBDS_TESTED)})"


# ---- RGBDS discovery -------------------------------------------------------

def managed_rgbds_dir(version):
    return home() / "rgbds" / version


def managed_rgbds_versions():
    root = home() / "rgbds"
    if not root.is_dir():
        return []
    found = []
    for d in root.iterdir():
        parsed = parse_version(d.name)
        if parsed and (d / f"rgbasm{EXE}").exists():
            found.append((parsed[0], d.name))
    return [name for _, name in sorted(found, reverse=True)]


def _locate_rgbds():
    """Return (directory or None, source description)."""
    env = os.environ.get("GBSTAGE_RGBDS")
    if env:
        return Path(env).expanduser(), "GBSTAGE_RGBDS environment variable"
    cfg = load_config().get("rgbds", {})
    if cfg.get("path"):
        return Path(cfg["path"]).expanduser(), f"config file ({config_path()})"
    if cfg.get("version"):
        return managed_rgbds_dir(cfg["version"]), f"managed install v{cfg['version']} (selected in config)"
    for name in managed_rgbds_versions():
        parsed = parse_version(name)
        if RGBDS_MIN <= parsed[0] < RGBDS_MAX_EXCLUSIVE:
            return managed_rgbds_dir(name), f"managed install v{name}"
    on_path = shutil.which("rgbasm")
    if on_path:
        return Path(on_path).resolve().parent, "system PATH"
    return None, "not found"


def tool_version(path):
    try:
        out = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10)
    except OSError as e:
        return None, f"could not run {path.name}: {e}"
    except subprocess.TimeoutExpired:
        return None, f"{path.name} --version timed out"
    text = (out.stdout + out.stderr).strip()
    parsed = parse_version(text)
    if out.returncode != 0 or not parsed:
        return None, f"{path.name} --version failed: {text or 'no output'}"
    return parsed, text


def rgbds_info():
    """Everything the UI and doctor need to know about the active RGBDS."""
    directory, source = _locate_rgbds()
    info = {"found": False, "source": source, "dir": str(directory) if directory else None,
            "tools": {}, "version": None, "compat": None, "compat_message": None, "error": None,
            "supported": supported_range_text(), "tested": RGBDS_TESTED, "recommended": RGBDS_RECOMMENDED}
    if directory is None:
        info["error"] = "RGBDS is not installed or not on PATH."
        return info
    versions = {}
    for tool in RGBDS_TOOLS:
        path = directory / f"{tool}{EXE}"
        if not path.exists():
            info["error"] = f"{tool} not found in {directory}"
            return info
        parsed, text = tool_version(path)
        if not parsed:
            info["error"] = text
            return info
        info["tools"][tool] = {"path": str(path), "version": fmt_version(parsed[0]) + parsed[1]}
        versions[tool] = parsed
    info["found"] = True
    distinct = {fmt_version(v) + s for v, s in versions.values()}
    if len(distinct) > 1:
        info["error"] = "RGBDS tools disagree on version: " + ", ".join(
            f"{t} v{fmt_version(v)}{s}" for t, (v, s) in versions.items())
        return info
    version, suffix = versions["rgbasm"]
    info["version"] = fmt_version(version) + suffix
    info["compat"], info["compat_message"] = compatibility(version, suffix)
    return info


def rgbds_tool(info, tool):
    return info["tools"][tool]["path"]


# ---- emulator --------------------------------------------------------------

def emulator_dir():
    return home() / "emulator" / f"{EMULATOR['name']}-{EMULATOR['commit'][:7]}"


def emulator_info(verify_hashes=True):
    import hashlib
    d = emulator_dir()
    info = {"name": EMULATOR["name"], "commit": EMULATOR["commit"][:7], "dir": str(d),
            "installed": False, "error": None}
    for name, (_, sha) in EMULATOR["files"].items():
        f = d / name
        if not f.exists():
            info["error"] = f"{name} is missing from {d}"
            return info
        if verify_hashes and hashlib.sha256(f.read_bytes()).hexdigest() != sha:
            info["error"] = f"{name} doesn't match the pinned hash (file changed or corrupted)"
            return info
    info["installed"] = True
    return info


def python_info():
    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PYTHON
    return {"version": f"{v.major}.{v.minor}.{v.micro}", "ok": ok,
            "required": ".".join(map(str, MIN_PYTHON)), "executable": sys.executable}
