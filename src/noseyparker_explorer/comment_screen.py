from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Input


class CommentScreen(ModalScreen[None | str]):
    """
    A modal screen for comment entry.

    When dismissed, it returns an optional string for the comment that was
    entered (if any).
    """

    def __init__(
        self,
        current_comment: str,
        *args,
        placeholder_prefix: None | str = None,
        placeholder: None | str = None,
        **kwargs,
    ) -> None:
        self.current_comment = current_comment

        if placeholder is None:
            placeholder_prefix = placeholder_prefix or 'Comment'
            placeholder = f"{placeholder_prefix}: enter to submit or escape to cancel"

        self.placeholder = placeholder
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield Input(
            value=self.current_comment,
            placeholder=self.placeholder,
        )

    def key_escape(self, evt) -> None:
        evt.stop()
        self.dismiss(None)

    @on(Input.Submitted)
    def submitted(self, evt: Input.Submitted) -> None:
        evt.stop()
        self.dismiss(evt.value)
