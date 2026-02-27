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

"""Formula list widget — Gtk.ColumnView with virtualised rendering.

Uses :class:`Gio.ListStore` + :class:`Gtk.FilterListModel` +
:class:`Gtk.SortListModel` so only visible rows are rendered even when
displaying the full ~7 000-item ``brew formulae`` list.
"""

from __future__ import annotations

from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class FormulaItem(GObject.GObject):
    """GObject wrapper for a single formula entry used in the list store."""

    __gtype_name__ = "LinebrewFormulaItem"

    def __init__(
        self,
        name: str,
        version: str = "",
        latest_version: str = "",
        status: str = "available",
    ) -> None:
        """Initialise a formula item.

        Parameters
        ----------
        name:
            Formula name, e.g. ``"git"``.
        version:
            Currently installed version (empty string if not installed).
        latest_version:
            Latest available version (used for outdated display).
        status:
            One of ``"installed"``, ``"outdated"``, ``"pinned"``,
            ``"available"``, or ``"tap"``.
        """
        super().__init__()
        self.name: str = name
        self.version: str = version
        self.latest_version: str = latest_version
        self.status: str = status


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class FormulaListView(Gtk.Box):
    """A filterable, sortable, virtualised list of Homebrew formulae.

    Emits the ``"formula-selected"`` signal with the selected
    :class:`FormulaItem` when the user clicks a row.
    """

    __gsignals__ = {
        "formula-selected": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (object,),
        ),
    }

    def __init__(self) -> None:
        """Build the widget hierarchy."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        # ── Search bar ────────────────────────────────────────────────────
        self._search_bar = Gtk.SearchBar()
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search formulae…")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_bar.set_child(self._search_entry)
        self._search_bar.set_show_close_button(False)
        self.append(self._search_bar)

        # ── Data models ───────────────────────────────────────────────────
        self._store: Gio.ListStore = Gio.ListStore(item_type=FormulaItem)
        self._search_text: str = ""

        self._filter = Gtk.CustomFilter.new(self._filter_func, None)
        self._filter_model = Gtk.FilterListModel(
            model=self._store, filter=self._filter
        )

        self._sorter = Gtk.CustomSorter.new(self._sort_func, None)
        self._sort_model = Gtk.SortListModel(
            model=self._filter_model, sorter=self._sorter
        )

        self._selection = Gtk.SingleSelection(model=self._sort_model)
        self._selection.connect("selection-changed", self._on_selection_changed)

        # ── Column view ───────────────────────────────────────────────────
        self._column_view = Gtk.ColumnView(model=self._selection)
        self._column_view.set_show_row_separators(True)
        self._column_view.set_vexpand(True)
        self._column_view.add_css_class("data-table")
        self._setup_columns()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(self._column_view)
        self.append(scrolled)

        # ── Empty state ───────────────────────────────────────────────────
        self._empty_page = Adw.StatusPage()
        self._empty_page.set_icon_name("system-search-symbolic")
        self._empty_page.set_title("No Formulae Found")
        self._empty_page.set_description("Try a different search term.")
        self._empty_page.set_vexpand(True)
        self._empty_page.set_visible(False)
        self.append(self._empty_page)

    # ── Column setup ──────────────────────────────────────────────────────

    def _setup_columns(self) -> None:
        """Create the Name, Installed, and Status columns."""

        # Name
        name_factory = Gtk.SignalListItemFactory()
        name_factory.connect("setup", self._setup_name_cell)
        name_factory.connect("bind", self._bind_name_cell)
        name_col = Gtk.ColumnViewColumn(title="Name", factory=name_factory)
        name_col.set_expand(True)
        self._column_view.append_column(name_col)

        # Installed version
        ver_factory = Gtk.SignalListItemFactory()
        ver_factory.connect("setup", self._setup_ver_cell)
        ver_factory.connect("bind", self._bind_ver_cell)
        ver_col = Gtk.ColumnViewColumn(title="Installed", factory=ver_factory)
        ver_col.set_fixed_width(110)
        self._column_view.append_column(ver_col)

        # Latest version
        latest_factory = Gtk.SignalListItemFactory()
        latest_factory.connect("setup", self._setup_latest_cell)
        latest_factory.connect("bind", self._bind_latest_cell)
        latest_col = Gtk.ColumnViewColumn(title="Latest", factory=latest_factory)
        latest_col.set_fixed_width(110)
        self._column_view.append_column(latest_col)

        # Status badge
        status_factory = Gtk.SignalListItemFactory()
        status_factory.connect("setup", self._setup_status_cell)
        status_factory.connect("bind", self._bind_status_cell)
        status_col = Gtk.ColumnViewColumn(title="Status", factory=status_factory)
        status_col.set_fixed_width(100)
        self._column_view.append_column(status_col)

    # Name column
    def _setup_name_cell(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        label = Gtk.Label(xalign=0, margin_start=6, margin_end=6,
                          margin_top=4, margin_bottom=4)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        list_item.set_child(label)

    def _bind_name_cell(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        item: FormulaItem = list_item.get_item()
        label: Gtk.Label = list_item.get_child()
        label.set_text(item.name)

    # Installed version column
    def _setup_ver_cell(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        label = Gtk.Label(xalign=0, margin_start=6, margin_end=6,
                          margin_top=4, margin_bottom=4)
        label.add_css_class("dim-label")
        list_item.set_child(label)

    def _bind_ver_cell(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        item: FormulaItem = list_item.get_item()
        label: Gtk.Label = list_item.get_child()
        label.set_text("Yes" if item.status in ("installed", "outdated", "pinned") else "No")

    # Latest version column
    def _setup_latest_cell(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        label = Gtk.Label(xalign=0, margin_start=6, margin_end=6,
                          margin_top=4, margin_bottom=4)
        label.add_css_class("dim-label")
        list_item.set_child(label)

    def _bind_latest_cell(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        item: FormulaItem = list_item.get_item()
        label: Gtk.Label = list_item.get_child()
        if item.status == "available":
            label.set_text("—")
        elif item.status == "outdated":
            label.set_text("No")
        else:
            label.set_text("Yes")

    # Status badge column
    def _setup_status_cell(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        badge = Gtk.Label(margin_start=6, margin_end=6, margin_top=4, margin_bottom=4)
        badge.add_css_class("status-badge")
        list_item.set_child(badge)

    def _bind_status_cell(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        item: FormulaItem = list_item.get_item()
        badge: Gtk.Label = list_item.get_child()

        status_map = {
            "installed": ("Installed", "badge-installed"),
            "outdated": ("Outdated", "badge-outdated"),
            "pinned": ("Pinned", "badge-pinned"),
            "available": ("Not Installed", "badge-not-installed"),
            "tap": ("", ""),
        }
        text, css_class = status_map.get(item.status, ("", ""))
        badge.set_text(text)
        for cls in ("badge-installed", "badge-outdated", "badge-pinned", "badge-not-installed"):
            badge.remove_css_class(cls)
        if css_class:
            badge.add_css_class(css_class)

    # ── Filter / sort callbacks ────────────────────────────────────────────

    def _filter_func(self, item: FormulaItem, _user_data: object) -> bool:
        """Return True if the item matches the current search text."""
        if not self._search_text:
            return True
        needle = self._search_text.lower()
        return needle in item.name.lower()

    def _sort_func(self, a: FormulaItem, b: FormulaItem, _user_data: object) -> int:
        """Sort formulae alphabetically by name."""
        if a.name < b.name:
            return -1
        if a.name > b.name:
            return 1
        return 0

    # ── Signal handlers ───────────────────────────────────────────────────

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_text = entry.get_text().strip()
        self._filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_empty_state()

    def _on_selection_changed(
        self,
        selection: Gtk.SingleSelection,
        position: int,
        n_items: int,
    ) -> None:
        item = selection.get_selected_item()
        if item is not None:
            self.emit("formula-selected", item)

    # ── Public API ────────────────────────────────────────────────────────

    def set_formulae(self, formulae: list[dict]) -> None:
        """Replace the current list with *formulae*.

        Parameters
        ----------
        formulae:
            List of dicts with keys ``name``, ``version`` (optional),
            ``latest_version`` (optional), ``status`` (optional).
        """
        items = [
            FormulaItem(
                name=f["name"],
                version=f.get("version", ""),
                latest_version=f.get("latest_version", ""),
                status=f.get("status", "available"),
            )
            for f in formulae
        ]
        # Use splice for bulk replace — much faster than remove_all + append loop
        self._store.splice(0, self._store.get_n_items(), items)
        self._update_empty_state()

    def merge_status(
        self,
        installed: dict[str, str],
        outdated: set[str],
        pinned: set[str],
    ) -> None:
        """Update the ``status`` and ``version`` fields without rebuilding the list.

        Parameters
        ----------
        installed:
            Mapping of formula name → installed version.
        outdated:
            Set of formula names that are outdated.
        pinned:
            Set of formula names that are pinned.
        """
        n = self._store.get_n_items()
        for i in range(n):
            item: FormulaItem = self._store.get_item(i)
            if item.name in outdated:
                item.status = "outdated"
                item.version = installed.get(item.name, "")
            elif item.name in pinned:
                item.status = "pinned"
                item.version = installed.get(item.name, "")
            elif item.name in installed:
                item.status = "installed"
                item.version = installed[item.name]
            else:
                item.status = "available"
                item.version = ""

    def focus_search(self) -> None:
        """Focus the search entry."""
        self._search_bar.set_search_mode(True)
        self._search_entry.grab_focus()

    def set_search_mode(self, active: bool) -> None:
        """Show or hide the search bar."""
        self._search_bar.set_search_mode(active)
        if active:
            self._search_entry.grab_focus()

    def get_item_count(self) -> int:
        """Return the total number of items in the backing store."""
        return self._store.get_n_items()

    def get_filtered_count(self) -> int:
        """Return the number of items visible after filtering."""
        return self._filter_model.get_n_items()

    def clear_search(self) -> None:
        """Clear the search entry and reset the filter."""
        self._search_entry.set_text("")
        self._search_text = ""
        self._filter.changed(Gtk.FilterChange.LESS_STRICT)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _update_empty_state(self) -> None:
        has_items = self._filter_model.get_n_items() > 0 or self._store.get_n_items() == 0
        # Show empty state only when the store has items but filter returns none
        show_empty = (
            self._store.get_n_items() > 0
            and self._filter_model.get_n_items() == 0
        )
        self._empty_page.set_visible(show_empty)
        self._column_view.set_visible(not show_empty)
