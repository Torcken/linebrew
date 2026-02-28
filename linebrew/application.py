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

"""Linebrew Adw.Application — entry point, CSS loading, global actions.

App ID: io.github.linebrew.Linebrew
"""

from __future__ import annotations

import importlib.resources
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gio, Gtk

from linebrew import __app_id__, __version__
from linebrew.preferences_dialog import PreferencesDialog, apply_color_scheme, load_prefs
from linebrew.window import MainWindow


class LinebrewApp(Adw.Application):
    """Top-level application object.

    Responsible for:
    * Loading the application CSS stylesheet.
    * Registering app-level actions (preferences, about, shortcuts).
    * Creating and presenting the main window on activation.
    """

    def __init__(self) -> None:
        """Initialise the application."""
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)
        self.connect("startup", self._on_startup)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def _on_startup(self, _app: "LinebrewApp") -> None:
        """Load CSS and register global actions on startup."""
        self._load_css()
        self._register_actions()

    def _on_activate(self, _app: "LinebrewApp") -> None:
        """Create or raise the main window."""
        win = self.get_active_window()
        if win is None:
            win = MainWindow(application=self)
        win.present()

    # ── CSS ────────────────────────────────────────────────────────────────

    def _load_css(self) -> None:
        """Load style.css from the package data directory."""
        css_path = self._find_css_path()
        if css_path is None:
            return

        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(str(css_path))
        except Exception:
            return

        Gtk.StyleContext.add_provider_for_display(
            Gtk.Widget.get_display(Gtk.Label()),  # any widget for display ref
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _find_css_path(self) -> "Path | None":
        """Locate style.css via importlib.resources (works installed or from src)."""
        try:
            # Python 3.9+ path
            ref = importlib.resources.files("linebrew").joinpath("style.css")
            if ref.is_file():
                return Path(str(ref))
        except (TypeError, AttributeError):
            pass

        # Fallback: look next to this module
        here = Path(__file__).parent
        css = here / "style.css"
        if css.is_file():
            return css
        return None

    # ── Global actions ─────────────────────────────────────────────────────

    def _register_actions(self) -> None:
        """Register app-level Gio.SimpleAction entries."""
        # Preferences  (Ctrl+P)
        prefs_action = Gio.SimpleAction.new("preferences", None)
        prefs_action.connect("activate", self._on_preferences)
        self.add_action(prefs_action)
        self.set_accels_for_action("app.preferences", ["<Control>p"])

        # Keyboard shortcuts  (?)
        shortcuts_action = Gio.SimpleAction.new("shortcuts", None)
        shortcuts_action.connect("activate", self._on_shortcuts)
        self.add_action(shortcuts_action)
        self.set_accels_for_action("app.shortcuts", ["question"])

        # About
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

        # Quit
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def _on_preferences(self, _action: Gio.SimpleAction, _param: object) -> None:
        win = self.get_active_window()
        dlg = PreferencesDialog()
        dlg.present(win)

    def _on_shortcuts(self, _action: Gio.SimpleAction, _param: object) -> None:
        """Display the GtkShortcutsWindow."""
        builder = Gtk.Builder()
        shortcuts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<interface>
  <object class="GtkShortcutsWindow" id="shortcuts_window">
    <property name="modal">1</property>
    <child>
      <object class="GtkShortcutsSection">
        <property name="section-name">shortcuts</property>
        <property name="title">Shortcuts</property>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="title">General</property>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">Refresh current category</property>
                <property name="accelerator">&lt;Control&gt;r F5</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">Focus search</property>
                <property name="accelerator">&lt;Control&gt;f</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">Preferences</property>
                <property name="accelerator">&lt;Control&gt;p</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">brew update</property>
                <property name="accelerator">&lt;Control&gt;u</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">brew cleanup</property>
                <property name="accelerator">&lt;Control&gt;&lt;Shift&gt;c</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">Show this window</property>
                <property name="accelerator">question</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">Quit</property>
                <property name="accelerator">&lt;Control&gt;q</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
  </object>
</interface>"""
        builder.add_from_string(shortcuts_xml)
        shortcuts_win = builder.get_object("shortcuts_window")
        if shortcuts_win:
            parent = self.get_active_window()
            if parent:
                shortcuts_win.set_transient_for(parent)
            shortcuts_win.present()

    def _on_about(self, _action: Gio.SimpleAction, _param: object) -> None:
        """Show the About dialog."""
        about = Adw.AboutDialog()
        about.set_application_name("Linebrew")
        about.set_version(__version__)
        about.set_developer_name("Torcken 🤍")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_comments("A modern interface for Homebrew on Linux")
        about.set_website("https://github.com/Torcken/linebrew")
        about.set_application_icon("io.github.linebrew.Linebrew")
        about.set_developers(["Torcken 🤍"])
        about.set_copyright("©2025 Made with love 🤍 by Torcken")
        parent = self.get_active_window()
        about.present(parent)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Launch the Linebrew application.

    Returns the process exit code.
    """
    app = LinebrewApp()
    return app.run(sys.argv)
