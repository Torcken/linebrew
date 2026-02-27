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

"""Streaming operation progress dialog for Linebrew.

Displays a terminal-style text view that receives live output from a brew
subprocess, colour-coding important lines and updating a progress bar.
"""

from __future__ import annotations

from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GLib", "2.0")
from gi.repository import Adw, GLib, GObject, Gtk


class ProgressDialog(Gtk.Window):
    """Modal window that streams brew command output in real-time.

    Usage::

        def start_fn(on_line, on_complete):
            brew_interface.install_formula("git", on_line, on_complete)

        dlg = ProgressDialog(
            title="Installing git",
            start_fn=start_fn,
            parent=main_window,
        )
        dlg.present()

    The dialog disables the *Close* button while the operation is running
    and re-enables it (with a success/failure indicator) when it finishes.
    """

    def __init__(
        self,
        title: str,
        start_fn: Callable[[Callable[[str], None], Callable[[int, str], None]], None],
        parent: Optional[Gtk.Window] = None,
        on_finished: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Create the dialog.

        Parameters
        ----------
        title:
            Human-readable operation name shown in the header.
        start_fn:
            Callable that accepts ``(on_line_cb, on_complete_cb)`` and begins
            the brew operation (must return immediately — the actual work runs
            in a daemon thread).
        parent:
            Transient parent window for correct positioning.
        on_finished:
            Optional callback invoked with the brew exit code after the dialog
            is closed; useful for triggering a refresh.
        """
        super().__init__()
        self.set_title(title)
        self.set_default_size(700, 480)
        self.set_modal(True)
        self.set_resizable(True)
        if parent:
            self.set_transient_for(parent)

        self._on_finished = on_finished
        self._returncode: int = -1
        self._pulse_source: Optional[int] = None

        # ── Layout ────────────────────────────────────────────────────────
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        # Header bar
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        title_label = Gtk.Label(label=title)
        title_label.add_css_class("heading")
        header.set_title_widget(title_label)
        root.append(header)

        # Progress bar
        self._progress = Gtk.ProgressBar()
        self._progress.set_margin_start(12)
        self._progress.set_margin_end(12)
        self._progress.set_margin_top(8)
        self._progress.set_margin_bottom(4)
        self._progress.set_pulse_step(0.05)
        root.append(self._progress)

        # Terminal output
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_margin_start(12)
        scrolled.set_margin_end(12)
        scrolled.set_margin_top(4)
        scrolled.set_margin_bottom(0)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._buffer = Gtk.TextBuffer()
        self._setup_text_tags()

        self._text_view = Gtk.TextView(buffer=self._buffer)
        self._text_view.set_editable(False)
        self._text_view.set_cursor_visible(False)
        self._text_view.add_css_class("terminal-view")
        self._text_view.set_monospace(True)
        self._text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scrolled.set_child(self._text_view)
        root.append(scrolled)

        # Button row
        btn_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_start=12,
            margin_end=12,
            margin_top=8,
            margin_bottom=12,
            halign=Gtk.Align.END,
        )

        self._status_label = Gtk.Label(label="Running…")
        self._status_label.add_css_class("dim-label")
        self._status_label.set_hexpand(True)
        self._status_label.set_xalign(0.0)
        btn_row.append(self._status_label)

        self._close_btn = Gtk.Button(label="Close")
        self._close_btn.set_sensitive(False)
        self._close_btn.connect("clicked", self._on_close_clicked)
        btn_row.append(self._close_btn)

        root.append(btn_row)

        # ── Start pulsing progress bar ────────────────────────────────────
        self._pulse_source = GLib.timeout_add(80, self._pulse_progress)

        # ── Start the operation ───────────────────────────────────────────
        start_fn(self._on_line, self._on_complete)

    # ── Text tag setup ─────────────────────────────────────────────────────

    def _setup_text_tags(self) -> None:
        """Create colour tags for the terminal text buffer."""
        tag_table = self._buffer.get_tag_table()

        # Blue: "==>" section headers
        header_tag = Gtk.TextTag(name="header")
        header_tag.props.foreground = "#89b4fa"
        tag_table.add(header_tag)

        # Red: error lines
        error_tag = Gtk.TextTag(name="error")
        error_tag.props.foreground = "#f38ba8"
        tag_table.add(error_tag)

        # Green: success lines
        success_tag = Gtk.TextTag(name="success")
        success_tag.props.foreground = "#a6e3a1"
        tag_table.add(success_tag)

        # Yellow/orange: warning lines
        warn_tag = Gtk.TextTag(name="warning")
        warn_tag.props.foreground = "#f9e2af"
        tag_table.add(warn_tag)

    def _tag_for_line(self, line: str) -> Optional[str]:
        """Return the tag name to apply to *line*, or ``None`` for plain text."""
        stripped = line.strip().lower()
        if line.startswith("==>"):
            return "header"
        if any(
            stripped.startswith(p)
            for p in ("error:", "error ", "curl: (", "fatal:")
        ):
            return "error"
        if any(
            kw in stripped
            for kw in ("warning:", "caution:")
        ):
            return "warning"
        if any(
            kw in stripped
            for kw in ("successfully installed", "already installed",
                       "complete", "finished", " installed")
        ):
            return "success"
        return None

    # ── Callbacks (always called on GTK main thread via idle_add) ──────────

    def _on_line(self, line: str) -> None:
        """Append *line* to the terminal view with appropriate colouring."""
        end_iter = self._buffer.get_end_iter()
        tag_name = self._tag_for_line(line)
        if tag_name:
            self._buffer.insert_with_tags_by_name(end_iter, line, tag_name)
        else:
            self._buffer.insert(end_iter, line)

        # Auto-scroll to bottom
        adj = self._text_view.get_vadjustment()
        if adj:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def _on_complete(self, returncode: int, _full_output: str) -> None:
        """Called when the brew process exits."""
        self._returncode = returncode

        # Stop pulsing
        if self._pulse_source is not None:
            GLib.source_remove(self._pulse_source)
            self._pulse_source = None

        if returncode == 0:
            self._progress.set_fraction(1.0)
            self._status_label.set_text("Completed successfully")
            self._status_label.remove_css_class("error")
        else:
            self._progress.set_fraction(0.0)
            self._status_label.set_text(f"Failed (exit code {returncode})")
            self._status_label.add_css_class("error")

        self._close_btn.set_sensitive(True)
        self._close_btn.grab_focus()

    def _on_close_clicked(self, _btn: Gtk.Button) -> None:
        self.close()
        if self._on_finished is not None:
            self._on_finished(self._returncode)

    # ── Progress pulse ────────────────────────────────────────────────────

    def _pulse_progress(self) -> bool:
        """Pulse the progress bar; called by a GLib timeout."""
        self._progress.pulse()
        return GLib.SOURCE_CONTINUE

    # ── Cleanup ───────────────────────────────────────────────────────────

    def do_close_request(self) -> bool:
        """Stop the pulse timer when the window is closed."""
        if self._pulse_source is not None:
            GLib.source_remove(self._pulse_source)
            self._pulse_source = None
        return False  # Allow default close
