"""Download and install RGBDS and the browser emulator into the gbstage home directory."""

import hashlib
import io
import json
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import deps


class InstallError(Exception):
    pass


def _get(url, accept=None):
    headers = {"User-Agent": "gbstage-installer"}
    if accept:
        headers["Accept"] = accept
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 403 and "api.github.com" in url:
            raise InstallError("GitHub API rate limit hit. Wait an hour or set GITHUB_TOKEN.")
        raise InstallError(f"Download failed ({e.code}): {url}")
    except urllib.error.URLError as e:
        raise InstallError(f"Couldn't reach {url}: {e.reason}. Check your internet connection.")


def _platform_asset_matcher():
    system, machine = platform.system(), platform.machine().lower()
    if system == "Darwin":
        return lambda name: "macos" in name and name.endswith(".zip")
    if system == "Windows":
        return lambda name: "win64" in name and name.endswith(".zip")
    if system == "Linux" and machine in ("x86_64", "amd64"):
        return lambda name: "linux-x86_64" in name
    raise InstallError(
        f"RGBDS doesn't publish prebuilt binaries for {system} {machine}. Install it with your package "
        "manager or build it from source (https://rgbds.gbdev.io/install), then run "
        "`python3 -m gbstage use rgbds --path <dir>` or just put it on your PATH.")


def _releases():
    data = json.loads(_get("https://api.github.com/repos/gbdev/rgbds/releases?per_page=100"))
    out = []
    for r in data:
        parsed = deps.parse_version(r["tag_name"])
        if parsed and not r["draft"] and not r["prerelease"] and not parsed[1].startswith("-"):
            out.append((parsed[0], r))
    return sorted(out, key=lambda x: x[0], reverse=True)


def _pick_release(version):
    releases = _releases()
    if version == "latest":
        for v, r in releases:
            if deps.RGBDS_MIN <= v < deps.RGBDS_MAX_EXCLUSIVE:
                return v, r
        raise InstallError("No released RGBDS version falls inside the supported range.")
    wanted = deps.parse_version(version)
    if not wanted:
        raise InstallError(f"'{version}' isn't a version number (expected something like {deps.RGBDS_RECOMMENDED}).")
    for v, r in releases:
        if v == wanted[0]:
            return v, r
    raise InstallError(f"RGBDS v{version} isn't a published release.")


def _extract_tools(archive_name, data, dest):
    """Unpack only the rgb* executables into dest, flattening any folders."""
    wanted = {f"{t}{deps.EXE}" for t in deps.RGBDS_TOOLS} | {f"rgbgfx{deps.EXE}"}
    dest.mkdir(parents=True, exist_ok=True)
    written = set()
    if archive_name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for member in z.infolist():
                name = Path(member.filename).name
                if name in wanted and not member.is_dir():
                    (dest / name).write_bytes(z.read(member))
                    written.add(name)
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for member in t.getmembers():
                name = Path(member.name).name
                if name in wanted and member.isfile():
                    (dest / name).write_bytes(t.extractfile(member).read())
                    written.add(name)
    for name in written:
        p = dest / name
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    missing = {f"{t}{deps.EXE}" for t in deps.RGBDS_TOOLS} - written
    if missing:
        raise InstallError(f"The release archive didn't contain: {', '.join(sorted(missing))}")


def install_rgbds(version=None, activate=True, allow_unverified=False, log=print):
    version = version or deps.RGBDS_RECOMMENDED
    v, release = _pick_release(version)
    vs = deps.fmt_version(v)
    status, message = deps.compatibility(v)
    if status == "unsupported":
        raise InstallError(message)

    match = _platform_asset_matcher()
    assets = [a for a in release["assets"] if match(a["name"])]
    if not assets:
        raise InstallError(f"RGBDS v{vs} has no prebuilt download for this platform.")
    asset = assets[0]

    log(f"Downloading RGBDS v{vs} ({asset['name']}, {asset['size'] // 1024} KB)...")
    data = _get(asset["browser_download_url"])
    digest = asset.get("digest")
    if digest and digest.startswith("sha256:"):
        if hashlib.sha256(data).hexdigest() != digest.split(":", 1)[1]:
            raise InstallError("Checksum mismatch: the download doesn't match what GitHub published. Not installing.")
        log("Checksum verified (SHA-256 published by GitHub).")
    elif not allow_unverified:
        raise InstallError(
            f"GitHub publishes no checksum for RGBDS v{vs}, so the download can't be verified. "
            "Use a newer version, or pass --allow-unverified if you accept that.")
    else:
        log("WARNING: no published checksum; installing unverified.")

    final = deps.managed_rgbds_dir(vs)
    deps.home().mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=deps.home()) as tmp:
        staging = Path(tmp) / vs
        _extract_tools(asset["name"], data, staging)
        for tool in deps.RGBDS_TOOLS:
            parsed, text = deps.tool_version(staging / f"{tool}{deps.EXE}")
            if not parsed:
                raise InstallError(f"Installed {tool} won't run: {text}")
            if parsed[0] != v:
                raise InstallError(f"{tool} reports {text}, expected v{vs}")
        if final.exists():
            shutil.rmtree(final)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(final))

    log(f"Installed RGBDS v{vs} to {final}")
    if status == "untested":
        log(f"Note: {message}")
    if activate:
        use_rgbds(version=vs, log=log)
    return final


def use_rgbds(version=None, path=None, log=print):
    cfg = deps.load_config()
    rgbds = cfg.setdefault("rgbds", {})
    rgbds.pop("path", None)
    rgbds.pop("version", None)
    if path:
        p = Path(path).expanduser().resolve()
        if not (p / f"rgbasm{deps.EXE}").exists():
            raise InstallError(f"No rgbasm in {p}")
        rgbds["path"] = str(p)
        log(f"Using RGBDS from {p}")
    elif version:
        if not (deps.managed_rgbds_dir(version) / f"rgbasm{deps.EXE}").exists():
            raise InstallError(f"RGBDS v{version} isn't installed. Run: python3 -m gbstage install rgbds --version {version}")
        rgbds["version"] = version
        log(f"Using RGBDS v{version}")
    else:
        log("Using automatic RGBDS detection")
    deps.save_config(cfg)


def install_emulator(log=print):
    e = deps.EMULATOR
    dest = deps.emulator_dir()
    log(f"Downloading {e['name']} @ {e['commit'][:7]}...")
    files = {}
    for name, (repo_path, sha) in e["files"].items():
        data = _get(f"https://raw.githubusercontent.com/{e['repo']}/{e['commit']}/{repo_path}")
        if hashlib.sha256(data).hexdigest() != sha:
            raise InstallError(f"{name} doesn't match the pinned hash. Not installing.")
        files[name] = data
    dest.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (dest / name).write_bytes(data)
    log(f"Installed {e['name']} to {dest} (hashes verified)")
    return dest


def install_all(log=print):
    info = deps.rgbds_info()
    if info["found"] and not info["error"] and info["compat"] != "unsupported":
        log(f"RGBDS v{info['version']} already available ({info['source']}); skipping.")
    else:
        install_rgbds(log=log)
    if deps.emulator_info()["installed"]:
        log("Emulator already installed; skipping.")
    else:
        install_emulator(log=log)
