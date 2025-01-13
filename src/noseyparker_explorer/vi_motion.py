from __future__ import annotations

from textual import events


def vi_motion_bindings(klass: type) -> type:
    """
    A widget class decorator that adds several vi-inspired motion bindings.

    The added motion bindings will not be shown in a footer.

    The event handler implementation for each added motion binding is written to
    stop event bubbling and avoid extraneous method calls.
    """

    def key_ctrl_f(self, evt: events.Key) -> None:
        self.scroll_page_down(animate=False)
        evt.stop()
    setattr(klass, 'key_ctrl_f', key_ctrl_f)

    def key_ctrl_b(self, evt: events.Key) -> None:
        self.scroll_page_up(animate=False)
        evt.stop()
    setattr(klass, 'key_ctrl_b', key_ctrl_b)

    def key_ctrl_e(self, evt: events.Key) -> None:
        self.scroll_to(y=self.scroll_target_y + 1, animate=False)
        evt.stop()
    setattr(klass, 'key_ctrl_e', key_ctrl_e)

    def key_ctrl_y(self, evt: events.Key) -> None:
        self.scroll_to(y=self.scroll_target_y - 1, animate=False)
        evt.stop()
    setattr(klass, 'key_ctrl_y', key_ctrl_y)

    def key_h(self, evt: events.Key) -> None:
        self.scroll_to(x=self.scroll_target_x - 5, animate=False)
        evt.stop()
    setattr(klass, 'key_h', key_h)

    if hasattr(klass, 'action_cursor_down'):
        def key_j(self, evt: events.Key) -> None:
            self.action_cursor_down()
            evt.stop()
    else:
        def key_j(self, evt: events.Key) -> None:
            self.scroll_down(animate=False)
            evt.stop()
    setattr(klass, 'key_j', key_j)

    if hasattr(klass, 'action_cursor_up'):
        def key_k(self, evt: events.Key) -> None:
            self.action_cursor_up()
            evt.stop()
    else:
        def key_k(self, evt: events.Key) -> None:
            self.scroll_up(animate=False)
            evt.stop()
    setattr(klass, 'key_k', key_k)

    def key_l(self, evt) -> None:
        self.scroll_to(x=self.scroll_target_x + 5, animate=False)
        evt.stop()
    setattr(klass, 'key_l', key_l)

    def key_dollar_sign(self, evt) -> None:
        self.scroll_to(x=self.scroll_target_x + 1000000, animate=False)
        evt.stop()
    setattr(klass, 'key_dollar_sign', key_dollar_sign)

    def key_0(self, evt) -> None:
        self.scroll_to(x=self.scroll_target_x - 1000000, animate=False)
        evt.stop()
    setattr(klass, 'key_0', key_0)

    def action_scroll_right(self) -> None:
        self.scroll_to(x=self.scroll_target_x + 5, animate=False)
    setattr(klass, "action_scroll_right", action_scroll_right)

    def action_scroll_left(self) -> None:
        self.scroll_to(x=self.scroll_target_x - 5, animate=False)
    setattr(klass, "action_scroll_left", action_scroll_left)

    return klass
