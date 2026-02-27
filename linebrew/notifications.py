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

"""Desktop notification helper for Linebrew.

Sends GLib/desktop notifications when long-running brew operations complete.
Falls back silently if notifications are not available.
"""

from __future__ import annotations

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib


def send_notification(
    app: "Gio.Application",
    title: str,
    body: str,
    success: bool = True,
) -> None:
    """Send a desktop notification via GLib.

    Parameters
    ----------
    app:
        The :class:`Gio.Application` instance (needed for
        :meth:`Gio.Application.send_notification`).
    title:
        Notification title, e.g. ``"Install complete"``.
    body:
        Notification body text.
    success:
        When ``True`` use an info icon; when ``False`` use an error icon.
    """
    try:
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        icon_name = "dialog-information" if success else "dialog-error"
        icon = Gio.ThemedIcon.new(icon_name)
        notification.set_icon(icon)
        app.send_notification("linebrew-op", notification)
    except Exception:
        # Notifications are best-effort; never crash the main app.
        pass
