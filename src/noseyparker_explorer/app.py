import asyncio
import datetime
import os
from itertools import islice
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Header

from . import version
from .datastore import NoseyParkerDatastoreBuilder
from .facets_tree import FacetsTree
from .filters import Filters
from .finding_details import FindingDetail, FindingDetailsList, MatchStatus
from .findings import FindingId, MatchId
from .findings_table import FindingsTable
from .help import HelpScreen
from .match_source_screen import MatchSourceScreen
from .timed import timed


class NoseyParkerExplorer(App):
    ############################################################################
    # default configuration
    ############################################################################
    TITLE = f"Nosey Parker Explorer v{version}"

    CSS_PATH = "noseyparker_explorer.tcss"

    BINDINGS = [
        Binding("?", "help", "Help"),
        Binding("ctrl+l", "redraw", "Redraw", show=False),
    ]

    ############################################################################
    # app basics
    ############################################################################
    def __init__(
        self,
        datastore_dir: Path,
        *args,
        max_findings: int,
        max_matches: int,
        max_provenance: int,
        suppress_redundant: bool,
        min_score: float,
        blobs_dir: Path,
        exclusions_file: None | Path,
        **kwargs,
    ) -> None:

        super().__init__(*args, **kwargs)

        self.datastore_dir = datastore_dir
        self.max_findings = max_findings if max_findings > 0 else None
        self.max_matches = max_matches if max_matches > 0 else None
        self.max_provenance = max_provenance if max_provenance > 0 else None
        self.suppress_redundant = suppress_redundant
        self.min_score = min_score if min_score >= 0 else None
        self.blobs_dir = blobs_dir
        self.exclusions_file = exclusions_file

    def on_mount(self) -> None:
        self.push_screen(NoseyParkerMainScreen(
            self.datastore_dir,
            max_findings=self.max_findings,
            max_matches=self.max_matches,
            max_provenance=self.max_provenance,
            suppress_redundant=self.suppress_redundant,
            min_score=self.min_score,
            blobs_dir=self.blobs_dir,
            exclusions_file=self.exclusions_file,
            id='main-screen',
        ))

    ############################################################################
    # help
    ############################################################################
    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())

    async def action_quit(self) -> None:
        await self.query_one('#main-screen', NoseyParkerMainScreen).cleanup()
        await asyncio.get_running_loop().shutdown_asyncgens()
        for task in asyncio.all_tasks():
            task.cancel()



class NoseyParkerMainScreen(Screen):
    ############################################################################
    # default configuration
    ############################################################################

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("a", "focus_filters", "Focus Filters", show=False),
        Binding("f", "focus_findings", "Focus Findings", show=False),
        Binding("d", "focus_details", "Focus Details", show=False),
        Binding("f5", "toggle_header", "Show/Hide Header", show=False),
        Binding("f7", "toggle_filters_visible", "Show/Hide Filters", show=False),
    ]

    ############################################################################
    # app basics
    ############################################################################
    def __init__(
        self,
        datastore_dir: Path,
        *args,
        max_findings: None | int,
        max_matches: None | int,
        max_provenance: None | int,
        suppress_redundant: bool,
        min_score: None | float,
        blobs_dir: Path,
        exclusions_file: None | Path,
        **kwargs,
    ) -> None:

        super().__init__(*args, **kwargs)
        self.datastore_dir = datastore_dir
        self.dbfile = datastore_dir / "datastore.db"
        self.max_findings = max_findings
        self.max_matches = max_matches
        self.max_provenance = max_provenance
        self.suppress_redundant = suppress_redundant
        self.min_score = min_score
        self.blobs_dir: Path = blobs_dir
        self.datastore_builder = NoseyParkerDatastoreBuilder(
            self.dbfile,
            exclusions_file=exclusions_file,
            max_provenance=max_provenance,
        )
        self.sub_title = str(self.datastore_dir)
        self.last_focused: Widget | None = None
        self.filters = Filters(min_score = min_score)

        # What finding ID is showing in the finding details widget right now?
        self._finding_details_finding_id: None | FindingId = None

    def compose(self) -> ComposeResult:
        yield Header(id="header")

        main_pane = Horizontal(id="main")
        main_pane.loading = True
        with main_pane:
            with Vertical(id="data"):
                yield FindingsTable(id="findings")
                yield FindingDetailsList(id="details")

            with Vertical(id="filters"):
                yield FacetsTree(id="facets")

        yield Footer()

    # This method is async and run in a worker so that the potentially long
    # datastore connection doesn't freeze the UI so badly.
    #
    # XXX the real problem here is that the findings table is a DataTable,
    # which requires that all the data be eagerly loaded in.
    #
    # See https://pypi.org/project/textual-fastdatatable/ for a possible
    # better-performing alternative.
    @work(exclusive=True, group="noseyparker-explorer--on-mount")
    async def on_mount(self) -> None:
        # Connect to the database; this may take a while.
        with timed("connected to datastore"):
            self.datastore = await self.datastore_builder.connect()

        try:
            # Populate findings table, facets, and details with empty content first
            # to get the layout to appear instead of a mostly empty UI.
            # This is especially important when opening large datastores, where the
            # initial load phase can be quite expensive.
            with timed("initial layout"):
                with timed("recomputed facets"):
                    new_facets = await asyncio.to_thread(
                        self.datastore.get_facets,
                        self.filters,
                        suppress_redundant=self.suppress_redundant,
                    )
                await self.query_one('#facets', FacetsTree).repopulate(new_facets)
                await self.query_one('#findings', FindingsTable).repopulate([])
                await self.query_one('#details', FindingDetailsList).repopulate([])

            self.query_one("#main", Horizontal).loading = False

            # Now update with real content.
            await self._filters_updated()
        except:
            await self.cleanup()
            raise

    async def cleanup(self) -> None:
        # FIXME: figure out how to call this on event of unhandled exception so that the app doesn't freeze
        try:
            await self.datastore.close()
        except Exception as e:
            pass

    async def action_quit(self) -> None:
        await self.cleanup()
        self.app.exit()

    ############################################################################
    # header
    ############################################################################
    def action_toggle_header(self) -> None:
        header = self.query_one("#header", Header)
        header.tall = not header.tall

    ############################################################################
    # redraw
    ############################################################################
    def action_redraw(self) -> None:
        self.refresh(repaint=True, layout=True)

    ############################################################################
    # filters
    ############################################################################
    def action_focus_filters(self) -> None:
        self.query_one("#facets").focus()

    def action_toggle_filters_visible(self) -> None:
        filters = self.query_one("#filters")
        facets = self.query_one("#facets", FacetsTree)

        if filters.styles.display == "none":
            filters.disabled = False
            filters.styles.display = "block"
            facets.focus()
        else:
            if facets.has_focus:
                self.query_one("#findings", FindingsTable).focus()
            filters.disabled = True
            filters.styles.display = "none"

    @on(FacetsTree.FacetSelected, "#facets")
    async def facet_selected(self, evt: FacetsTree.FacetSelected) -> None:
        facet_value = evt.facet_value
        if self.filters.select_facet_value(facet_value):
            await self._filters_updated()

    @on(FacetsTree.FacetDeselected, "#facets")
    async def facet_deselected(self, evt: FacetsTree.FacetDeselected) -> None:
        facet_value = evt.facet_value
        if self.filters.deselect_facet_value(facet_value):
            await self._filters_updated()

    @on(FacetsTree.ResetSelections, "#facets")
    async def facets_reset(self, evt: FacetsTree.ResetSelections) -> None:
        if self.filters.clear():
            await self._filters_updated()

    def _fetch_data(self):
        with timed("recomputed facets"):
            new_facets = self.datastore.get_facets(self.filters, suppress_redundant=self.suppress_redundant)

        with timed("recomputed findings"):
            new_findings = self.datastore.get_findings(self.filters, suppress_redundant=self.suppress_redundant)

        with timed("counted findings"):
            tot_findings = self.datastore.get_total_num_findings(self.filters, suppress_redundant=self.suppress_redundant)

        return new_facets, new_findings, tot_findings

    async def _filters_updated(self) -> None:
        with timed("updated filters"):
            facets = self.query_one('#facets', FacetsTree)
            findings = self.query_one('#findings', FindingsTable)
            details = self.query_one('#details', FindingDetailsList)

            try:
                # details.loading = True
                # findings.loading = True
                # facets.disabled = True

                new_facets, new_findings, tot_findings = await asyncio.to_thread(self._fetch_data)

                with timed("repopulated facets"):
                    await facets.repopulate(new_facets)

                with timed("repopulated findings"):
                    await findings.repopulate(islice(new_findings, self.max_findings))
                    num_findings = findings.row_count
                    if num_findings == 0:
                        await details.repopulate([])


                self.sub_title = f"{self.datastore_dir} — {num_findings}/{tot_findings} findings shown"
            finally:
                # facets.disabled = False
                # findings.loading = False
                # details.loading = False
                pass

    ############################################################################
    # findings table
    ############################################################################
    def action_focus_findings(self) -> None:
        self.query_one("#findings").focus()

    @on(FindingsTable.RowHighlighted, "#findings")
    async def finding_highlighted(self, evt: FindingsTable.RowHighlighted) -> None:
        if (row_key := evt.row_key) is None:
            return

        if (finding_id := row_key.value) is None:
            return

        assert isinstance(finding_id, str)
        finding_id = FindingId(finding_id)
        # the selected finding has changed; invalidate the finding details widget
        self._finding_details_finding_id = None
        self.update_finding_details(finding_id)

    @work(exclusive=True, group="update-finding-details")
    async def update_finding_details(self, finding_id: FindingId) -> None:
        await asyncio.sleep(0.1) # hacked keyboard throttle
        await self._update_finding_details(finding_id)

    async def _update_finding_details(
        self,
        finding_id: FindingId,
        *,
        preserve_scroll_offset: bool = False,
    ) -> None:
        """
        Update the finding details pane for the given finding ID.
        Other panes and widgets are not modified.

        If `preserve_scroll_offset` is given, the scroll offset of the details
        pane will be preserved, otherwise it will be reset.
        """

        if self._finding_details_finding_id == finding_id:
            # nothing to do!
            return

        with timed("get finding details"):
            matches = await asyncio.to_thread(
                self.datastore.get_finding_details,
                self.filters,
                finding_id,
                max_matches=self.max_matches,
                max_provenance=self.max_provenance,
                suppress_redundant=self.suppress_redundant,
            )

        details = self.query_one("#details", FindingDetailsList)

        with timed("update finding details"):
            async with details.batch():
                old_offset = details.scroll_offset
                await details.repopulate(matches)
                if preserve_scroll_offset:
                    # N.B. using `_scroll_to` here instead of `scroll_to` because
                    # the latter is lazy in refreshing, causing flickering
                    details._scroll_to(x=old_offset.x, y=old_offset.y, animate=False)

        self._finding_details_finding_id = finding_id


    @on(FindingsTable.StatusSet, "#findings")
    async def finding_status_set(self, evt: FindingsTable.StatusSet) -> None:
        with (
            timed("update finding status"),
            self.app.batch_update(),
        ):
            finding_id = evt.finding_id

            # Ensure that the details of this finding are loaded.
            #
            # This is necessary because of the hacked keyboard throttle
            # mechanism in `self.update_finding_details`, which causes the
            # details to be asynchronously updated to improve app responsiveness.
            # But that added responsiveness comes at the cost of not always
            # having the details widget be fully updated when we get here.
            await self._update_finding_details(finding_id, preserve_scroll_offset=True)

            # Figure out which matches from the details pane have been scrolled
            # past.
            #
            # The reasoning for doing this, rather than marking all matches
            # accordingly, is that we only want to explicitly record the status
            # for matches that have plausibly been seen by a human reviewer. If
            # a match has not been scrolled past, it hasn't been seen, and we
            # will err on the conservative side.
            #
            # XXX We could actually be more aggressive about assigning status
            # to matches here: if two matches have the same rendered snippet,
            # they can be considered equivalent.
            details = self.query_one("#details", FindingDetailsList)
            items = details.query(FindingDetail)

            # sanity check: the details better be for the finding in question!
            for item in items:
                assert item.finding_id == finding_id

            max_index_seen = 0
            for idx in range(1, len(items)):
                item = items[idx]
                can_view = details.can_view_partial(item)
                if can_view:
                    max_index_seen = idx
                # print(f"{finding_id = } {idx = } {item.match_id = } {can_view = } {max_index_seen = }")

            match_ids = (i.match_id for i in islice(items, 0, max_index_seen + 1))
            await self._set_match_status(finding_id, evt.new_status, *match_ids)

            # the selected finding has changed; invalidate the finding details widget
            #
            # XXX the performance here could be made better if we didn't rely
            # on totally clearing the finding details widget every time some
            # aspect of it changes
            self._finding_details_finding_id = None
            await self._update_finding_details(finding_id, preserve_scroll_offset=True)

    @on(FindingsTable.CommentSet, "#findings")
    async def finding_comment_set(self, evt: FindingsTable.CommentSet) -> None:
        with timed("update finding comment"):
            await self.datastore.set_finding_comment(evt.finding_id, evt.comment)

    async def _set_match_status(
        self,
        finding_id: FindingId,
        status: MatchStatus,
        *match_ids: MatchId,
    ) -> None:
        """
        Set the status of the match IDs to the given value in the datastore,
        and update the `status` cell in the findings table for the row with the
        given finding ID.

        Each of matches referred to should belong to the given finding.
        """

        with timed(f"update match status: {finding_id = } {status = } {match_ids = }"):
            await self.datastore.set_match_status(*match_ids, status=status)
            new_finding_status = self.datastore.get_finding_status(finding_id)
            findings = self.query_one("#findings", FindingsTable)
            findings.update_row_status_cell(finding_id, new_finding_status)

    ############################################################################
    # finding details
    ############################################################################
    def action_focus_details(self) -> None:
        self.query_one("#details").focus()

    @on(FindingDetailsList.OpenSource)
    def open_match_source(self, evt: FindingDetailsList.OpenSource) -> None:
        self.app.push_screen(MatchSourceScreen(match=evt.match, blobs_dir=self.blobs_dir, datastore_root=self.datastore_dir))

    @on(FindingDetailsList.CommentSet, "#details")
    async def match_comment_set(self, evt: FindingDetailsList.CommentSet) -> None:
        with timed("update match comment"):
            await self.datastore.set_match_comment(evt.match_id, evt.comment)

    @on(FindingDetailsList.StatusSet, "#details")
    async def match_status_set(self, evt: FindingDetailsList.StatusSet) -> None:
        await self._set_match_status(evt.finding_id, evt.new_status, evt.match_id)
