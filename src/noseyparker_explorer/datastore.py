"""
Data model implementation helpers
"""
from __future__ import annotations

import asyncio
import json

from contextlib import asynccontextmanager
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from textwrap import dedent
from typing import Iterable

import aiosqlite
import duckdb

from .facets import FacetDefinition, FacetMetadata, FacetValue
from .filters import Filters
from .findings import Finding, FindingId, FindingStatus, Match, MatchId, MatchStatus
from .timed import timed


def decode_utf8_lossy(b: bytes) -> str:
    return b.decode('utf-8', errors='replace')


_CHUNK_SIZE: int = 1024

_FACETS = [
    FacetDefinition(
        name="Rule Name",
        column="rule_name",
        sort_order='name',
        sort_reverse=False,
    ),
    FacetDefinition(
        name="Rule ID",
        column="rule_text_id",
        sort_order='name',
        sort_reverse=False,
    ),
    FacetDefinition(
        name="Source Multimedia Type",
        column="mime_essence",
        sort_order='name',
        sort_reverse=False,
    ),
    FacetDefinition(
        name="Source Charset",
        column="charset",
        sort_order='name',
        sort_reverse=False,
    ),

    # XXX The following facets don't fit into this facet description framework now.
    #
    # Additionally, these frequently have a large number of facet values
    # (hundreds or thousands), which don't scale well with the tree-based UX.
    # Some kind of query-based filter (e.g., like GitHub search) would be a
    # better UX for these.

    # FacetDefinition(
    #     name="Git Repo",
    #     column="git_repo",
    #     sort_order='count',
    #     sort_reverse=True,
    # ),

    # FacetDefinition(
    #     name="Blob",
    #     column="blob_id",
    #     sort_order='count',
    #     sort_reverse=True,
    # ),

    # FacetDefinition(
    #     name="Provenance Type",
    #     column="provenance_type",
    #     sort_order='name',
    #     sort_reverse=False,
    # ),
]


@dataclass
class FacetFragment:
    definition: FacetDefinition
    value_constraint: str
    params: list


class DatastoreError(Exception):
    """
    Something went wrong with a datastore operation.
    """


class NoseyParkerDatastoreBuilder:
    """
    A builder for `NoseyParkerDatastore` values.

    This is split into a separate class so that the `NoseyParkerDatastore`
    class can assume that it is actually connected to the datastore. This
    allows more useful static type checking (with mypy, pyright, etc) with many
    runtime checks being avoided.
    """

    def __init__(
        self,
        dbfile: Path,
        *,
        exclusions_file: None | Path,
        max_provenance: None | int,
    ) -> None:
        # Check that the database actually exists.
        # The point of this is to avoid baffling error messages when someone
        # tries to open a nonexistent datastore: fail fast.
        try:
            with dbfile.open('rb') as infile:
                pass
        except IOError as e:
            raise DatastoreError(f'database file at {dbfile} is inaccessible') from e

        self.dbfile = dbfile
        self.exclusions_file = exclusions_file
        self.max_provenance = max_provenance

    async def connect(self) -> NoseyParkerDatastore:
        """
        Actually connect to the database.
        This needs to be called after initializing a `NoseyParkerDatastore` object.

        This two-stage initialization is needed because this connection
        operation is async, and Python __init__ methods can't be async.
        """

        # Connect to the existing datastore database, *not* creating it if it doesn't already exist
        conn = await aiosqlite.connect(f'file:{self.dbfile}?mode=rw',
                                       iter_chunk_size=_CHUNK_SIZE, uri=True)

        # avoid baffling errors by failing fast: ensure that the datastore
        # database has the expected schema version
        cur = await conn.execute("pragma user_version")
        row = await cur.fetchone()
        assert row is not None
        user_version = row[0]
        EXPECTED_SCHEMA_VERSION = 70
        if user_version != EXPECTED_SCHEMA_VERSION:
            await conn.close()
            raise DatastoreError(dedent(f'''\
                The database file at {self.dbfile} is incompatible with this version of Nosey Parker Explorer.

                The database has schema version {user_version}, but {EXPECTED_SCHEMA_VERSION} was expected.

                This version of Nosey Parker Explorer is compatible with datastores created by Nosey Parker v0.22.'''))


        # increase sqlite cache size to 2GiB
        await conn.execute(f"pragma cache_size = {-2 * 1024 * 1024}")
        # enforce foreign key checking
        await conn.execute(f"pragma foreign_keys = 1")

        def connect_ddb() -> duckdb.DuckDBPyConnection:
            ddb = duckdb.connect(':memory:')
            ddb.install_extension('sqlite')
            ddb.load_extension('sqlite')

            # XXX one _can_ expose Python functions to DuckDB, but the
            # resulting performance is really bad, as it's Python code, and
            # there's no way to release the GIL
            # ddb.create_function('decode_utf8_lossy', decode_utf8_lossy)

            if self.exclusions_file:
                exclusions = ddb.read_csv(str(self.exclusions_file), names=['blob_id'])
                filter_clause = '\nwhere blob_id not in (select blob_id from exclusions)'
            else:
                filter_clause = ''

            # attach the sqlite database in duckdb for read-only access to finding status and comments
            # XXX: there is probably sqli here
            ddb.execute(f'attach {str(self.dbfile)!r} as sqlite (type sqlite, read_only)')

            # load all matches into a single denormalized duckdb table for best speed of faceted search
            ddb.execute(dedent('''
                create table matches (
                    id integer primary key,

                    structural_id text unique not null,
                    finding_id text not null,

                    blob_id text not null,
                    blob_id_int integer not null,

                    start_byte integer not null,
                    end_byte integer not null,

                    start_line integer not null,
                    start_column integer not null,
                    end_line integer not null,
                    end_column integer not null,

                    rule_name text not null,
                    rule_text_id text not null,
                    rule_structural_id text not null,

                    groups blob[] not null,

                    before_snippet blob not null,
                    matching_input blob not null,
                    after_snippet blob not null,

                    status text,
                    comment text,
                    score real,

                    mime_essence text,
                    charset text,
                    size integer,

                    blob_provenance varchar[],
                    redundant_to integer[],
                );
                '''))

            ddb.execute(dedent('''
                insert into matches
                -- XXX This is copypasta from Nosey Parker's `match_denorm` view, which DuckDB doesn't natively correctly understand.
                select
                    m.id,

                    m.structural_id,
                    f.finding_id,

                    b.blob_id,
                    b.id,

                    m.start_byte,
                    m.end_byte,

                    bss.start_line,
                    bss.start_column,
                    bss.end_line,
                    bss.end_column,

                    r.name,
                    r.text_id,
                    r.structural_id,

                    list_transform(
                        from_json_strict(f.groups, '"text[]"'),
                        v -> from_base64(v)
                    ),

                    before_snippet.snippet,
                    matching_snippet.snippet,
                    after_snippet.snippet,

                    match_status.status,
                    match_comment.comment,
                    match_score.score,

                    bme.mime_essence,
                    bcs.charset,
                    b.size,
                    (
                        select coalesce(list(provenance), []::varchar[])[:?]
                        from sqlite.blob_provenance bp
                        where bp.blob_id = m.blob_id
                    ),
                    (
                        select coalesce(list(redundant_to), []::integer[])
                        from sqlite.match_redundancy mr
                        where mr.match_id = m.id
                    ),
                from
                    sqlite.match m
                    inner join sqlite.finding f on (m.finding_id = f.id)
                    inner join sqlite.blob_source_span bss on (m.blob_id = bss.blob_id and m.start_byte = bss.start_byte and m.end_byte = bss.end_byte)
                    inner join sqlite.blob b on (m.blob_id = b.id)
                    inner join sqlite.rule r on (f.rule_id = r.id)
                    inner join sqlite.snippet before_snippet on (m.before_snippet_id = before_snippet.id)
                    inner join sqlite.snippet matching_snippet on (m.matching_snippet_id = matching_snippet.id)
                    inner join sqlite.snippet after_snippet on (m.after_snippet_id = after_snippet.id)
                    left outer join sqlite.match_status on (m.id = match_status.match_id)
                    left outer join sqlite.match_comment on (m.id = match_comment.match_id)
                    left outer join sqlite.match_score on (m.id = match_score.match_id)
                    left outer join sqlite.blob_mime_essence bme on (b.id = bme.blob_id)
                    left outer join sqlite.blob_charset bcs on (b.id = bcs.blob_id)
                ''' + filter_clause), [self.max_provenance])

            return ddb

        ddb = await asyncio.to_thread(connect_ddb)
        return NoseyParkerDatastore(self.dbfile, self.exclusions_file, ddb, conn)


class NoseyParkerDatastore:
    """
    An abstraction around a Nosey Parker datastore.
    """

    ############################################################################
    # basics
    ############################################################################
    def __init__(
        self,
        dbfile: Path,
        exclusions_file: None | Path,
        ddb: duckdb.DuckDBPyConnection,
        conn: aiosqlite.Connection,
    ) -> None:
        """
        Create a new `NoseyParkerDatastore` value.
        Only intended to be called by `NoseyParkerDatastoreBuilder`.
        """

        self.dbfile = dbfile
        self.exclusions_file = exclusions_file

        # We have a lock used to prevent multiple coroutines from trying to
        # open a transaction at once.
        #
        # SQL transactions need to be atomic also as far as the Python code is
        # concerned, as this datastore opens only a single connection to the
        # database which is shared among all coroutines.
        #
        # It turns out that when you are using `async`, you very quickly can
        # run into all the same synchronization issues that you get when you
        # use regular threads!
        self._tx_lock = asyncio.Lock()
        self._ddb = ddb
        self._conn = conn



    async def close(self) -> None:
        """
        Explicitly close the datastore.
        """

        if self._ddb:
            self._ddb.close()

        if self._conn:
            await self._conn.close()

    ############################################################################
    # backup
    ############################################################################
    async def backup(self, dest_dbfile: str) -> None:
        async with aiosqlite.connect(dest_dbfile) as dest_conn:
            await self._conn.backup(dest_conn)

    ############################################################################
    # implementation helpers
    ############################################################################
    @asynccontextmanager
    async def _cursor(self, arraysize: int = _CHUNK_SIZE):
        async with self._conn.cursor() as cur:
            cur.arraysize = arraysize
            yield cur

    @asynccontextmanager
    async def _transaction(self, arraysize: int = _CHUNK_SIZE):
        async with (
            self._tx_lock,
            self._cursor(arraysize=arraysize) as cur,
        ):
            await cur.execute("begin")
            try:
                yield cur
            except:
                await self._conn.rollback()
                raise
            else:
                await self._conn.commit()


    @staticmethod
    def _constrain(facet_frags: list[FacetFragment]) -> tuple[str, list]:
        """
        Generate a SQL expression with placeholders that is equivalent to the
        conjunction of the given filter query fragments, and a list of the
        parameters to supply when ultimatley executing the SQL query.
        """
        if not facet_frags:
            return "true", []

        constraints, param_lists = [], []
        for f in facet_frags:
            dfn = f.definition
            constraints.append(f.value_constraint)
            param_lists.append(f.params)

        constraint = " and ".join(constraints)
        # constraint = f"({constraint})"
        params = [p for ps in param_lists for p in ps]

        return constraint, params



    def _get_filter_query_fragments(self, filters: Filters) -> list[FacetFragment]:
        facet_frags: list[FacetFragment] = []

        by_dfn = lambda f: f.definition
        dfn_groups = groupby(sorted(filters.facets, key=by_dfn), by_dfn)
        for dfn, facet_values in dfn_groups:
            clauses, params = [], []
            for facet_value in facet_values:
                if facet_value.value is None:
                    clauses.append(f"{dfn.column} is null")
                else:
                    clauses.append(f"{dfn.column} = ?")
                    params.append(facet_value.value)

            value_constraint = " or ".join(clauses)
            value_constraint = f"({value_constraint})"

            facet_frags.append(FacetFragment(
                definition=dfn,
                value_constraint=value_constraint,
                params=params,
            ))

        return facet_frags



    ############################################################################
    # persistence of match status
    ############################################################################
    async def set_match_status(self, *match_ids: MatchId, status: MatchStatus) -> None:
        """
        Record the given status for each of the matches into the datastore.
        """

        async with self._transaction() as cur:

            if status is None:
                query = dedent("""
                    delete from match_status
                    where match_id = ?
                    """)
                # print("MATCH STATUS QUERY:", query)
                # print("MATCH STATUS PARAMS:", [match_ids, status])
                await cur.executemany(query, ((match_id, ) for match_id in match_ids))
            else:
                query = dedent("""
                    insert or replace into match_status(match_id, status)
                    values (?, ?)
                    """)
                # print("MATCH STATUS QUERY:", query)
                # print("MATCH STATUS PARAMS:", [match_ids, status])
                await cur.executemany(query, ((match_id, status) for match_id in match_ids))

            try:
                self._ddb.begin()
                self._ddb.executemany(dedent("""
                    update matches
                    set status = ?
                    where id = ?
                    """), [(status, match_id) for match_id in match_ids])
            except:
                self._ddb.rollback()
                raise
            else:
                self._ddb.commit()

    ############################################################################
    # persistence of finding comment
    ############################################################################
    async def set_finding_comment(self, finding_id: FindingId, comment: None | str) -> None:
        """
        Record a comment for the finding with given id into the datastore.
        """

        async with self._transaction() as cur:
            params: list[str]
            if not comment:
                query = dedent("""
                    delete from finding_comment
                    where finding_id in (select id from finding where finding_id = ?)
                    """)
                params = [finding_id]
            else:
                query = dedent("""
                    insert or replace into finding_comment(finding_id, comment)
                    select f.id, ?
                    from finding f
                    where f.finding_id = ?
                    """)
                params = [comment, finding_id]

            # print("FINDING COMMENT QUERY:", query)
            # print("FINDING COMMENT PARAMS:", params)

            await cur.execute(query, params)

    ############################################################################
    # persistence of match comment
    ############################################################################
    async def set_match_comment(self, match_id: MatchId, comment: None | str) -> None:
        """
        Record a comment for the match with given id into the datastore.
        """

        async with self._transaction() as cur:
            params: list
            if not comment:
                query = dedent("""
                    delete from match_comment
                    where match_id = ?
                    """)
                params = [match_id]
            else:
                query = dedent("""
                    insert or replace into match_comment(match_id, comment)
                    values (?, ?)
                    """)
                params = [match_id, comment]

            # print("MATCH COMMENT QUERY:", query)
            # print("MATCH COMMENT PARAMS:", params)

            await cur.execute(query, params)

            try:
                self._ddb.begin()
                self._ddb.execute(dedent("""
                    update matches
                    set comment = ?
                    where id = ?
                    """), (comment, match_id))
            except:
                self._ddb.rollback()
                raise
            else:
                self._ddb.commit()


    ############################################################################
    # facets
    ############################################################################
    def get_facets(
        self,
        filters: Filters,
        *,
        suppress_redundant: bool,
    ) -> list[tuple[FacetDefinition, list[tuple[FacetValue, FacetMetadata]]]]:
        """
        Given a set of active filters, recompute the facet value counts.
        """
        if suppress_redundant:
            redundant_constraint = 'len(redundant_to) = 0'
        else:
            redundant_constraint = 'true'

        facet_frags = self._get_filter_query_fragments(filters)

        def get_facet(dfn: FacetDefinition) -> list[tuple[FacetValue, FacetMetadata]]:
            constraint, params = self._constrain([f for f in facet_frags if f.definition != dfn])

            if constraint == "true":
                count_expr = "1"
            else:
                count_expr = f"case {constraint} when true then 1 else 0 end"

            direction = 'desc' if dfn.sort_reverse else 'asc'

            if dfn.sort_order == 'name':
                order_by = f'1 {direction}'
            elif dfn.sort_order == 'count':
                order_by = f'2 {direction}, 1'
            else:
                assert False, f'unknown sort order {dfn.sort_order}'

            query = dedent(f"""
                with
                    summarized as (
                        select
                            {dfn.column} val,
                            sum({count_expr}) cnt,
                            avg(score) mean_score,
                        from matches
                        where {redundant_constraint}
                        group by 1, finding_id
                    )
                select val, sum(case cnt when 0 then 0 else 1 end)
                from summarized
                where mean_score is null or mean_score >= {filters.min_score}
                group by 1
                order by {order_by}
                """)

            # print("FACETS QUERY:", query)
            # print("FACETS PARAMS:", params)

            values = []

            cur = self._ddb.cursor()
            cur.execute(query, params)
            while rows := cur.fetchmany(_CHUNK_SIZE):
                for value, count in rows:
                    values.append((
                        FacetValue(definition=dfn, value=value),
                        FacetMetadata(count=count),
                    ))
            return values

        facet_values = []
        for dfn in _FACETS:
            with timed(f"facet: {dfn.name}"):
                facet_values.append((dfn, get_facet(dfn)))
        return facet_values


    ############################################################################
    # findings
    ############################################################################
    def get_total_num_findings(self, filters: Filters, *, suppress_redundant: bool) -> int:
        """
        How many findings are there, total, in the datastore?
        """

        if suppress_redundant:
            redundant_constraint = 'len(redundant_to) = 0'
        else:
            redundant_constraint = 'true'

        cur = self._ddb.execute(f'''
            with
                finding_score as (
                    select finding_id, avg(score) mean_score
                    from matches
                    where {redundant_constraint}
                    group by finding_id
                )
            select count(*) from finding_score
            where mean_score is null or mean_score >= {filters.min_score}
            ''')
        row = cur.fetchone()
        assert row is not None
        return row[0]

    def get_findings(self, filters: Filters, *, suppress_redundant: bool) -> Iterable[Finding]:
        """
        Given a set of active filters, get the corresponding findings.
        """

        facet_frags = self._get_filter_query_fragments(filters)
        constraint, params = self._constrain(facet_frags)

        if suppress_redundant:
            redundant_constraint = 'len(redundant_to) = 0'
        else:
            redundant_constraint = 'true'

        query = dedent(f"""
            with
                findings as (
                    select
                        finding_id,
                        rule_structural_id,
                        groups,
                        min(rule_text_id) rule_text_id,
                        min(rule_name) rule_name,
                        count(*) num_matches,
                        avg(score) mean_score,
                        list(distinct status order by status) filter (where status is not null) statuses,
                    from matches
                    where {constraint}
                      and {redundant_constraint}
                    group by all
                )
            select
                f.finding_id,
                f.rule_structural_id,
                f.rule_text_id,
                f.rule_name,
                f.groups,
                f.num_matches,
                case
                    when len(f.statuses) > 1 then 'mixed'
                    when f.statuses = ['accept'] then 'accept'
                    when f.statuses = ['reject'] then 'reject'
                end status,
                fc.comment,
                f.mean_score,
            from
                findings f
                inner join sqlite.finding sf on (sf.finding_id = f.finding_id)
                left outer join sqlite.finding_comment fc on (fc.finding_id = sf.id)
            where f.mean_score is null or f.mean_score >= {filters.min_score}
            order by f.rule_name, f.rule_text_id, f.rule_structural_id, f.mean_score desc, f.groups, f.num_matches, status, fc.comment
            """)

        # print("FINDINGS QUERY:", query)
        # print("FINDINGS PARAMS:", params)

        cur = self._ddb.cursor()
        cur.execute(query, params)
        while rows := cur.fetchmany(_CHUNK_SIZE):
            # print('got batch')
            for r in rows:
                yield Finding(
                    id=r[0],
                    rule_structural_id=r[1],
                    rule_text_id=r[2],
                    rule_name=r[3],
                    groups=[decode_utf8_lossy(s) for s in r[4]],
                    num_matches=r[5],
                    status=r[6],
                    comment=r[7],
                    mean_score=r[8],
                )

    def get_finding_status(self, finding_id: FindingId) -> FindingStatus:
        """
        Get the status associated with the finding with the given ID.
        """
        query = dedent(f"""
            with
                findings as (
                    select
                        list(distinct status order by status)
                            filter (where status is not null) statuses
                    from matches
                    where finding_id = ?
                    group by all
                )
            select
                case
                    when len(f.statuses) > 1 then 'mixed'
                    when f.statuses = ['accept'] then 'accept'
                    when f.statuses = ['reject'] then 'reject'
                end status,
            from findings f
            """)
        params = [finding_id]

        # print("FINDINGS STATUS QUERY:", query)
        # print("FINDINGS STATUS PARAMS:", params)

        cur = self._ddb.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        assert row is not None
        return row[0]

    ############################################################################
    # finding details
    ############################################################################
    def get_finding_details(
        self,
        filters: Filters,
        finding_id: FindingId,
        *,
        max_matches: None | int,
        max_provenance: None | int,
        suppress_redundant: bool,
    ) -> list[Match]:

        """
        Get the set of matches corresponding to a given finding.
        """

        fragments = self._get_filter_query_fragments(filters)
        constraint, constraint_params = self._constrain(fragments)

        if suppress_redundant:
            redundant_constraint = 'len(m.redundant_to) = 0'
        else:
            redundant_constraint = 'true'

        query = dedent(f"""
            select
                m.id,
                m.blob_id,
                m.start_byte,
                m.end_byte,

                m.start_line,
                m.start_column,
                m.end_line,
                m.end_column,

                m.before_snippet,
                m.matching_input,
                m.after_snippet,

                m.groups,

                m.rule_name,

                m.size,
                m.mime_essence,
                m.charset,
                m.score,

                ms.status,
                mc.comment,

                m.blob_provenance,

            from
                matches m
                left outer join sqlite.match_status ms on m.id = ms.match_id
                left outer join sqlite.match_comment mc on m.id = mc.match_id

            where finding_id = ?
              and {constraint}
              and {redundant_constraint}
            order by m.blob_id, m.start_byte, m.end_byte
            """)

        params: list = [finding_id] + constraint_params

        if max_matches is not None:
            query += 'limit ?'
            params.append(max_matches)

        # print("DETAILS QUERY:", query)
        # print("DETAILS PARAMS:", params)

        result = []
        cur = self._ddb.cursor()
        cur.execute(query, params)
        while rows := cur.fetchmany(_CHUNK_SIZE):
            for row in rows:
                result.append(Match(
                    id=row[0],
                    finding_id=finding_id,
                    blob_id=row[1],
                    start_byte=row[2],
                    end_byte=row[3],
                    start_line=row[4],
                    start_column=row[5],
                    end_line=row[6],
                    end_column=row[7],
                    before_snippet=decode_utf8_lossy(row[8]),
                    matching_input=decode_utf8_lossy(row[9]),
                    after_snippet=decode_utf8_lossy(row[10]),
                    groups=[decode_utf8_lossy(s) for s in row[11]],
                    rule_name=row[12],
                    blob_size=row[13],
                    blob_mime=row[14],
                    blob_charset=row[15],
                    score=row[16],
                    status=row[17],
                    comment=row[18],
                    provenance=[json.loads(p) for p in row[19]],
                ))
        return result
