"""Define commands at the application level."""

import logging

from prompt_toolkit.filters import buffer_has_focus

from euporie.app.current import get_tui_app as get_app
from euporie.commands.registry import add
from euporie.filters import tab_has_focus

log = logging.getLogger(__name__)


@add(
    keys="c-n",
    group="File",
)
def new_notebook() -> "None":
    """Create a new file."""
    get_app().ask_new_file()


@add(
    keys="c-o",
    group="File",
)
def open_file() -> "None":
    """Open a file."""
    get_app().ask_open_file()


@add(
    keys="c-w",
    filter=tab_has_focus,
    group="File",
)
def close_file() -> None:
    """Close the current file."""
    get_app().close_tab()


@add(
    keys="c-q",
    name="quit",
    group="File",
)
def quit() -> "None":
    """Quit euporie."""
    get_app().exit()


@add(
    keys="c-pageup",
    filter=tab_has_focus,
    group="App",
)
def next_tab() -> "None":
    """Switch to the next tab."""
    get_app().tab_idx += 1


@add(
    keys="c-pagedown",
    filter=tab_has_focus,
    group="App",
)
def previous_tab() -> "None":
    """Switch to the previous tab."""
    get_app().tab_idx -= 1


@add(
    keys="tab",
    group="App",
    filter=~buffer_has_focus,
)
@add(
    keys="tab",
    group="App",
    filter=~buffer_has_focus,
)
def focus_next() -> "None":
    """Focus the next control."""
    get_app().layout.focus_next()


@add(
    keys="s-tab",
    group="App",
    filter=~buffer_has_focus,
)
def focus_previous() -> "None":
    """Focus the previous control."""
    get_app().layout.focus_previous()


@add(group="help")
def keyboard_shortcuts() -> "None":
    """Show the currently bound keyboard shortcuts."""
    get_app().help_keys()


@add(group="help")
def view_logs() -> "None":
    """Open the logs in a new tab."""
    get_app().help_logs()


@add(group="help")
def about() -> "None":
    """Show the about dialog."""
    get_app().help_about()