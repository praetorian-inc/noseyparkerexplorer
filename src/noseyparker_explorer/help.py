from textwrap import dedent

from textual import on
from textual.app import ComposeResult, ScreenStackError
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, MarkdownViewer

from . import version
from .vi_motion import vi_motion_bindings

HELP_TEXT = dedent(f"""
# Nosey Parker Explorer v{version}

## Overview

Nosey Parker Explorer is a console application for interactive review and annotation of findings collected by [Nosey Parker](https://github.com/praetorian-inc/noseyparker).
It provides faceted search, allowing you to focus on findings from particular rules, Git repositories, particular files, etc.

It has been used successfully to review large sets of results (multi-gigabyte datastores with millions of matches from scanning thousands of Git repositories).

It works best with a terminal of at least 160x50.

Its interface three panes: a filters pane on the left, a findings pane on top, and a findings details pane on bottom.
When focusing on a particular finding, up to 10 occurrences of it are shown in the details window.
(This behavior can be overridden with the `--max-matches` command-line argument.)


## Filters

The filters pane provides a mechanism to filter the set of visible findings, similar to what you get in online shopping sites.

This filtering mechanism is known more technically as _faceted search_.
A number of _facets_ are available, such as `Rule`, each with a number of possible values.
These values can be selected to restrict the set of findings to those that have particular facet values.

By default, no facet values are selected, and the entire set of findings is displayed.
When you select a facet value (either by clicking it or pressing `x` or `Enter` when it is under the cursor), only findings that have that particular value will be displayed.

Multiple facet values can be selected simultaneously.
In this case, when two values `V1` and `V2` within the same facet are selected, it is their _union_ that is displayed.
That is, findings that have _either_ `V1` or `V2` for that facet will be shown.

The numbers next to facet values indicate how many findings are available given the current set of selected facet values.


## Annotations

You can assign a status (either `accept` or `reject`) and freeform comments to both findings and individual matches.
These annotations are included in the output of `noseyparker report`.
That command can also filter output by assigned status (e.g., `noseyparker report --finding-status accept` to only show accepted findings).

Any status or comment you assign will be saved to the Nosey Parker datastore you have opened.
Your data will not be lost.

Note that statuses are recorded at the individual match level, not the finding level, even though the UI supports assigning status when either a finding or individual match is selected.
When a finding is selected and a status is assigned, all of its matches _up to the point of the details pane scroll position_ are assigned that status.
This is done instead of assigning the status to _all_ matches of the finding to avoid assigning a status to matches that the operator has not actually looked at.


## Controls

### Focus
- **a**                    focus on the filters pane
- **f**                    focus on the findings pane
- **d**                    focus on the findings details pane

### Motion
- **←↑→↓ / hjkl**          move cursor
- **Page Up / CTRL+b**     scroll page up
- **Page Down / CTRL+f**   scroll page down
- **Home**                 scroll to top
- **End**                  scroll to bottom
- **0**                    scroll to start of line
- **$**                    scroll to end of line

### Filters
- **x**                    activate / deactivate selected filter value
- **R**                    reset all filters

### Findings
- **e**                    toggle finding status as `accept`
- **r**                    toggle finding status as `reject`
- **E**                    toggle finding status as `accept` and move down
- **R**                    toggle finding status as `reject` and move down
- **c**                    edit comment for finding

### Finding Details
- **o**                    open original source file for selected match
- **e**                    toggle finding status as `accept`
- **r**                    toggle finding status as `reject`
- **E**                    toggle finding status as `accept` and move down
- **R**                    toggle finding status as `reject` and move down
- **c**                    edit comment for match

### Global
- **q / CTRL-c**           quit
- **?**                    show this help
- **F7**                   show / hide the filters pane
- **CTRL-l**               redraw screen

### Mouse Input

Mouse input is supported.

- **Wheel**                scroll vertically
- **CTRL-Wheel**           scroll horizontally

Direct horizontal scrolling (such as on a trackpad) is *not* supported, due to limitations of terminal input libraries.

### Clipboard

Nosey Parker Explorer puts your terminal in to application mode which disables clicking and dragging to select text.
It _is_ possible to copy from Nosey Parker Explorer, but it probably requires pressing a modifier key as you click and drag:

- iTerm2: the `Fn` or Option key
- Gnome Terminal: the Shift key

Other terminals may use other modifier keys.
""")

@vi_motion_bindings
class HelpMarkdownViewer(MarkdownViewer):
    pass

class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "close", show=False),
        Binding("q", "close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="container"):
            yield HelpMarkdownViewer(HELP_TEXT, show_table_of_contents=True, id="viewer")
            yield Button('Dismiss (or press escape)', id="dismiss")

    @on(Button.Pressed, "#dismiss")
    def all_done(self) -> None:
        self.action_close()

    def action_close(self) -> None:
        try:
            self.dismiss(None)
        except ScreenStackError:
            # ignore "ScreenStackError: Can't dismiss screen HelpScreen() that's not at the top of the stack."
            pass
