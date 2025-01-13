from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal, NewType
from unicodedata import category as unicode_category

from rich.console import Group, RenderableType
from rich.markup import escape as escape_rich_markup
from rich.padding import Padding
from rich.text import Text

# The integer `match.id` from the datastore sqlite database
MatchId = NewType("MatchId", int)

# The string `finding.structural_id` from the datastore sqlite database
FindingId = NewType("FindingId", str)


@dataclass(frozen=True, repr=True, order=True)
class Finding:
    id: FindingId
    rule_name: str
    rule_text_id: str
    rule_structural_id: str
    groups: list[str]
    num_matches: int
    status: None | Literal["accept", "reject", "mixed"] = None
    comment: None | str = None
    mean_score: None | float = None


MatchStatus = None | Literal["accept", "reject"]
FindingStatus = None | Literal["accept", "reject", "mixed"]


@dataclass(repr=True)
class Match:
    id: MatchId
    finding_id: FindingId

    blob_id: str
    start_byte: int
    end_byte: int

    start_line: int
    start_column: int

    end_line: int
    end_column: int

    before_snippet: str
    matching_input: str
    after_snippet: str

    groups: list[str]

    rule_name: str

    blob_size: int
    blob_mime: None | str
    blob_charset: None | str

    score: None | float

    status: MatchStatus
    comment: None | str

    provenance: list[dict] = field(default_factory=list)

    def __rich__(self) -> RenderableType:
        preceding = escape(self.before_snippet)
        matching = escape(self.matching_input)
        trailing = escape(self.after_snippet)

        # strip until first newline to make indentation work right
        if (newline := preceding.find("\n")) >= 0:
            preceding = preceding[newline + 1 :]

        # strip until last newline to make indentation work right
        if (newline := trailing.rfind("\n")) >= 0:
            trailing = trailing[:newline]

        # FIXME: add line numbers in the left gutter
        snippet = Text.assemble(
            # "<<<",
            preceding,
            Text(matching, style="bold red"),
            trailing,
            # ">>>",
        )

        blob_id = self.blob_id
        blob_size = sizeof_fmt(self.blob_size)
        blob_mime = self.blob_mime or "unknown type"
        blob_charset = self.blob_charset or "unknown charset"

        src_range = (
            f"{self.start_line}:{self.start_column}-{self.end_line}:{self.end_column}"
        )
        score = "" if self.score is None else f"{self.score:.03f}"
        comment = "" if self.comment is None else self.comment
        status = "" if self.status is None else self.status

        parts: list[RenderableType] = []

        provenance_entries: list[RenderableType] = []

        is_first = True
        for provenance in self.provenance:
            provenance_parts: list[RenderableType] = []

            if is_first:
                is_first = False
                provenance_entries.append(rich_provenance(provenance))
            else:
                provenance_entries.append(Group(Text(), rich_provenance(provenance)))

        header_style = 'bold blue'
        parts += [
            Text.assemble(
                Text("Blob:          ", style=header_style),
                f"{blob_id}; {blob_size}; {blob_mime}; {blob_charset}",
            ),
            Text.assemble(
                Text("Location:      ", style=header_style),
                f"{src_range}, bytes {self.start_byte}-{self.end_byte}",
            ),
            Text.assemble(Text("Score:         ", style=header_style), score),
            Text.assemble(Text("Status:        ", style=header_style), status),
            Text.assemble(Text("Comment:       ", style=header_style), comment),
            Text.assemble(Text("Provenance:    ", style=header_style), "\n"),
            Padding.indent(Group(*provenance_entries), 4),
            "",
            Text.assemble(Text("Snippet:       ", style=header_style), "\n"),
            Padding.indent(snippet, 4),
        ]

        return Group(*parts)


################################################################################
# Utilities
################################################################################
def rich_provenance(provenance: dict) -> RenderableType:
    """
    Converts a JSON-parsed provenance entry into a Rich renderable.
    """

    provenance_parts: list[RenderableType] = []

    match provenance.get("kind"):
        case "file":
            provenance_parts.append(
                Text.assemble(
                    Text("Path:          ", style="bold blue"), provenance["path"]
                )
            )

        case "git_repo":
            provenance_parts.append(
                Text.assemble(
                    Text("Git repo:      ", style="bold blue"), provenance["repo_path"]
                )
            )
            if (first_commit := provenance.get("first_commit")) is not None:
                md = first_commit["commit_metadata"]
                provenance_parts.append(
                    Text.assemble(
                        Text("First commit:  ", style="bold blue"), md["commit_id"]
                    )
                )
                author = f'{md["author_name"]} {md["author_email"]}'
                provenance_parts.append(
                    Text.assemble(Text("Author:        ", style="bold blue"), author)
                )
                ts_str = md["author_timestamp"]
                ts = git_timestamp_as_iso8601(ts_str) or ts_str
                provenance_parts.append(
                    Text.assemble(Text("Date:          ", style="bold blue"), ts)
                )
                message_lines = md["message"].splitlines()
                summary = message_lines[0] if message_lines else ""
                # trim long summary lines
                if len(summary) > 80:
                    summary = summary[:80] + "…"
                provenance_parts.append(
                    Text.assemble(Text("Summary:       ", style="bold blue"), summary)
                )
                provenance_parts.append(
                    Text.assemble(
                        Text("Path:          ", style="bold blue"),
                        first_commit["blob_path"],
                    )
                )

        case "extended":
            provenance_parts.append(
                Text.assemble(Text("Extended:      ", style="bold blue"), "\n")
            )
            provenance_parts.append(
                Padding.indent(Text(json.dumps(provenance, indent=4)), 4)
            )

        case _:
            assert False

    return Group(*provenance_parts)


################################################################################
# String utilities
################################################################################
def escape(s: str, codec: str = "utf-8") -> str:
    """
    Decode a bytestring as UTF-8 on a best-effort basis, stripping ANSI codes,
    escaping non-space nonprinting characters, and escaping `rich` markup.

    >>> escape("hello")
    'hello'

    >>> escape('\x06')
    '\\\\x06'

    >>> escape('[bold red]')
    '\\\\[bold red]'
    """

    s = strip_ansi_sequences(s)
    s = escape_nonprinting(s)
    s = escape_rich_markup(s)
    return s


_ANSI_SEQUENCE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi_sequences(s: str) -> str:
    """
    Strip out 7-bit ANSI escape sequences from the given string.

    Adapted from https://stackoverflow.com/a/14693789.
    """
    return _ANSI_SEQUENCE.sub("", s)


def escape_nonprinting(s: str) -> str:
    """
    Backslash-escape nonprinting non-space characters.

    Adapted from https://stackoverflow.com/a/19016117.
    """

    def transform(ch):
        if ch.isspace() or unicode_category(ch)[0] != "C":
            return ch
        else:
            return f"\\x{ord(ch):02x}"

    return "".join(transform(ch) for ch in s)


def sizeof_fmt(num, suffix="B") -> str:
    """
    Formats a bytes quantity in human-readable form.

    Examples:

    >>> sizeof_fmt(25)
    '25.0 B'

    >>> sizeof_fmt(1025)
    '1.0 KiB'

    >>> sizeof_fmt(1500)
    '1.5 KiB'

    >>> sizeof_fmt(1024**3)
    '1.0 GiB'
    """

    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Yi{suffix}"


def git_timestamp_as_iso8601(ts: str) -> None | str:
    """
    Converts a Nosey Parker-formatted commit timestamp like "<UNIX SECONDS>
    <OFFSET>" into an ISO-8601 timestamp.

    Examples:

    >>> git_timestamp_as_iso8601('1384157507 -0800')
    '2013-11-11T00:11:47-08:00'

    >>> git_timestamp_as_iso8601('1384157507 -080')
    """

    ts_parts = ts.split()
    if len(ts_parts) != 2:
        return None

    secs_str, tz_str = ts_parts

    if len(tz_str) != 5:
        return None

    try:
        secs = int(secs_str)
        tz_hours = int(tz_str[:3])
        tz_minutes = int(tz_str[3:])
    except ValueError:
        return None

    tz = timezone(timedelta(hours=tz_hours, minutes=tz_minutes))
    dt = datetime.fromtimestamp(secs, tz)
    return dt.isoformat()
