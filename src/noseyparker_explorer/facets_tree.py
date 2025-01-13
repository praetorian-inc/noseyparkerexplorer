from __future__ import annotations

import asyncio
from typing import Iterable

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree

from .facets import FacetDefinition, FacetMetadata, FacetValue
from .vi_motion import vi_motion_bindings


@vi_motion_bindings
class FacetsTree(Tree[tuple[FacetValue, FacetMetadata] | str]):
    ############################################################################
    # Bindings
    ############################################################################
    BINDINGS = [
        Binding("x", "select_cursor", "Select", show=True),
        Binding("ctrl+r", "reset_selections", "Reset All Filters", show=True),
    ]

    ############################################################################
    # Messages
    ############################################################################
    class FacetSelected(Message):
        """
        Emitted when a facet is selected in the tree.
        """
        def __init__(self, facets_tree: FacetsTree, facet_value: FacetValue) -> None:
            self.facets_tree = facets_tree
            self.facet_value = facet_value
            super().__init__()

        @property
        def control(self) -> FacetsTree:
            return self.facets_tree

    class FacetDeselected(Message):
        """
        Emitted when a facet is deselected in the tree.
        """
        def __init__(self, facets_tree: FacetsTree, facet_value: FacetValue) -> None:
            self.facets_tree = facets_tree
            self.facet_value = facet_value
            super().__init__()

        @property
        def control(self) -> FacetsTree:
            return self.facets_tree

    class ResetSelections(Message):
        """
        Emitted when the selections are requested to be reset.
        """
        def __init__(self, facets_tree: FacetsTree) -> None:
            self.facets_tree = facets_tree
            super().__init__()

        @property
        def control(self) -> FacetsTree:
            return self.facets_tree

    ############################################################################
    # Widget basics
    ############################################################################
    def __init__(self, *args, **kwargs) -> None:
        # the set of facet names that are not expanded
        self._collapsed: set[str] = set()

        # the set of facet values that are selected
        self._selected: set[FacetValue] = set()

        super().__init__("Facets", *args, **kwargs)

    def on_mount(self) -> None:
        self.show_root = False
        self.show_guides = False
        self.guide_depth = 2


    ############################################################################
    # Content updating
    ############################################################################
    def action_reset_selections(self) -> None:
        self._selected.clear()
        self.post_message(self.ResetSelections(self))

    async def repopulate(
        self,
        facets_iter: Iterable[tuple[FacetDefinition, list[tuple[FacetValue, FacetMetadata]]]],
    ) -> None:
        """
        Replace the contents of this FacetsTree with the given ones.
        """
        async with self.lock:
            await self._repopulate(facets_iter)

    async def _repopulate(
        self,
        facets_iter: Iterable[tuple[FacetDefinition, list[tuple[FacetValue, FacetMetadata]]]],
    ) -> None:

        selected_line = self.cursor_line
        collapsed = self._collapsed
        selected = self._selected

        self.clear()

        leaves_added = 0
        for dfn, pairs in facets_iter:
            # FIXME: figure out a better way to deal with huge facets
            LIMIT = 125
            if len(pairs) > LIMIT:
                pairs = pairs[:LIMIT]
                entries_label = f"{LIMIT}+"
            else:
                entries_label = str(len(pairs))

            name = f"{dfn.name} ({entries_label} options)"
            expand = name not in collapsed
            tree = self.root.add(name, expand=expand, data=name)
            for facet_value, facet_metadata in pairs:
                label = make_label(facet_value in selected, facet_value, facet_metadata)
                tree.add_leaf(label, data=(facet_value, facet_metadata))

                leaves_added += 1
                if leaves_added % 2500 == 0:
                    await asyncio.sleep(0)  # allow for other coroutines to run


        # reset the cursor
        selected_line = self.validate_cursor_line(selected_line)
        if (node := self.get_node_at_line(selected_line)) is not None:
            self.move_cursor(node)

    ############################################################################
    # Message handling
    ############################################################################
    def on_tree_node_collapsed(self, evt: Tree.NodeCollapsed) -> None:
        # keep track of the set of collapsed facets
        data = evt.node.data
        assert isinstance(data, str)
        self._collapsed.add(data)

    def on_tree_node_expanded(self, evt: Tree.NodeCollapsed) -> None:
        # keep track of the set of collapsed facets
        data = evt.node.data
        assert isinstance(data, str)
        self._collapsed.discard(data)

    def on_tree_node_selected(self, evt: Tree.NodeSelected) -> None:
        node = evt.node
        data = node.data

        if isinstance(data, str):
            # skip non-leaf nodes
            return

        assert isinstance(data, tuple)
        facet_value, facet_metadata = data

        # keep track of the set of selected facet values
        is_selected = facet_value in self._selected

        msg: Message
        if is_selected:
            msg = self.FacetDeselected(
                facets_tree=self,
                facet_value=facet_value,
            )
            self._selected.discard(facet_value)
        else:
            msg = self.FacetSelected(
                facets_tree=self,
                facet_value=facet_value,
            )
            self._selected.add(facet_value)

        node.label = make_label(not is_selected, facet_value, facet_metadata)

        self.refresh()

        self.post_message(msg)


def make_label(is_selected: bool, facet_value: FacetValue, facet_metadata: FacetMetadata) -> Text:
    selector = Text("+" if is_selected else " ", style="bold")
    count = facet_metadata.count
    count_style = "dim" if count == 0 else ""

    if isinstance(facet_value.value, str):
        value = facet_value.value
    elif isinstance(facet_value.value, bytes):
        value = facet_value.value.decode('utf-8', errors='replace')
    elif facet_value.value is None:
        value = '<missing>'
    else:
        assert False, f'facet value has unexpected type {type(facet_value.value)}'

    return Text.assemble(
        selector,
        " ",
        Text(value, style=count_style),
        " ",
        Text(f"({count})", style=count_style),
        style="bold" if is_selected else "",
    )
