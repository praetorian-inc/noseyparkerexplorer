from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal

from rich.text import Text
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable
from textual.widgets.data_table import ColumnKey, RowKey

from .comment_screen import CommentScreen
from .findings import Finding, FindingId, MatchStatus, FindingStatus
from .vi_motion import vi_motion_bindings


@dataclass(frozen=True, order=True, repr=True, slots=True)
class ColumnDescriptor:
    """
    A description of a column in the `FindingsTable`.

    This is used for data-oriented configuration of the columns in a findings table.
    """

    name: str
    accessor: Callable[[Finding], str | int | float | None]
    sort_key: Callable[[FindingsTableCell], Any]
    max_width: int | None = None


def _get_groups(f: Finding) -> str:
    gs = f.groups
    if len(gs) == 1:
        return gs[0]
    else:
        return str(gs)  # FIXME: render multiple groups more usefully


_COLUMN_DESCRS: list[ColumnDescriptor] = [
    ColumnDescriptor(
        name="Rule Name",
        accessor=lambda f: f.rule_name,
        sort_key=lambda c: c.value,
    ),
    ColumnDescriptor(
        name="Groups",
        max_width=60,
        accessor=_get_groups,
        sort_key=lambda c: c.value,
    ),
    ColumnDescriptor(
        name="Count",
        accessor=lambda f: f.num_matches,
        sort_key=lambda c: c.value,
    ),
    ColumnDescriptor(
        name="Score",
        accessor=lambda f: f.mean_score,
        sort_key=lambda c: c.value or 0.0,
    ),
    ColumnDescriptor(
        name="Status",
        accessor=lambda f: f.status,
        sort_key=lambda c: c.value or "",
    ),
    ColumnDescriptor(
        name="Comment",
        accessor=lambda f: f.comment,
        sort_key=lambda c: c.value or "",
    ),
]


def _column_index(name: str) -> int:
    for i, k in enumerate(_COLUMN_DESCRS):
        if k.name == name:
            return i
    raise KeyError(f"column {name} not found")


_COMMENT_COLUMN = _column_index("Comment")
_STATUS_COLUMN = _column_index("Status")


@dataclass(repr=True, slots=True)
class FindingsTableCell:
    """
    A cell within a `FindingsTable`.

    This keeps track of both a raw value and a renderable form, making it
    possible to correctly sort columns in a findings table while still
    supporting custom rendering.
    """

    value: Any
    label: Text

    def __rich__(self) -> Text:
        return self.label


SortState = tuple[int, bool] | None


@vi_motion_bindings
class FindingsTable(DataTable[FindingsTableCell]):
    """
    A table that displays Nosey Parker findings.

    Each finding gets one row in the table.
    Findings can be commented upon and have a status set.
    """

    ############################################################################
    # Messages
    ############################################################################
    class StatusSet(Message):
        def __init__(
            self,
            findings_table: FindingsTable,
            row_key: RowKey,
            finding_id: FindingId,
            current_status: MatchStatus,
            new_status: MatchStatus,
        ) -> None:
            self.findings_table = findings_table
            self.row_key = row_key
            self.finding_id = finding_id
            self.current_status = current_status
            self.new_status = new_status
            super().__init__()

        @property
        def control(self) -> FindingsTable:
            return self.findings_table

    class CommentSet(Message):
        def __init__(
            self,
            findings_table: FindingsTable,
            row_key: RowKey,
            finding_id: FindingId,
            comment: None | str,
        ) -> None:
            self.findings_table = findings_table
            self.row_key = row_key
            self.finding_id = finding_id
            self.comment = comment
            super().__init__()

        @property
        def control(self) -> FindingsTable:
            return self.findings_table

    ############################################################################
    # Bindings
    ############################################################################
    BINDINGS = [
        Binding("r", "status_reject", "Status: Reject"),
        Binding("R", "status_reject_then_next", "Status: Reject", show=False),
        Binding("e", "status_accept", "Status: Accept"),
        Binding("E", "status_accept_then_next", "Status: Accept", show=False),
        Binding("c", "edit_comment", "Comment"),
    ]

    ############################################################################
    # Reactives
    ############################################################################
    sort_state: reactive[SortState] = reactive(None)

    ############################################################################
    # Widget basics
    ############################################################################
    def on_mount(self) -> None:
        self.cursor_type = "row"

    ############################################################################
    # Column sorting
    ############################################################################
    def on_data_table_header_selected(self, evt: DataTable.HeaderSelected) -> None:
        sort_reverse = False
        if (sort_state := self.sort_state) is not None:
            if sort_state[0] == evt.column_index:
                sort_reverse = not sort_state[1]

        self.sort_state = (evt.column_index, sort_reverse)

    def watch_sort_state(self, old: SortState, new: SortState) -> None:
        if old is not None and old != new:
            # reset label for previous sort column
            old_index, old_reverse = old
            old_column_descr = _COLUMN_DESCRS[old_index]
            old_key = ColumnKey(old_column_descr.name)
            self.columns[old_key].label = Text(old_column_descr.name)

        if new is not None:
            new_index, new_reverse = new
            new_column_descr = _COLUMN_DESCRS[new_index]
            new_key = ColumnKey(new_column_descr.name)
            direction = "▼" if new_reverse else "▲"
            self.columns[new_key].label = Text(f"{new_column_descr.name} {direction}")
            self.sort(new_key, reverse=new_reverse, key=new_column_descr.sort_key)

    ############################################################################
    # Content updating
    ############################################################################
    async def repopulate(self, findings: Iterable[Finding]) -> None:
        """
        Clear and repopulate this `FindingsTable` with the given iterable of findings.
        """
        with self.app.batch_update():
            await self._repopulate(findings)

    async def _repopulate(self, findings: Iterable[Finding]) -> None:
        # remove and re-add columns to get them to resize if possible
        self.clear(columns=True)

        # keep the list of column keys for re-sorting later
        column_keys = [
            self.add_column(f"{descr.name}  ", width=descr.max_width, key=descr.name)
            for descr in _COLUMN_DESCRS
        ]

        # add a row for each finding
        for finding_num, finding in enumerate(findings, 1):
            if finding_num % 2500 == 0:
                await asyncio.sleep(0)  # allow for other coroutines to run

            # compute each column value
            row_values: list[FindingsTableCell] = []
            for descr in _COLUMN_DESCRS:
                value = descr.accessor(finding)

                if value is None:
                    label = Text()

                elif isinstance(value, str):
                    # N.B. we explicitly use `Text` here to prevent string
                    # values from being interpreted as containing Rich markup

                    # truncate overly long labels
                    max_width = descr.max_width
                    if max_width is not None and len(value) > max_width:
                        value = f"{value[:max_width - 1]}…"

                    label = Text(value)

                elif isinstance(value, int):
                    label = Text(f"{value}", justify="right")

                elif isinstance(value, float):
                    label = Text(f"{value:.3f}", justify="right")

                elif isinstance(value, Text):
                    label = value

                else:
                    assert (
                        False
                    ), f"Unhandled cell type case for value of type {type(value)}"

                row_values.append(FindingsTableCell(value=value, label=label))

            self.add_row(*row_values, key=finding.id)

        # re-sort table
        if (sort_state := self.sort_state) is not None:
            self.watch_sort_state(sort_state, sort_state)

    def update_row_status_cell(self, finding_id: FindingId, status: FindingStatus) -> None:
        """
        Update the status for the row with the given finding ID.

        This exists so that the findings table can have status values updated
        without having to use its expensive repopulate() function.
        """
        row_idx = self.get_row_index(finding_id)
        print(f'{finding_id = } {row_idx = }')

        coord = Coordinate(row=row_idx, column=_STATUS_COLUMN)
        cell = self.get_cell_at(coord)
        cell.value = status
        cell.label = Text(status or '')
        self.update_cell_at(coord, cell, update_width=True)


    ############################################################################
    # Finding comments
    ############################################################################
    def action_edit_comment(self) -> None:
        selected_row_idx = self.cursor_row
        if not self.is_valid_row_index(selected_row_idx):
            return

        coord = Coordinate(row=selected_row_idx, column=_COMMENT_COLUMN)

        async def update_comment(comment: None | str) -> None:
            if comment is not None:
                new_cell = FindingsTableCell(value=comment, label=Text(comment))
                self.update_cell_at(coord, new_cell, update_width=True)
                key = self.coordinate_to_cell_key(coord)
                row_key = key.row_key
                row_value = row_key.value
                assert isinstance(row_value, str)
                finding_id = FindingId(row_value)
                self.post_message(self.CommentSet(self, row_key, finding_id, comment))

        current_comment = self.get_cell_at(coord)
        self.app.push_screen(CommentScreen(current_comment.label.plain, placeholder_prefix='Comment on finding'), update_comment)

    ############################################################################
    # Finding status
    ############################################################################
    def action_status_reject(self) -> None:
        self._update_status("reject")

    async def action_status_reject_then_next(self) -> None:
        async with self.batch():
            self._update_status("reject")
            self.action_cursor_down()

    def action_status_accept(self) -> None:
        self._update_status("accept")

    async def action_status_accept_then_next(self) -> None:
        async with self.batch():
            self._update_status("accept")
            self.action_cursor_down()

    def _update_status(self, new_status: Literal["accept", "reject"]) -> None:
        """
        Update the status of matches from the finding of the currently selected
        row.

        If `new_status` is the same as the current status, the status of the
        row is cleared.

        This posts a `StatusSet` message.
        """

        # get the currently selected row
        selected_row_idx = self.cursor_row
        if not self.is_valid_row_index(selected_row_idx):
            return None

        # get the coordinate and cell for the status cell of the selected row
        status_coord = Coordinate(row=selected_row_idx, column=_STATUS_COLUMN)
        status_cell = self.get_cell_at(status_coord)
        status_cell_key = self.coordinate_to_cell_key(status_coord)

        current_cell_status = status_cell.value

        if status_cell.value == new_status:
            # clear status
            new_cell_status = None
            new_cell_label = Text()
        else:
            # update status
            new_cell_status = new_status
            new_cell_label = Text(new_status)

        status_cell.value = new_cell_status
        status_cell.label = new_cell_label

        self.update_cell_at(status_coord, status_cell, update_width=True)

        row_key = status_cell_key.row_key
        row_key_value = row_key.value
        assert isinstance(row_key_value, str)
        finding_id = FindingId(row_key_value)
        self.post_message(self.StatusSet(self, row_key, finding_id, current_cell_status, new_cell_status))
