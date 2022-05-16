"""Defines widget for defining layouts."""

import logging
from abc import ABCMeta, abstractmethod
from functools import partial
from typing import TYPE_CHECKING, NamedTuple

from prompt_toolkit.application.current import get_app
from prompt_toolkit.cache import SimpleCache
from prompt_toolkit.filters import Condition, to_filter
from prompt_toolkit.formatted_text.base import to_formatted_text
from prompt_toolkit.formatted_text.utils import fragment_list_width
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    DynamicContainer,
    HSplit,
    VSplit,
    Window,
    to_container,
)
from prompt_toolkit.layout.controls import (
    FormattedTextControl,
    GetLinePrefixCallable,
    UIContent,
    UIControl,
)
from prompt_toolkit.mouse_events import MouseEventType
from prompt_toolkit.utils import Event
from prompt_toolkit.widgets import Box

from euporie.border import InnerEdgeGridStyle, OuterEdgeGridStyle
from euporie.widgets.decor import Border, BorderVisibility

if TYPE_CHECKING:
    from typing import (
        Any,
        Callable,
        ClassVar,
        Dict,
        List,
        Optional,
        Sequence,
        Tuple,
        Union,
    )

    from prompt_toolkit.filters import FilterOrBool
    from prompt_toolkit.formatted_text.base import AnyFormattedText, StyleAndTextTuples
    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone
    from prompt_toolkit.layout.containers import AnyContainer, Container
    from prompt_toolkit.mouse_events import MouseEvent

log = logging.getLogger(__name__)


class ConditionalSplit:
    """A split container where the orientation depends on a filter."""

    def __init__(
        self, vertical: "FilterOrBool", *args: "Any", **kwargs: "Any"
    ) -> "None":
        """Creates a new conditional split container.

        Args:
            vertical: A filter which determines if the container should be displayed vertically
            args: Positional arguments to pass to the split container
            kwargs: Key-word arguments to pass to the split container

        """
        self.vertical = to_filter(vertical)
        self.args = args
        self.kwargs = kwargs
        self._cache: "SimpleCache" = SimpleCache(maxsize=2)

    def load_container(self, vertical):
        if vertical:
            return HSplit(*self.args, **self.kwargs)
        else:
            return VSplit(*self.args, **self.kwargs)

    def container(self):
        vertical = self.vertical()
        return self._cache.get(vertical, partial(self.load_container, vertical))

    def __pt_container__(self) -> "AnyContainer":
        return DynamicContainer(self.container)


class ReferencedSplit:
    def __init__(self, split, children, *args, **kwargs) -> "None":
        self.container = split([], *args, **kwargs)
        self.children = children

    @property
    def children(self):
        return [to_container(x) for x in self._children]

    @children.setter
    def children(self, children):
        self._children = children
        self.container.children = self.children

    def __pt_container__(self) -> "Container":
        return self.container


class Tab(NamedTuple):
    """A named tuple represting a tab and it's callbacks."""

    title: "AnyFormattedText"
    on_activate: "Callable"
    on_deactivate: "Optional[Callable]" = None
    on_close: "Optional[Callable]" = None


class TabControl(UIControl):
    """A control which shows a tab bar."""

    char_bottom = "▁"
    char_left = "▏"
    char_right = "▕"
    char_top = "▁"
    char_close = "✖"

    def __init__(
        self,
        tabs: "Tuple[Tab]",
        active: "int",
        spacing: "int" = 1,
        closeable: "bool" = False,
    ) -> "None":
        """Creates a new tab bar instance.

        Args:
            tabs: A list to tuples describing the tab title and the callback to run
                when the tab is activated.
            spacing: The number of characters between the tabs
            closable: Whether to show close buttons the the tabs

        """
        self.tabs = tabs
        self.spacing = spacing
        self.closeable = closeable
        self.active = active

        self.mouse_handlers: "Dict[int, Optional[Callable[..., Any]]]" = {}

        self._title_cache: SimpleCache = SimpleCache(maxsize=1)
        self._content_cache: SimpleCache = SimpleCache(maxsize=50)

    def preferred_width(self, max_available_width: "int") -> "Optional[int]":
        return max_available_width

    def preferred_height(
        self,
        width: "int",
        max_available_height: "int",
        wrap_lines: "bool",
        get_line_prefix: "Optional[GetLinePrefixCallable]",
    ) -> "Optional[int]":
        return 2

    def is_focusable(self) -> bool:
        """Tell whether this user control is focusable."""
        return True

    def create_content(self, width: int, height: int) -> "UIContent":
        def get_content() -> UIContent:
            fragment_lines = self.render(width)

            return UIContent(
                get_line=lambda i: fragment_lines[i],
                line_count=len(fragment_lines),
                show_cursor=False,
            )

        key = (hash(self.tabs), width, self.closeable, self.active)
        return self._content_cache.get(key, get_content)

    def render(self, width: "int") -> "List[StyleAndTextTuples]":
        """Render the tab-bar as linest of formatted text."""
        top_line: "StyleAndTextTuples" = []
        tab_line: "StyleAndTextTuples" = []
        i = 0

        # Initial spacing
        for _ in range(self.spacing):
            top_line += [("", " ")]
            tab_line += [("class:border,bottom", self.char_bottom)]
        i += self.spacing

        for j, tab in enumerate(self.tabs):
            title_ft = to_formatted_text(tab.title)
            title_width = fragment_list_width(title_ft)
            style = "class:active" if self.active == j else "class:inactive"

            # Add top edge over title
            top_line += [
                (f"{style} class:tab,border,top", self.char_top * (title_width + 2))
            ]

            # Left edge
            tab_line += [(f"{style} class:tab,border,left", self.char_left)]
            self.mouse_handlers[i] = tab.on_activate
            i += 1

            # Title
            tab_line += [
                (f"{style} class:tab,title {frag_style}", text)
                for frag_style, text, *_ in title_ft
            ]
            for _ in range(title_width):
                self.mouse_handlers[i] = tab.on_activate
                i += 1

            # Close button
            if self.closeable:
                top_line += [(f"{style} class:tab,border,top", self.char_top * 2)]
                self.mouse_handlers[i] = tab.on_activate
                i += 1
                tab_line += [
                    ("", " "),
                    (f"{style} class:tab,close", self.char_close),
                ]
                self.mouse_handlers[i] = tab.on_close
                i += 1

            # Right edge
            tab_line += [(f"{style} class:tab,border,right", self.char_right)]
            self.mouse_handlers[i] = tab.on_activate
            i += 1

            # Spacing
            for _ in range(self.spacing):
                top_line += [("", " ")]
                tab_line += [("class:border,bottom", self.char_bottom)]
                i += 1

        # Add border to fill width
        tab_line += [
            (
                "class:border,bottom",
                self.char_bottom * (width - fragment_list_width(tab_line)),
            )
        ]

        result = [top_line, tab_line]
        return result

    def mouse_handler(self, mouse_event: "MouseEvent") -> "NotImplementedOrNone":
        """Handle mouse events."""
        row = mouse_event.position.y
        col = mouse_event.position.x

        if row == 1:
            if mouse_event.event_type == MouseEventType.MOUSE_UP:
                if handler := self.mouse_handlers.get(col):
                    handler()
                    return None

        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            index = max(self.active - 1, 0)
            if index != self.active:
                if callable(deactivate := self.tabs[self.active].on_deactivate):
                    deactivate()
                if callable(activate := self.tabs[index].on_activate):
                    activate()
                return None
        elif mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            index = max(self.active + 1, len(self.tabs))
            if index != self.active:
                if callable(deactivate := self.tabs[self.active].on_deactivate):
                    deactivate()
                if callable(activate := self.tabs[index].on_activate):
                    activate()
                return None
        return NotImplemented


class StackedSplit(metaclass=ABCMeta):
    """Base class for containers with selectable children."""

    def __init__(
        self,
        children: "Sequence[AnyContainer]",
        titles: "Sequence[AnyFormattedText]",
        active: "int" = 0,
        style: "Union[str, Callable[[], str]]" = "class:tab-split",
        on_change: "Optional[Callable[[StackedSplit], None]]" = None,
    ) -> "None":
        """Create a new tabbed container instance.

        Args:
            children: A list of child container or a callable which returns such
            children: A list of tab titles or a callable which returns such
            active: The index of the active tab
            style: A style to apply to the tabbed container

        """
        self._children = list(children)
        self._titles = list(titles)
        self._active: "Optional[int]" = active
        self.style = style
        self.on_change = Event(self, on_change)

        self.container = self.load_container()

    @abstractmethod
    def load_container(self) -> "AnyContainer":
        ...

    def add_style(self, style) -> "str":
        base_style = self.style() if callable(self.style) else self.style
        return f"{base_style} {style}"

    @property
    def active(self) -> "Optional[int]":
        return self._active

    @active.setter
    def active(self, value: "Optional[int]") -> "None":
        """Set the active tab.

        Args:
            value: The index of the tab to make active
        """
        if value is not None:
            value = max(0, min(value, len(self.children)))
        if value != self._active:
            self._active = value
            self.refresh()
            self.on_change.fire()
            if value is not None:
                try:
                    get_app().layout.focus(self.children[value])
                except ValueError:
                    pass

    @property
    def children(self) -> "List[AnyContainer]":
        return self._children

    @children.setter
    def children(self, value: "Sequence[AnyContainer]") -> "None":
        self._children = list(value)
        self.refresh()

    def active_child(self):
        return self.children[self.active]

    @property
    def titles(self) -> "List[AnyFormattedText]":
        return self._titles

    @titles.setter
    def titles(self, value: "Sequence[AnyFormattedText]") -> "None":
        self._titles = list(value)
        self.refresh()

    def refresh(self) -> "None":
        pass

    def __pt_container__(self) -> "AnyContainer":
        """Return the widget's container."""
        return self.container


class TabbedSplit(StackedSplit):
    """A container which switches between children using tabs."""

    def load_container(self) -> "AnyContainer":
        self.control = TabControl(self.load_tabs(), active=self.active or 0)
        return HSplit(
            [
                Window(self.control, style=partial(self.add_style, "class:tab-bar")),
                Border(
                    Box(
                        DynamicContainer(self.active_child),
                        padding=0,
                        padding_top=1,
                        padding_bottom=1,
                    ),
                    border=OuterEdgeGridStyle,
                    show_borders=BorderVisibility(False, True, True, True),
                    style="class:border",
                ),
            ],
            style="class:tabbed-split",
        )

    def refresh(self):
        self.control.tabs = self.load_tabs()
        if self.active is not None:
            self.control.active = self.active

    def load_tabs(self):
        return tuple(
            Tab(
                title=title,
                on_activate=partial(setattr, self, "active", i),
            )
            for i, title in enumerate(self.titles)
        )


class AccordionSplit(StackedSplit):
    """A container which switches between children using expandable sections."""

    def load_container(self) -> "AnyContainer":
        self.draw_container()
        return DynamicContainer(lambda: self._container)

    def draw_container(self):
        self._container = HSplit(
            [
                Border(
                    HSplit(
                        [
                            Window(
                                FormattedTextControl(
                                    partial(self.title_text, index, title),
                                    focusable=True,
                                    show_cursor=False,
                                )
                            ),
                            ConditionalContainer(
                                Box(child, padding_left=0),
                                filter=Condition(
                                    partial(lambda i: self.active == i, index)
                                ),
                            ),
                        ]
                    ),
                    style=partial(self.add_style, "class:border"),
                )
                for index, (title, child) in enumerate(zip(self.titles, self.children))
            ],
            style="class:accordion",
        )

    def title_text(self, index: "int", title: "AnyFormattedText"):
        return [
            ("", " "),
            (
                "bold" + (" class:selection" if self.active == index else ""),
                "⮞" if self.active == index else "⮟",
                partial(self.mouse_handler, index),
            ),
            ("", " "),
            *[
                (
                    f"bold {style}",
                    text,
                    partial(self.mouse_handler, index),
                )
                for style, text, *_ in to_formatted_text(title)
            ],
        ]

    def mouse_handler(self, index: "int", mouse_event: "MouseEvent"):
        # if mouse_event.event_type == MouseEventType.MOUSE_DOWN:
        #     get_app().layout.focus()
        if mouse_event.event_type == MouseEventType.MOUSE_UP:
            self.toggle(index)

    def toggle(
        self,
        index: "int",
    ) -> "None":
        self.active = index if self.active != index else None

    def refresh(self):
        self.draw_container()
