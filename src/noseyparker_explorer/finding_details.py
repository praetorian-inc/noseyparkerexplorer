from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from typing import Literal

from .comment_screen import CommentScreen
from .findings import Match, MatchId, MatchStatus, FindingId
from .vi_motion import vi_motion_bindings


class FindingDetail(ListItem):
    def __init__(self, match: Match, *args, **kwargs):
        self._match = match
        self._content = Static(match, id='content')
        super().__init__(self._content, *args, **kwargs)

    def update_comment(self, comment: None | str) -> None:
        self._match.comment = comment
        self._content.update(self._match)

    def update_status(self, status: MatchStatus) -> None:
        self._match.status = status
        self._content.update(self._match)

    @property
    def match_id(self) -> MatchId:
        return self._match.id

    @property
    def finding_id(self) -> FindingId:
        return self._match.finding_id


@vi_motion_bindings
class FindingDetailsList(ListView):

    # FIXME: the page up / page down behavior is different here than with the FindingsTable

    ############################################################################
    # Messages
    ############################################################################
    class OpenSource(Message):
        def __init__(
            self,
            finding_details: FindingDetailsList,
            match: Match,
        ) -> None:

            self.finding_details = finding_details
            self.match = match
            super().__init__()

        @property
        def control(self) -> FindingDetailsList:
            return self.finding_details

    class CommentSet(Message):
        def __init__(
            self,
            finding_details: FindingDetailsList,
            match_id: MatchId,
            comment: None | str,
        ) -> None:
            self.finding_details = finding_details
            self.match_id = match_id
            self.comment = comment
            super().__init__()

        @property
        def control(self) -> FindingDetailsList:
            return self.finding_details

    class StatusSet(Message):
        def __init__(
            self,
            finding_details: FindingDetailsList,
            finding_id: FindingId,
            match_id: MatchId,
            current_status: MatchStatus,
            new_status: MatchStatus,
        ) -> None:
            self.finding_details = finding_details
            self.finding_id = finding_id
            self.match_id = match_id
            self.current_status = current_status
            self.new_status = new_status
            super().__init__()

        @property
        def control(self) -> FindingDetailsList:
            return self.finding_details

    ############################################################################
    # Bindings
    ############################################################################
    BINDINGS = [
        Binding("o", "open_file", "Open Source..."),

        Binding("r", "status_reject", "Match Status: Reject"),
        Binding("R", "status_reject_then_next", "Match Status: Reject", show=False),
        Binding("e", "status_accept", "Match Status: Accept"),
        Binding("E", "status_accept_then_next", "Match Status: Accept", show=False),
        Binding("c", "edit_comment", "Comment"),
    ]

    ############################################################################
    # Content updating
    ############################################################################
    async def repopulate(self, matches: list[Match]) -> None:
        with self.app.batch_update():
            await self.clear()
            for match in matches:
                await self.append(FindingDetail(match))

    ############################################################################
    # Open source...
    ############################################################################
    def action_open_file(self) -> None:
        if (child := self.highlighted_child) is None:
            return
        assert isinstance(child, FindingDetail)

        self.post_message(self.OpenSource(self, child._match))

    ############################################################################
    # Comments
    ############################################################################
    def action_edit_comment(self) -> None:
        if (child := self.highlighted_child) is None:
            return

        assert isinstance(child, FindingDetail)

        async def update_comment(comment: None | str) -> None:
            print('COMMENT:', comment)
            if comment is not None:
                child.update_comment(comment)
                self.post_message(self.CommentSet(self, child._match.id, comment))

        current_comment = child._match.comment or ''
        self.app.push_screen(CommentScreen(current_comment, placeholder_prefix='Comment on match'), update_comment)

    ############################################################################
    # Match status
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
        Update the status of the match in the currently selected item.

        If `new_status` is the same as the current status, the status of the
        item is cleared.
        """

        # get the currently selected item
        if (child := self.highlighted_child) is None:
            return

        assert isinstance(child, FindingDetail)

        match = child._match

        current_child_status = match.status
        if match.status == new_status:
            new_child_status = None
        else:
            new_child_status = new_status

        child.update_status(new_child_status)

        self.post_message(self.StatusSet(
            self,
            match.finding_id,
            match.id,
            current_child_status,
            new_child_status,
        ))
