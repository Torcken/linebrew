# Linebrew
# Copyright (C) 2025 Torcken
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Homebrew CLI interface — all subprocess wrappers for Linebrew.

All public functions that perform brew operations accept an ``on_line``
callback for streaming output and an ``on_complete`` callback that receives
``(returncode: int, full_output: str)``.  Both callbacks are dispatched to
the GTK main loop via :func:`GLib.idle_add` so they are always safe to call
UI code from.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from typing import Callable, Optional

import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib

# ---------------------------------------------------------------------------
# Brew executable discovery
# ---------------------------------------------------------------------------

_brew_path: Optional[str] = None


def find_brew() -> Optional[str]:
    """Return the path to the ``brew`` executable, or ``None`` if not found.

    Checks :envvar:`PATH` first, then common Linux Homebrew install locations.
    """
    global _brew_path
    if _brew_path and os.path.isfile(_brew_path):
        return _brew_path

    candidate = shutil.which("brew")
    if candidate:
        _brew_path = candidate
        return _brew_path

    for p in (
        "/home/linuxbrew/.linuxbrew/bin/brew",
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
    ):
        if os.path.isfile(p):
            _brew_path = p
            return _brew_path

    return None


def _get_env() -> dict[str, str]:
    """Return a copy of :data:`os.environ` with the brew bin directory in PATH."""
    env = os.environ.copy()
    brew = find_brew()
    if brew:
        brew_bin = os.path.dirname(brew)
        current_path = env.get("PATH", "")
        if brew_bin not in current_path.split(os.pathsep):
            env["PATH"] = f"{brew_bin}{os.pathsep}{current_path}"
    return env


# ---------------------------------------------------------------------------
# Low-level execution helpers
# ---------------------------------------------------------------------------

def _run_async(
    args: list[str],
    on_line: Optional[Callable[[str], None]],
    on_complete: Optional[Callable[[int, str], None]],
) -> None:
    """Run ``brew <args>`` in a daemon thread, streaming output via idle_add."""

    def _worker() -> None:
        brew = find_brew()
        if not brew:
            msg = "Error: brew not found. Install Homebrew first.\n"
            if on_line:
                GLib.idle_add(on_line, msg)
            if on_complete:
                GLib.idle_add(on_complete, 1, msg)
            return

        cmd = [brew] + args
        env = _get_env()
        collected: list[str] = []

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                bufsize=1,
            )
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                collected.append(raw_line)
                if on_line:
                    line_copy = raw_line
                    GLib.idle_add(on_line, line_copy)
            proc.wait()
            returncode = proc.returncode
        except OSError as exc:
            error = f"Error executing brew: {exc}\n"
            if on_line:
                GLib.idle_add(on_line, error)
            if on_complete:
                GLib.idle_add(on_complete, 1, error)
            return

        full_output = "".join(collected)
        if on_complete:
            GLib.idle_add(on_complete, returncode, full_output)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _run_sync(args: list[str]) -> tuple[int, str]:
    """Run ``brew <args>`` synchronously (only for background data-fetch threads)."""
    brew = find_brew()
    if not brew:
        return 1, ""

    cmd = [brew] + args
    env = _get_env()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )
        return result.returncode, result.stdout
    except OSError as exc:
        return 1, str(exc)


# ---------------------------------------------------------------------------
# Data-fetch functions (run in daemon threads, deliver via callback)
# ---------------------------------------------------------------------------

def get_installed_formulae(callback: Callable[[list[dict]], None]) -> None:
    """Fetch installed formulae asynchronously.

    Calls ``callback(list[dict])`` on the main thread where each dict has
    keys ``name``, ``version``, ``status``.
    """

    def _worker() -> None:
        rc, out = _run_sync(["list", "--versions"])
        formulae: list[dict] = []
        for line in out.strip().splitlines():
            parts = line.split()
            if parts:
                name = parts[0]
                version = parts[1] if len(parts) > 1 else ""
                formulae.append({"name": name, "version": version, "status": "installed"})
        GLib.idle_add(callback, formulae)

    threading.Thread(target=_worker, daemon=True).start()


def get_all_formulae(callback: Callable[[list[dict]], None]) -> None:
    """Fetch all formulae with real installation and outdated status."""

    def _worker() -> None:
        _, all_out = _run_sync(["formulae"])
        _, installed_out = _run_sync(["list", "--versions"])
        _, outdated_out = _run_sync(["outdated"])

        installed: dict[str, str] = {}
        for line in installed_out.strip().splitlines():
            parts = line.split()
            if parts:
                installed[parts[0]] = parts[1] if len(parts) > 1 else ""

        outdated: set[str] = set()
        for line in outdated_out.strip().splitlines():
            parts = line.split()
            if parts:
                outdated.add(parts[0])

        formulae: list[dict] = []
        for line in all_out.strip().splitlines():
            name = line.strip()
            if not name:
                continue
            if name in outdated:
                status = "outdated"
                version = installed.get(name, "")
            elif name in installed:
                status = "installed"
                version = installed[name]
            else:
                status = "available"
                version = ""
            formulae.append({"name": name, "version": version, "status": status})

        GLib.idle_add(callback, formulae)

    threading.Thread(target=_worker, daemon=True).start()


def get_outdated_formulae(callback: Callable[[list[dict]], None]) -> None:
    """Fetch outdated formulae asynchronously."""

    def _worker() -> None:
        rc, out = _run_sync(["outdated", "--verbose"])
        formulae: list[dict] = []
        for line in out.strip().splitlines():
            parts = line.split()
            if parts:
                name = parts[0]
                # "name (installed) < latest"
                installed = ""
                latest = ""
                if len(parts) >= 3:
                    installed = parts[1].strip("()")
                    latest = parts[-1]
                formulae.append({
                    "name": name,
                    "version": installed,
                    "latest_version": latest,
                    "status": "outdated",
                })
        GLib.idle_add(callback, formulae)

    threading.Thread(target=_worker, daemon=True).start()


def get_leaves(callback: Callable[[list[dict]], None]) -> None:
    """Fetch leaf formulae (not dependencies of any other installed formula)."""

    def _worker() -> None:
        rc, out = _run_sync(["leaves"])
        formulae: list[dict] = []
        for line in out.strip().splitlines():
            name = line.strip()
            if name:
                formulae.append({"name": name, "version": "", "status": "installed"})
        GLib.idle_add(callback, formulae)

    threading.Thread(target=_worker, daemon=True).start()


def get_pinned_formulae(callback: Callable[[list[dict]], None]) -> None:
    """Fetch pinned formulae asynchronously."""

    def _worker() -> None:
        rc, out = _run_sync(["list", "--pinned"])
        formulae: list[dict] = []
        for line in out.strip().splitlines():
            name = line.strip()
            if name:
                formulae.append({"name": name, "version": "", "status": "pinned"})
        GLib.idle_add(callback, formulae)

    threading.Thread(target=_worker, daemon=True).start()


def get_taps(callback: Callable[[list[dict]], None]) -> None:
    """Fetch tapped repositories asynchronously."""

    def _worker() -> None:
        rc, out = _run_sync(["tap"])
        taps: list[dict] = []
        for line in out.strip().splitlines():
            name = line.strip()
            if name:
                taps.append({"name": name, "version": "", "status": "tap"})
        GLib.idle_add(callback, taps)

    threading.Thread(target=_worker, daemon=True).start()


def get_formula_info(
    name: str,
    callback: Callable[[Optional[dict]], None],
) -> None:
    """Fetch detailed JSON info for a formula via ``brew info --json=v1``."""

    def _worker() -> None:
        rc, out = _run_sync(["info", "--json=v1", name])
        if rc != 0 or not out.strip():
            GLib.idle_add(callback, None)
            return
        try:
            data = json.loads(out)
            GLib.idle_add(callback, data[0] if data else None)
        except (json.JSONDecodeError, IndexError):
            GLib.idle_add(callback, None)

    threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Mutating brew operations (stream output)
# ---------------------------------------------------------------------------

def install_formula(
    name: str,
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew install <name>``."""
    _run_async(["install", name], on_line, on_complete)


def uninstall_formula(
    name: str,
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew uninstall <name>``."""
    _run_async(["uninstall", name], on_line, on_complete)


def upgrade_formula(
    name: str,
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew upgrade <name>``."""
    _run_async(["upgrade", name], on_line, on_complete)


def upgrade_all(
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew upgrade`` (upgrade all outdated formulae)."""
    _run_async(["upgrade"], on_line, on_complete)


def pin_formula(
    name: str,
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew pin <name>``."""
    _run_async(["pin", name], on_line, on_complete)


def unpin_formula(
    name: str,
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew unpin <name>``."""
    _run_async(["unpin", name], on_line, on_complete)


def tap_repository(
    repo: str,
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew tap <repo>``."""
    _run_async(["tap", repo], on_line, on_complete)


def untap_repository(
    repo: str,
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew untap <repo>``."""
    _run_async(["untap", repo], on_line, on_complete)


def run_update(
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew update``."""
    _run_async(["update"], on_line, on_complete)


def run_cleanup(
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew cleanup``."""
    _run_async(["cleanup"], on_line, on_complete)


def run_doctor(
    on_line: Callable[[str], None],
    on_complete: Callable[[int, str], None],
) -> None:
    """Run ``brew doctor``."""
    _run_async(["doctor"], on_line, on_complete)
