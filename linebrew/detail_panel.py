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

"""Formula detail panel — right pane showing formula info and action buttons."""

from __future__ import annotations

from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk


class DetailPanel(Gtk.ScrolledWindow):
    """Scrollable right pane showing info and actions for the selected formula.

    Emits signals when the user requests an action so the parent window can
    open the appropriate :class:`~linebrew.progress_dialog.ProgressDialog`.
    """

    __gsignals__ = {
        "install-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "uninstall-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "upgrade-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "pin-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "unpin-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self) -> None:
        """Build the detail panel widget tree."""
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_min_content_width(280)

        self._formula_name: Optional[str] = None
        self._info: Optional[dict] = None

        # Outer clamp keeps content readable at wide window sizes
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(16)
        self.set_child(clamp)

        self._root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        clamp.set_child(self._root_box)

        # ── Empty / loading states ────────────────────────────────────────
        self._empty_page = Adw.StatusPage()
        self._empty_page.set_icon_name("package-x-generic-symbolic")
        self._empty_page.set_title("No Formula Selected")
        self._empty_page.set_description("Select a formula from the list to see details.")
        self._root_box.append(self._empty_page)

        self._spinner_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            vexpand=True,
        )
        spinner = Gtk.Spinner()
        spinner.set_size_request(32, 32)
        spinner.start()
        self._spinner_box.append(spinner)
        load_lbl = Gtk.Label(label="Loading…")
        load_lbl.add_css_class("dim-label")
        self._spinner_box.append(load_lbl)
        self._spinner_box.set_visible(False)
        self._root_box.append(self._spinner_box)

        # ── Detail content (hidden until info is loaded) ───────────────────
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._content_box.set_visible(False)
        self._root_box.append(self._content_box)

        self._build_content_widgets()

    def _build_content_widgets(self) -> None:
        """Pre-build all content widgets once; update them when info arrives."""
        box = self._content_box

        # Name + version header
        self._name_label = Gtk.Label(xalign=0.0)
        self._name_label.add_css_class("formula-title")
        self._name_label.set_wrap(True)
        box.append(self._name_label)

        self._version_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._version_label = Gtk.Label(xalign=0.0)
        self._version_label.add_css_class("dim-label")
        self._version_box.append(self._version_label)
        self._installed_badge = Gtk.Label()
        self._installed_badge.add_css_class("status-badge")
        self._version_box.append(self._installed_badge)
        self._outdated_badge = Gtk.Label()
        self._outdated_badge.add_css_class("status-badge")
        self._version_box.append(self._outdated_badge)
        self._pinned_badge = Gtk.Label()
        self._pinned_badge.add_css_class("status-badge")
        self._version_box.append(self._pinned_badge)
        box.append(self._version_box)

        # Description
        self._desc_label = Gtk.Label(xalign=0.0)
        self._desc_label.set_wrap(True)
        self._desc_label.add_css_class("formula-description")
        box.append(self._desc_label)

        # Separator
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Metadata group
        meta_group = Adw.PreferencesGroup()
        meta_group.set_title("Details")

        self._homepage_row = Adw.ActionRow()
        self._homepage_row.set_title("Homepage")
        self._homepage_btn = Gtk.LinkButton()
        self._homepage_btn.set_valign(Gtk.Align.CENTER)
        self._homepage_row.add_suffix(self._homepage_btn)
        meta_group.add(self._homepage_row)

        self._license_row = Adw.ActionRow()
        self._license_row.set_title("License")
        self._license_val = Gtk.Label()
        self._license_val.add_css_class("dim-label")
        self._license_val.set_valign(Gtk.Align.CENTER)
        self._license_row.add_suffix(self._license_val)
        meta_group.add(self._license_row)

        self._tap_row = Adw.ActionRow()
        self._tap_row.set_title("Tap")
        self._tap_val = Gtk.Label()
        self._tap_val.add_css_class("dim-label")
        self._tap_val.set_valign(Gtk.Align.CENTER)
        self._tap_row.add_suffix(self._tap_val)
        meta_group.add(self._tap_row)

        box.append(meta_group)

        # Dependencies
        self._deps_group = Adw.PreferencesGroup()
        self._deps_group.set_title("Dependencies")
        self._deps_label = Gtk.Label(xalign=0.0)
        self._deps_label.set_wrap(True)
        self._deps_label.add_css_class("dim-label")
        self._deps_label.set_margin_start(12)
        self._deps_label.set_margin_end(12)
        self._deps_label.set_margin_top(4)
        self._deps_label.set_margin_bottom(4)
        self._deps_group.add(self._deps_label)
        box.append(self._deps_group)

        # Caveats
        self._caveats_group = Adw.PreferencesGroup()
        self._caveats_group.set_title("Caveats")
        self._caveats_label = Gtk.Label(xalign=0.0)
        self._caveats_label.set_wrap(True)
        self._caveats_label.add_css_class("caveat-box")
        self._caveats_label.set_selectable(True)
        self._caveats_label.set_margin_start(4)
        self._caveats_label.set_margin_end(4)
        self._caveats_label.set_margin_top(4)
        self._caveats_label.set_margin_bottom(4)
        self._caveats_group.add(self._caveats_label)
        box.append(self._caveats_group)

        # ── Action buttons ────────────────────────────────────────────────
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self._actions_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=4, margin_bottom=8,
        )
        box.append(self._actions_box)

        self._install_btn = Gtk.Button(label="Install")
        self._install_btn.add_css_class("suggested-action")
        self._install_btn.add_css_class("pill")
        self._install_btn.connect("clicked", lambda _: self._emit_action("install-requested"))
        self._actions_box.append(self._install_btn)

        self._upgrade_btn = Gtk.Button(label="Upgrade")
        self._upgrade_btn.add_css_class("suggested-action")
        self._upgrade_btn.add_css_class("pill")
        self._upgrade_btn.connect("clicked", lambda _: self._emit_action("upgrade-requested"))
        self._actions_box.append(self._upgrade_btn)

        self._uninstall_btn = Gtk.Button(label="Uninstall")
        self._uninstall_btn.add_css_class("destructive-action")
        self._uninstall_btn.add_css_class("pill")
        self._uninstall_btn.connect("clicked", lambda _: self._emit_action("uninstall-requested"))
        self._actions_box.append(self._uninstall_btn)

        self._pin_btn = Gtk.Button(label="Pin")
        self._pin_btn.add_css_class("pill")
        self._pin_btn.connect("clicked", lambda _: self._emit_action("pin-requested"))
        self._actions_box.append(self._pin_btn)

        self._unpin_btn = Gtk.Button(label="Unpin")
        self._unpin_btn.add_css_class("pill")
        self._unpin_btn.connect("clicked", lambda _: self._emit_action("unpin-requested"))
        self._actions_box.append(self._unpin_btn)

    # ── Public API ─────────────────────────────────────────────────────────

    def show_empty(self) -> None:
        """Reset the panel to the empty/no-selection state."""
        self._formula_name = None
        self._info = None
        self._empty_page.set_visible(True)
        self._spinner_box.set_visible(False)
        self._content_box.set_visible(False)

    def show_loading(self, name: str) -> None:
        """Show a spinner while formula info is being fetched."""
        self._formula_name = name
        self._empty_page.set_visible(False)
        self._spinner_box.set_visible(True)
        self._content_box.set_visible(False)

    def show_formula(self, info: Optional[dict], name: str = "") -> None:
        """Populate the panel with *info* from ``brew info --json=v1``.

        Parameters
        ----------
        info:
            Parsed JSON dict for the formula, or ``None`` on failure.
        name:
            Formula name used as fallback if *info* is ``None``.
        """
        self._spinner_box.set_visible(False)
        self._empty_page.set_visible(False)

        if info is None:
            self._empty_page.set_title("Information Unavailable")
            self._empty_page.set_description(
                f"Could not fetch details for \"{name}\"."
            )
            self._empty_page.set_visible(True)
            return

        self._info = info
        formula_name = info.get("name") or name
        self._formula_name = formula_name

        # Name
        self._name_label.set_text(formula_name)

        # Versions
        versions = info.get("versions", {})
        stable = versions.get("stable", "")
        installed_list: list[dict] = info.get("installed", [])
        installed_ver = installed_list[0].get("version", "") if installed_list else ""
        is_installed = bool(installed_list)
        is_outdated = info.get("outdated", False)
        is_pinned = info.get("pinned", False)

        ver_parts = []
        if installed_ver:
            ver_parts.append(f"Installed: {installed_ver}")
        if stable and stable != installed_ver:
            ver_parts.append(f"Latest: {stable}")
        self._version_label.set_text("  ".join(ver_parts))

        # Badges
        self._installed_badge.set_visible(is_installed and not is_outdated and not is_pinned)
        self._installed_badge.set_text("Installed")
        self._installed_badge.add_css_class("badge-installed")

        self._outdated_badge.set_visible(is_outdated)
        self._outdated_badge.set_text("Outdated")
        for c in ("badge-installed", "badge-pinned"):
            self._outdated_badge.remove_css_class(c)
        self._outdated_badge.add_css_class("badge-outdated")

        self._pinned_badge.set_visible(is_pinned)
        self._pinned_badge.set_text("Pinned")
        for c in ("badge-installed", "badge-outdated"):
            self._pinned_badge.remove_css_class(c)
        self._pinned_badge.add_css_class("badge-pinned")

        # Description
        self._desc_label.set_text(info.get("desc") or "")

        # Homepage
        homepage = info.get("homepage") or ""
        if homepage:
            self._homepage_btn.set_label(homepage)
            self._homepage_btn.set_uri(homepage)
            self._homepage_row.set_visible(True)
        else:
            self._homepage_row.set_visible(False)

        # License
        license_val = info.get("license") or "—"
        self._license_val.set_text(license_val)

        # Tap
        tap = info.get("tap") or info.get("full_name", "").rsplit("/", 1)[0]
        self._tap_val.set_text(tap or "—")

        # Dependencies
        deps: list[str] = info.get("dependencies", [])
        if deps:
            self._deps_label.set_text(", ".join(deps))
            self._deps_group.set_visible(True)
        else:
            self._deps_group.set_visible(False)

        # Caveats
        caveats = info.get("caveats") or ""
        if caveats.strip():
            self._caveats_label.set_text(caveats.strip())
            self._caveats_group.set_visible(True)
        else:
            self._caveats_group.set_visible(False)

        # Action buttons
        self._install_btn.set_visible(not is_installed)
        self._upgrade_btn.set_visible(is_installed and is_outdated)
        self._uninstall_btn.set_visible(is_installed)
        self._pin_btn.set_visible(is_installed and not is_pinned)
        self._unpin_btn.set_visible(is_pinned)

        self._content_box.set_visible(True)

    def get_formula_name(self) -> Optional[str]:
        """Return the currently displayed formula name, or ``None``."""
        return self._formula_name

    # ── Internal helpers ───────────────────────────────────────────────────

    def _emit_action(self, signal_name: str) -> None:
        """Emit one of the action signals with the current formula name."""
        if self._formula_name:
            self.emit(signal_name, self._formula_name)
