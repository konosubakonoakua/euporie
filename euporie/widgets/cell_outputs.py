"""Contains a container for the cell output area."""

import logging
from abc import ABCMeta, abstractmethod
from pathlib import PurePath
from typing import TYPE_CHECKING, NamedTuple, cast

from prompt_toolkit.layout.containers import HSplit, Window, to_container

from euporie.convert.base import MIME_FORMATS, find_route
from euporie.widgets.display import Display

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, List, Literal, Optional, Union

    from prompt_toolkit.layout.containers import AnyContainer

log = logging.getLogger(__name__)


class CellOutputElement(metaclass=ABCMeta):
    def __init__(
        self, mime: "str", data: "str", metadata: "Dict", cell: "Cell"
    ) -> "None":
        ...

    @abstractmethod
    def __pt_container__(self) -> "AnyContainer":
        ...


class CellOutputDataElement(CellOutputElement):
    def __init__(
        self, mime: "str", data: "str", metadata: "Dict", cell: "Cell"
    ) -> "None":
        """"""
        self.cell = cell

        # Get foreground and background colors
        fg_color = self.cell.nb.app.color_palette.fg.base_hex
        bg_color = {"light": "#FFFFFF", "dark": "#000000"}.get(
            metadata.get("needs_background")
        )

        # Get internal format
        format_ = "ansi"
        mime_path = PurePath(mime)
        for format_mime, mime_format in MIME_FORMATS.items():
            if mime_path.match(format_mime):
                if find_route(mime_format, "formatted_text") is not None:
                    format_ = mime_format
                    break

        self.container = Display(
            datum=data,
            format_=format_,
            fg_color=fg_color,
            bg_color=bg_color,
            px=metadata.get("width"),
            py=metadata.get("height"),
            focusable=False,
            focus_on_click=False,
            show_scrollbar=False,
            wrap_lines=False,
            always_hide_cursor=True,
            style=f"class:cell.output.element.data class:mime.{mime.replace('/','.')}",
        )

    def __pt_container__(self) -> "AnyContainer":
        return self.container


class CellOutputWidgetElement(CellOutputElement):
    def __init__(
        self, mime: "str", data: "str", metadata: "Dict", cell: "Cell"
    ) -> "None":
        self.cell = cell
        self.comm_id = data.get("model_id")

        comm = self.cell.nb.comms.get(self.comm_id)
        if comm:
            self.container = comm.create_view(self.cell)
        else:
            self.container = Display(self.comm_id, format_="ansi")

    def __pt_container__(self) -> "AnyContainer":
        return self.container


MIME_RENDERERS = {
    "application/vnd.jupyter.widget-view+json": CellOutputWidgetElement,
    "*": CellOutputDataElement,
}

MIME_ORDER = [
    "application/vnd.jupyter.widget-view+json",
    "image/*",
    "application/pdf",
    "text/latex",
    "text/markdown",
    "text/x-markdown",
    "text/x-python-traceback",
    "text/stderr",
    "text/html",
    "text/*",
    "*",
]


def _calculate_mime_rank(mime_data: "Tuple[str, Any]") -> "int":
    """Scores the richness of mime output types."""
    mime, data = mime_data
    for i, ranked_mime in enumerate(MIME_ORDER):
        # Uprank plain text with escape sequences
        if mime == "text/plain" and "\x1b[" in data:
            i -= 2
        if mime == "text/html" and "<" not in data:
            i += 2
        if PurePath(mime).match(ranked_mime):
            return i
    else:
        return 999


class CellOutput:
    """Represents a single cell output.

    Capable of displaying multiple mime representations of the same data.

    TODO - allow the visible mime-type to be rotated.
    """

    def __init__(self, json, cell: "Cell") -> "None":
        # Select the first mime-type to render
        self.cell = cell
        self._json = json
        self._selected_mime = None
        self._containers = {}

    @property
    def selected_mime(self) -> "None":
        data = self.data
        # If an mime-type has not been explicitly selected, display the first
        if self._selected_mime not in data:
            return next(x for x in self.data)
        return self._selected_mime

    @property
    def json(self) -> "Dict":
        return self._json

    @json.setter
    def json(self, outputs_json: "Dict") -> "None":
        self._json = outputs_json
        self._containers = {}

    @property
    def container(self) -> "CellOutputElement":
        if self.selected_mime not in self._containers:
            for mime_pattern, OutputElement in MIME_RENDERERS.items():
                if PurePath(self.selected_mime).match(mime_pattern):
                    element = OutputElement(
                        mime=self.selected_mime,
                        data=self.data[self.selected_mime],
                        metadata=self.json.get("metadata", {}).get(
                            self.selected_mime, {}
                        ),
                        cell=self.cell,
                    )
                    self._containers[self.selected_mime] = element
                    return element

        return self._containers[self.selected_mime]

    @property
    def data(self) -> "dict[str, str]":
        """Return dictionary of mime types and data for this output.

        This generates similarly structured data objects for markdown cells and text
        output streams.

        Returns:
            JSON dictionary mapping mimes type to representation data.

        """
        data = {}
        output_type = self.json.get("output_type", "unknown")
        if output_type == "stream":
            data = {f'stream/{self.json.get("name")}': self.json.get("text", "")}
        elif output_type == "error":
            data = {
                "text/x-python-traceback": "\n".join(self.json.get("traceback", ""))
            }
        else:
            data = self.json.get("data", {})
        return dict(sorted(data.items(), key=_calculate_mime_rank))

    def __pt_container__(self):
        return self.container


class CellOutputArea:
    def __init__(self, json, cell: "Cell") -> "None":
        self.cell = cell
        self._rendered_outputs = []
        self.container = HSplit([])
        self.json = json

    @property
    def json(self) -> "Dict":
        return self._json

    @json.setter
    def json(self, outputs_json: "Dict") -> "None":
        self._json = outputs_json
        self.container.children = self.rendered_outputs

    @property
    def rendered_outputs(self) -> "List[CellOutput]":
        """Generates a list of rendered outputs."""
        n_existing_outputs = len(self._rendered_outputs)
        rendered_outputs: "List[CellOutput]" = []
        for i, output_json in enumerate(self.json):
            if i < n_existing_outputs:
                output = self._rendered_outputs[i]
                output.json = output_json
            else:
                output = CellOutput(output_json, self.cell)
            rendered_outputs.append(output)
        self._rendered_outputs = rendered_outputs
        return [to_container(x) for x in rendered_outputs]

    def scroll_left(self) -> "None":
        """Scrolls the outputs left."""
        for output_window in self.container.children:
            output_window._scroll_left()

    def scroll_right(self) -> "None":
        """Scrolls the outputs right."""
        for output_window in self.container.children:
            output_window._scroll_right()

    def __pt_container__(self):
        return self.container