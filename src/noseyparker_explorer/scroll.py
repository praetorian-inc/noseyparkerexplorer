from textual.containers import ScrollableContainer

from .vi_motion import vi_motion_bindings


@vi_motion_bindings
class Scroll(ScrollableContainer, can_focus=True, inherit_bindings=True, inherit_css=True):
    DEFAULT_CSS = """
    Scroll {
        width: 1fr;
        height: 1fr;
        layout: vertical;
        overflow: auto auto;
    }
    """
