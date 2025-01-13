import asyncio
from pathlib import Path

from rich.syntax import Syntax
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from .findings import Match
from .scroll import Scroll


class MatchSourceScreen(ModalScreen):
    """
    A modal screen that displays a complete source file, with highlighted lines
    corresponding to where a match is.

    FIXME: this implementation is very slow for large inputs (>1MB or so), and freezes the UI.
    FIXME: this implementation doesn't always properly scroll to the highlighted lines; probably a bug in `rich`.
    """

    def __init__(self, *args, match: Match, blobs_dir: Path, datastore_root: Path, **kwargs) -> None:
        assert isinstance(match, Match)
        assert isinstance(blobs_dir, Path)
        assert isinstance(datastore_root, Path)
        self.match = match
        self.blobs_dir = blobs_dir
        self.datastore_root = datastore_root
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        with Scroll(id="scroll"):
            yield Static(id="content")

    @staticmethod
    def _load_file_content(source: Path) -> str:
        return source.read_text(encoding='utf-8', errors='replace')

    @staticmethod
    async def _load_git_content(repo_dir: Path, blob_id: str) -> str:
        try:
            cmd = ['git', 'show', blob_id]
            # print(f'*** {cmd} cwd={repo_dir}')
            proc = await asyncio.subprocess.create_subprocess_exec(
                *cmd,
                cwd=repo_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            assert proc.returncode is not None
            if proc.returncode != 0:
                stderr_str = stderr.decode('utf-8', errors='replace')
                content = f"error running git: exit code {proc.returncode}:\n{stderr_str}"
            else:
                content = stdout.decode('utf-8', errors='replace')
        except Exception as e:
            content = f"error reading content for git repo {repo_dir} blob {blob_id}: {e}"

        return content


    async def _load_source(self) -> str:
        """
        Loads the source from a file on disk or from Git history.
        Returns the full source content decoded as utf-8.
        """

        content = f"unable to find source for {self.match.blob_id}"

        for provenance in self.match.provenance:
            match provenance.get('kind'):
                case 'file':
                    try:
                        source = provenance['path']
                        return self._load_file_content(Path(source))
                    except Exception as e:
                        content = f"error reading content for file {source}: {e}"

                case 'git_repo':
                    blob_id = self.match.blob_id
                    assert isinstance(blob_id, str)

                    # first try to load from the blobs directory, and if that fails, try to load from the git repo
                    try:
                        return self._load_file_content(self.blobs_dir / blob_id[:2] / blob_id[2:])
                    except FileNotFoundError:
                        repo_path = Path(provenance['repo_path'])

                        # if the repo path is a relative path, and appears to be within the datastore,
                        # try opening the git repo there
                        # XXX this is a sloppy heuristic
                        if not repo_path.is_absolute():
                            if self.datastore_root.parts[-1] == repo_path.parts[0]:
                                repo_path = self.datastore_root.joinpath(*repo_path.parts[1:])

                        try:
                            content = await self._load_git_content(repo_path, blob_id)
                        except Exception as e:
                            content = f"error reading content for file {source}: {e}"

        return content

    def _make_syntax(self, content: str) -> Syntax:
        # the materialized set of lines to highlight; needed for the Syntax API
        lines = set(range(self.match.start_line, self.match.end_line + 1))

        # choose a theme that is going to work with the app theme
        # sadly, `rich` themes are totally separate from textual css
        #
        # XXX note that there is a built-in `TextArea` widget in Textual now,
        # which supports textual's CSS, but that would take some engineering
        # work to switch to, and it appears that it has performance problems
        # just like this does on large single-line inputs
        theme_name = 'github-dark'
        if (theme := self.app.get_theme(self.app.theme)) is not None:
            theme_name = 'github-dark' if theme.dark else 'github-light'

        return Syntax(content, 'default', line_numbers=True, highlight_lines=lines, word_wrap=True, theme=theme_name)


    @work(exclusive=True, group="match-source-screen--mount")
    async def on_mount(self) -> None:
        try:
            self.loading = True
            source = await self._load_source()
            syntax = self._make_syntax(source)
            content = self.query_one("#content", Static)
            content.update(syntax)

            # # try to center the first match line in the scroll window
            scroll = self.query_one('#scroll', Scroll)
            y_target = max(max(self.match.start_line - 1, 0) - max(scroll.content_size.height / 2, 0), 0)
            scroll.scroll_to(y=y_target, animate=False, force=True)

        finally:
            self.loading = False



    BINDINGS = [
        Binding("escape", "close", show=False),
        Binding("q", "close", show=False),
    ]

    def action_close(self) -> None:
        self.dismiss()
