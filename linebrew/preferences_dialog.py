# Linebrew
# Copyright (C) 2025  Torcken
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

"""Preferences dialog for Linebrew.

Settings are persisted to ``~/.config/linebrew/config.json`` and read back
on startup.  The dialog uses :class:`Adw.PreferencesDialog` with switch rows
and a combo row for the colour scheme.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

# ---------------------------------------------------------------------------
# Persistent config helpers
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path.home() / ".config" / "linebrew" / "config.json"

_DEFAULTS: dict[str, Any] = {
    "color_scheme": "system",    # "system" | "light" | "dark"
    "update_on_launch": False,
    "show_all_on_startup": False,
}


def load_prefs() -> dict[str, Any]:
    """Load preferences from disk, filling missing keys with defaults."""
    prefs = dict(_DEFAULTS)
    if _CONFIG_PATH.exists():
        try:
            with _CONFIG_PATH.open() as fh:
                saved = json.load(fh)
            prefs.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return prefs


def save_prefs(prefs: dict[str, Any]) -> None:
    """Persist *prefs* to ``~/.config/linebrew/config.json``."""
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CONFIG_PATH.open("w") as fh:
            json.dump(prefs, fh, indent=2)
    except OSError:
        pass


def apply_color_scheme(scheme: str) -> None:
    """Apply *scheme* (``"system"``, ``"light"``, or ``"dark"``) to Adwaita."""
    style_manager = Adw.StyleManager.get_default()
    mapping = {
        "system": Adw.ColorScheme.DEFAULT,
        "light": Adw.ColorScheme.FORCE_LIGHT,
        "dark": Adw.ColorScheme.FORCE_DARK,
    }
    style_manager.set_color_scheme(mapping.get(scheme, Adw.ColorScheme.DEFAULT))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class PreferencesDialog(Adw.PreferencesDialog):
    """Application preferences dialog.

    Changes take effect immediately; they are also written to disk so they
    persist across sessions.
    """

    def __init__(self) -> None:
        """Build the preferences UI."""
        super().__init__()
        self.set_title("Preferences")
        self.set_search_enabled(False)

        self._prefs = load_prefs()

        # ── Appearance page ───────────────────────────────────────────────
        appearance_page = Adw.PreferencesPage()
        appearance_page.set_title("Appearance")
        appearance_page.set_icon_name("preferences-desktop-appearance-symbolic")
        self.add(appearance_page)

        appearance_group = Adw.PreferencesGroup()
        appearance_group.set_title("Theme")
        appearance_page.add(appearance_group)

        # Colour scheme combo row
        self._scheme_row = Adw.ComboRow()
        self._scheme_row.set_title("Color Scheme")
        self._scheme_row.set_subtitle("Controls the application colour theme")
        scheme_model = Gtk.StringList.new(["System Default", "Light", "Dark"])
        self._scheme_row.set_model(scheme_model)

        scheme_map = {"system": 0, "light": 1, "dark": 2}
        self._scheme_row.set_selected(
            scheme_map.get(self._prefs.get("color_scheme", "system"), 0)
        )
        self._scheme_row.connect("notify::selected", self._on_scheme_changed)
        appearance_group.add(self._scheme_row)

        # ── Behaviour page ─────────────────────────────────────────────────
        behaviour_page = Adw.PreferencesPage()
        behaviour_page.set_title("Behaviour")
        behaviour_page.set_icon_name("preferences-system-symbolic")
        self.add(behaviour_page)

        behaviour_group = Adw.PreferencesGroup()
        behaviour_group.set_title("On Launch")
        behaviour_page.add(behaviour_group)

        self._update_row = Adw.SwitchRow()
        self._update_row.set_title("Run brew update on Launch")
        self._update_row.set_subtitle("Fetch the latest formula index when the app starts")
        self._update_row.set_active(self._prefs.get("update_on_launch", False))
        self._update_row.connect("notify::active", self._on_update_toggle)
        behaviour_group.add(self._update_row)

        self._show_all_row = Adw.SwitchRow()
        self._show_all_row.set_title("Show All Formulae on Startup")
        self._show_all_row.set_subtitle("Automatically select the All Formulae category")
        self._show_all_row.set_active(self._prefs.get("show_all_on_startup", False))
        self._show_all_row.connect("notify::active", self._on_show_all_toggle)
        behaviour_group.add(self._show_all_row)

    # ── Signal handlers ────────────────────────────────────────────────────

    def _on_scheme_changed(self, row: Adw.ComboRow, _param: object) -> None:
        idx = row.get_selected()
        scheme_keys = ["system", "light", "dark"]
        scheme = scheme_keys[idx] if idx < len(scheme_keys) else "system"
        self._prefs["color_scheme"] = scheme
        apply_color_scheme(scheme)
        save_prefs(self._prefs)

    def _on_update_toggle(self, row: Adw.SwitchRow, _param: object) -> None:
        self._prefs["update_on_launch"] = row.get_active()
        save_prefs(self._prefs)

    def _on_show_all_toggle(self, row: Adw.SwitchRow, _param: object) -> None:
        self._prefs["show_all_on_startup"] = row.get_active()
        save_prefs(self._prefs)
