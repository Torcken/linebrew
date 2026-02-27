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

"""Main application window for Linebrew.

Three-pane layout:
  Left   — category sidebar (Installed, Outdated, All, Leaves, Pinned, Taps)
  Centre — filterable/sortable formula list
  Right  — formula detail pane with action buttons

All brew operations open a :class:`~linebrew.progress_dialog.ProgressDialog`
that streams live output.  After any mutating operation the affected category
cache is invalidated and the list refreshed.
"""

from __future__ import annotations

from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from linebrew import brew_interface
from linebrew.detail_panel import DetailPanel
from linebrew.formula_list import FormulaItem, FormulaListView
from linebrew.notifications import send_notification
from linebrew.preferences_dialog import PreferencesDialog, apply_color_scheme, load_prefs
from linebrew.progress_dialog import ProgressDialog


# ---------------------------------------------------------------------------
# Sidebar category constants
# ---------------------------------------------------------------------------

CATEGORY_INSTALLED = "installed"
CATEGORY_OUTDATED = "outdated"
CATEGORY_ALL = "all"
CATEGORY_LEAVES = "leaves"
CATEGORY_PINNED = "pinned"
CATEGORY_TAPS = "taps"

_SIDEBAR_ITEMS = [
    (CATEGORY_INSTALLED, "Installed", "drive-harddisk-symbolic"),
    (CATEGORY_OUTDATED, "Outdated", "software-update-available-symbolic"),
    (CATEGORY_ALL, "All Formulae", "system-search-symbolic"),
    (CATEGORY_LEAVES, "Leaves", "emblem-ok-symbolic"),
    (CATEGORY_PINNED, "Pinned", "view-pin-symbolic"),
    (CATEGORY_TAPS, "Taps", "network-server-symbolic"),
]


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(Adw.ApplicationWindow):
    """Linebrew primary window."""

    def __init__(self, **kwargs: object) -> None:
        """Initialise the window."""
        super().__init__(**kwargs)
        self.set_title("Linebrew")
        self.set_default_size(1100, 700)
        self.set_icon_name("io.github.linebrew.Linebrew")

        # Category → cached list[dict]
        self._cache: dict[str, list[dict]] = {}
        self._current_category: str = CATEGORY_INSTALLED
        self._loading = False

        # Sidebar row widgets for badge updates
        self._sidebar_rows: dict[str, Gtk.ListBoxRow] = {}
        self._sidebar_badges: dict[str, Gtk.Label] = {}

        prefs = load_prefs()
        apply_color_scheme(prefs.get("color_scheme", "system"))

        self._build_ui()
        self._setup_actions()
        self._setup_keyboard_shortcuts()

        # ── Auto-launch behaviour ──────────────────────────────────────────
        if prefs.get("show_all_on_startup"):
            GLib.idle_add(lambda: self._select_category(CATEGORY_ALL) or False)
        else:
            GLib.idle_add(lambda: self._select_category(CATEGORY_INSTALLED) or False)

        if prefs.get("update_on_launch"):
            GLib.idle_add(lambda: self._run_update() or False)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the full widget hierarchy."""
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)

        # Header bar
        self._header = Adw.HeaderBar()
        self._build_header(self._header)
        root_box.append(self._header)

        # Homebrew not-found banner
        self._brew_banner = Adw.Banner()
        self._brew_banner.set_title(
            "Homebrew not found. Add /home/linuxbrew/.linuxbrew/bin to PATH."
        )
        self._brew_banner.set_button_label("Get Homebrew")
        self._brew_banner.connect("button-clicked", self._on_brew_banner_clicked)
        self._brew_banner.set_revealed(False)
        root_box.append(self._brew_banner)

        # Check for brew
        if brew_interface.find_brew() is None:
            self._brew_banner.set_revealed(True)

        # Three-pane layout using nested Gtk.Paned
        main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_paned.set_vexpand(True)
        root_box.append(main_paned)

        # Left: sidebar
        sidebar_box = self._build_sidebar()
        main_paned.set_start_child(sidebar_box)
        main_paned.set_shrink_start_child(False)
        main_paned.set_resize_start_child(False)
        main_paned.set_position(220)

        # Centre + right paned
        content_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_paned.set_end_child(content_paned)
        main_paned.set_shrink_end_child(False)

        # Centre: formula list
        self._formula_list = FormulaListView()
        self._formula_list.set_size_request(280, -1)
        self._formula_list.connect("formula-selected", self._on_formula_selected)
        content_paned.set_start_child(self._formula_list)
        content_paned.set_shrink_start_child(False)
        content_paned.set_resize_start_child(True)
        content_paned.set_position(380)

        # Right: detail panel
        self._detail_panel = DetailPanel()
        self._detail_panel.connect("install-requested", self._on_install_requested)
        self._detail_panel.connect("uninstall-requested", self._on_uninstall_requested)
        self._detail_panel.connect("upgrade-requested", self._on_upgrade_requested)
        self._detail_panel.connect("pin-requested", self._on_pin_requested)
        self._detail_panel.connect("unpin-requested", self._on_unpin_requested)
        content_paned.set_end_child(self._detail_panel)
        content_paned.set_shrink_end_child(False)
        content_paned.set_resize_end_child(True)

        # Loading overlay label
        self._loading_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            vexpand=True,
        )
        self._loading_spinner = Gtk.Spinner()
        self._loading_spinner.set_size_request(32, 32)
        self._loading_spinner.start()
        self._loading_box.append(self._loading_spinner)
        lbl = Gtk.Label(label="Loading…")
        lbl.add_css_class("dim-label")
        self._loading_box.append(lbl)
        self._loading_box.set_visible(False)
        # Insert after search bar in formula list
        self._formula_list.prepend(self._loading_box)

    def _build_header(self, header: Adw.HeaderBar) -> None:
        """Populate the header bar with buttons and title."""
        # Left side buttons
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_tooltip_text("Menu")
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("Keyboard Shortcuts", "app.shortcuts")
        menu.append("About Linebrew", "app.about")
        menu_btn.set_menu_model(menu)
        header.pack_start(menu_btn)

        # Right side buttons
        search_btn = Gtk.ToggleButton()
        search_btn.set_icon_name("system-search-symbolic")
        search_btn.set_tooltip_text("Search (Ctrl+F)")
        search_btn.connect("toggled", self._on_search_toggled)
        self._search_toggle_btn = search_btn
        header.pack_end(search_btn)

        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh (Ctrl+R)")
        refresh_btn.connect("clicked", lambda _: self._refresh_current_category())
        header.pack_end(refresh_btn)

        # Title with category name
        self._title_widget = Adw.WindowTitle()
        self._title_widget.set_title("Linebrew")
        self._title_widget.set_subtitle("Installed")
        header.set_title_widget(self._title_widget)

        # Sidebar action buttons (inside header on left)
        update_btn = Gtk.Button(label="Update")
        update_btn.set_icon_name("software-update-available-symbolic")
        update_btn.set_tooltip_text("brew update (Ctrl+U)")
        update_btn.connect("clicked", lambda _: self._run_update())
        header.pack_start(update_btn)

    def _build_sidebar(self) -> Gtk.Box:
        """Build the left navigation sidebar."""
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(200, -1)

        # Navigation list
        self._sidebar_list = Gtk.ListBox()
        self._sidebar_list.add_css_class("navigation-sidebar")
        self._sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._sidebar_list.set_vexpand(True)
        self._sidebar_list.connect("row-selected", self._on_sidebar_row_selected)

        for cat_id, label, icon in _SIDEBAR_ITEMS:
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=10,
                margin_start=12,
                margin_end=8,
                margin_top=8,
                margin_bottom=8,
            )
            img = Gtk.Image.new_from_icon_name(icon)
            img.set_pixel_size(16)
            row_box.append(img)
            lbl = Gtk.Label(label=label, xalign=0.0, hexpand=True)
            row_box.append(lbl)
            badge = Gtk.Label(label="")
            badge.add_css_class("sidebar-count-badge")
            badge.set_visible(False)
            row_box.append(badge)
            row.set_child(row_box)
            row.set_name(cat_id)
            self._sidebar_list.append(row)
            self._sidebar_rows[cat_id] = row
            self._sidebar_badges[cat_id] = badge

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(self._sidebar_list)
        sidebar.append(scrolled)

        # Bottom action buttons
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sidebar.append(sep)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            margin_start=8,
            margin_end=8,
            margin_top=6,
            margin_bottom=6,
        )

        cleanup_btn = self._make_sidebar_action_btn(
            "Cleanup", "user-trash-symbolic", self._run_cleanup
        )
        actions.append(cleanup_btn)

        doctor_btn = self._make_sidebar_action_btn(
            "Doctor", "dialog-information-symbolic", self._run_doctor
        )
        actions.append(doctor_btn)

        upgrade_all_btn = self._make_sidebar_action_btn(
            "Upgrade All", "software-update-urgent-symbolic", self._run_upgrade_all
        )
        actions.append(upgrade_all_btn)

        tap_btn = self._make_sidebar_action_btn(
            "Add Tap…", "list-add-symbolic", self._show_add_tap_dialog
        )
        actions.append(tap_btn)

        sidebar.append(actions)
        return sidebar

    def _make_sidebar_action_btn(
        self, label: str, icon: str, callback: Callable
    ) -> Gtk.Button:
        """Create a flat button suitable for the sidebar action area."""
        btn = Gtk.Button()
        btn.add_css_class("flat")
        row_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_start=4,
            margin_end=4,
            margin_top=2,
            margin_bottom=2,
        )
        img = Gtk.Image.new_from_icon_name(icon)
        img.set_pixel_size(16)
        row_box.append(img)
        lbl = Gtk.Label(label=label, xalign=0.0)
        row_box.append(lbl)
        btn.set_child(row_box)
        btn.connect("clicked", lambda _: callback())
        return btn

    # ── Actions & keyboard shortcuts ───────────────────────────────────────

    def _setup_actions(self) -> None:
        """Register window-level actions."""
        actions = {
            "refresh": self._refresh_current_category,
            "focus-search": lambda: self._formula_list.focus_search(),
            "update": self._run_update,
            "cleanup": self._run_cleanup,
        }
        for name, fn in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, f=fn: f())
            self.add_action(action)

    def _setup_keyboard_shortcuts(self) -> None:
        """Register window keyboard shortcuts via Gtk.ShortcutController."""
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.MANAGED)

        def add_shortcut(trigger_str: str, action_str: str) -> None:
            trigger = Gtk.ShortcutTrigger.parse_string(trigger_str)
            action = Gtk.ShortcutAction.parse_string(action_str)
            if trigger and action:
                controller.add_shortcut(Gtk.Shortcut.new(trigger, action))

        add_shortcut("<Control>r", "action(win.refresh)")
        add_shortcut("F5", "action(win.refresh)")
        add_shortcut("<Control>f", "action(win.focus-search)")
        add_shortcut("<Control>u", "action(win.update)")
        add_shortcut("<Control><Shift>c", "action(win.cleanup)")
        self.add_controller(controller)

    # ── Category loading ───────────────────────────────────────────────────

    def _select_category(self, category: str) -> None:
        """Select *category* in the sidebar and load its formulae."""
        row = self._sidebar_rows.get(category)
        if row:
            self._sidebar_list.select_row(row)

    def _on_sidebar_row_selected(
        self, listbox: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]
    ) -> None:
        if row is None:
            return
        cat = row.get_name()
        self._current_category = cat
        subtitle_map = {k: v for k, v, _ in _SIDEBAR_ITEMS}
        self._title_widget.set_subtitle(subtitle_map.get(cat, ""))
        self._detail_panel.show_empty()
        self._load_category(cat)

    def _load_category(self, category: str, force: bool = False) -> None:
        """Load formulae for *category*, using cache if available."""
        if not force and category in self._cache:
            self._formula_list.set_formulae(self._cache[category])
            return

        self._show_loading(True)
        fetch_fn = {
            CATEGORY_INSTALLED: brew_interface.get_installed_formulae,
            CATEGORY_OUTDATED: brew_interface.get_outdated_formulae,
            CATEGORY_ALL: brew_interface.get_all_formulae,
            CATEGORY_LEAVES: brew_interface.get_leaves,
            CATEGORY_PINNED: brew_interface.get_pinned_formulae,
            CATEGORY_TAPS: brew_interface.get_taps,
        }.get(category)

        if fetch_fn is None:
            self._show_loading(False)
            return

        def _on_loaded(formulae: list[dict]) -> None:
            self._cache[category] = formulae
            self._formula_list.set_formulae(formulae)
            self._update_sidebar_badge(category, len(formulae))
            self._show_loading(False)

        fetch_fn(_on_loaded)

    def _refresh_current_category(self) -> None:
        """Invalidate cache and reload the current category."""
        self._cache.pop(self._current_category, None)
        self._load_category(self._current_category, force=True)

    def _invalidate_cache(self) -> None:
        """Clear the entire formula cache after a mutating operation."""
        self._cache.clear()

    def _show_loading(self, loading: bool) -> None:
        self._loading = loading
        self._loading_box.set_visible(loading)
        self._formula_list._column_view.set_sensitive(not loading)

    def _update_sidebar_badge(self, category: str, count: int) -> None:
        badge = self._sidebar_badges.get(category)
        if badge:
            badge.set_text(str(count))
            badge.set_visible(count > 0)

    # ── Formula selection ──────────────────────────────────────────────────

    def _on_formula_selected(
        self, _list_view: FormulaListView, item: FormulaItem
    ) -> None:
        """Fetch and display formula details when a row is selected."""
        self._detail_panel.show_loading(item.name)
        brew_interface.get_formula_info(item.name, self._on_formula_info_loaded)

    def _on_formula_info_loaded(self, info: Optional[dict]) -> None:
        name = self._detail_panel.get_formula_name() or ""
        self._detail_panel.show_formula(info, name)

    # ── Action button handlers ─────────────────────────────────────────────

    def _on_install_requested(self, _panel: DetailPanel, name: str) -> None:
        self._run_operation(
            title=f"Installing {name}",
            start_fn=lambda on_line, on_done: brew_interface.install_formula(
                name, on_line, on_done
            ),
            notification_title=f"Installed {name}",
            notification_body=f"{name} has been installed.",
        )

    def _on_uninstall_requested(self, _panel: DetailPanel, name: str) -> None:
        self._confirm_destructive(
            title=f"Uninstall {name}?",
            body=f"Are you sure you want to uninstall \"{name}\"?",
            confirm_label="Uninstall",
            on_confirm=lambda: self._run_operation(
                title=f"Uninstalling {name}",
                start_fn=lambda on_line, on_done: brew_interface.uninstall_formula(
                    name, on_line, on_done
                ),
                notification_title=f"Uninstalled {name}",
                notification_body=f"{name} has been uninstalled.",
            ),
        )

    def _on_upgrade_requested(self, _panel: DetailPanel, name: str) -> None:
        self._run_operation(
            title=f"Upgrading {name}",
            start_fn=lambda on_line, on_done: brew_interface.upgrade_formula(
                name, on_line, on_done
            ),
            notification_title=f"Upgraded {name}",
            notification_body=f"{name} has been upgraded.",
        )

    def _on_pin_requested(self, _panel: DetailPanel, name: str) -> None:
        self._run_operation(
            title=f"Pinning {name}",
            start_fn=lambda on_line, on_done: brew_interface.pin_formula(
                name, on_line, on_done
            ),
            notification_title=f"Pinned {name}",
            notification_body=f"{name} is now pinned.",
        )

    def _on_unpin_requested(self, _panel: DetailPanel, name: str) -> None:
        self._run_operation(
            title=f"Unpinning {name}",
            start_fn=lambda on_line, on_done: brew_interface.unpin_formula(
                name, on_line, on_done
            ),
            notification_title=f"Unpinned {name}",
            notification_body=f"{name} has been unpinned.",
        )

    # ── Sidebar operations ─────────────────────────────────────────────────

    def _run_update(self) -> None:
        self._run_operation(
            title="brew update",
            start_fn=lambda on_line, on_done: brew_interface.run_update(on_line, on_done),
            notification_title="Homebrew Updated",
            notification_body="brew update completed successfully.",
        )

    def _run_cleanup(self) -> None:
        self._run_operation(
            title="brew cleanup",
            start_fn=lambda on_line, on_done: brew_interface.run_cleanup(on_line, on_done),
            notification_title="Cleanup Complete",
            notification_body="brew cleanup completed successfully.",
        )

    def _run_doctor(self) -> None:
        self._run_operation(
            title="brew doctor",
            start_fn=lambda on_line, on_done: brew_interface.run_doctor(on_line, on_done),
            notification_title="Doctor Complete",
            notification_body="brew doctor finished.",
        )

    def _run_upgrade_all(self) -> None:
        self._run_operation(
            title="brew upgrade (all)",
            start_fn=lambda on_line, on_done: brew_interface.upgrade_all(on_line, on_done),
            notification_title="All Packages Upgraded",
            notification_body="brew upgrade completed.",
        )

    # ── Add tap dialog ─────────────────────────────────────────────────────

    def _show_add_tap_dialog(self) -> None:
        """Show an input dialog to add a new tap."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            modal=True,
            heading="Add Tap",
            body="Enter the tap name (e.g. homebrew/cask):",
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("user/repo")
        entry.set_activates_default(True)
        entry.set_margin_start(16)
        entry.set_margin_end(16)
        entry.set_margin_bottom(8)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("tap", "Add Tap")
        dialog.set_default_response("tap")
        dialog.set_response_appearance("tap", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect(
            "response",
            lambda d, resp: self._on_add_tap_response(d, resp, entry),
        )
        dialog.present()

    def _on_add_tap_response(
        self, dialog: Adw.MessageDialog, response: str, entry: Gtk.Entry
    ) -> None:
        dialog.destroy()
        if response != "tap":
            return
        repo = entry.get_text().strip()
        if not repo:
            return
        self._run_operation(
            title=f"Tapping {repo}",
            start_fn=lambda on_line, on_done: brew_interface.tap_repository(
                repo, on_line, on_done
            ),
            notification_title=f"Tapped {repo}",
            notification_body=f"{repo} has been tapped.",
        )

    def _show_untap_dialog(self, repo: str) -> None:
        """Confirm and execute brew untap."""
        self._confirm_destructive(
            title=f"Untap {repo}?",
            body=f"Remove the tap \"{repo}\"?",
            confirm_label="Untap",
            on_confirm=lambda: self._run_operation(
                title=f"Untapping {repo}",
                start_fn=lambda on_line, on_done: brew_interface.untap_repository(
                    repo, on_line, on_done
                ),
                notification_title=f"Untapped {repo}",
                notification_body=f"{repo} has been untapped.",
            ),
        )

    # ── Generic operation runner ───────────────────────────────────────────

    def _run_operation(
        self,
        title: str,
        start_fn: Callable,
        notification_title: str = "",
        notification_body: str = "",
    ) -> None:
        """Open a :class:`ProgressDialog` for a brew operation.

        Parameters
        ----------
        title:
            Title shown in the dialog header bar.
        start_fn:
            Callable accepting ``(on_line, on_complete)`` that starts the
            brew operation.  Must return immediately.
        notification_title / notification_body:
            Text used for the completion desktop notification.
        """

        def _on_finished(returncode: int) -> None:
            self._invalidate_cache()
            self._refresh_current_category()
            if notification_title:
                app = self.get_application()
                if app:
                    send_notification(
                        app,
                        notification_title,
                        notification_body,
                        success=(returncode == 0),
                    )

        dlg = ProgressDialog(
            title=title,
            start_fn=start_fn,
            parent=self,
            on_finished=_on_finished,
        )
        dlg.present()

    # ── Confirmation dialog ────────────────────────────────────────────────

    def _confirm_destructive(
        self,
        title: str,
        body: str,
        confirm_label: str,
        on_confirm: Callable,
    ) -> None:
        """Show a destructive-action confirmation dialog."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            modal=True,
            heading=title,
            body=body,
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("confirm", confirm_label)
        dialog.set_default_response("cancel")
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect(
            "response",
            lambda d, resp: (d.destroy(), on_confirm()) if resp == "confirm" else d.destroy(),
        )
        dialog.present()

    # ── Search toggle ──────────────────────────────────────────────────────

    def _on_search_toggled(self, btn: Gtk.ToggleButton) -> None:
        self._formula_list.set_search_mode(btn.get_active())

    # ── Homebrew not found banner ──────────────────────────────────────────

    def _on_brew_banner_clicked(self, _banner: Adw.Banner) -> None:
        Gtk.show_uri(self, "https://brew.sh", 0)
