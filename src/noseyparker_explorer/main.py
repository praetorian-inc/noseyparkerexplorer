"""
An interactive review tool for Nosey Parker++ data built using Textual
"""
import argparse
import os
import sys

from pathlib import Path

from . import version


def _check_sanity() -> None:
    """
    Do some version sanity checking first thing, to try to give a meaningful
    error message if the environment will definitely *not* work
    """
    if sys.version_info < (3, 10):
        sys.exit(f'Error: this Python interpreter is version {sys.version}, '
                 f'but Python 3.10 or newer is required')

    import sqlite3
    if sqlite3.sqlite_version_info < (3, 37):
        sys.exit(f'Error: this Python interpreter includes sqlite3 version '
                 f'{sqlite3.sqlite_version}, but sqlite3 version 3.37 '
                 f'or newer is required')

    try:
        import duckdb
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(f'Error: this Python interpreter cannot import duckdb. '
                 f'Are you running under the intended Python interpreter?')


def _get_options() -> argparse.Namespace:
    """
    Parse the command-line options for the application.
    """

    p = argparse.ArgumentParser(description='Interactively explore and annotate findings from Nosey Parker')
    p.add_argument('--max-findings', metavar='N', type=int, default=500, help='maximum number of findings to display in the findings pane; non-positive means "no limit" (default: %(default)s)')
    p.add_argument('--max-matches', metavar='N', type=int, default=10, help='maximum number of matches to display in the findings details pane; non-positive means "no limit" (default: %(default)s)')
    p.add_argument('--max-provenance', metavar='N', type=int, default=3, help='maximum number of provenance entries to display in the findings details pane; non-positive means "no limit" (default: %(default)s)')
    p.add_argument('--suppress-redundant', metavar='BOOL', type=lambda x: x.lower() in ('true', '1', 'yes', 'y'), default=True, help='suppress redundant matches and findings')
    p.add_argument('--min-score', metavar='N', type=float, default=0.05, help='minimum score of findings to be displayed')
    p.add_argument('--datastore', '-d', metavar='DIR', type=Path, default=Path('datastore.np'), help='path to the Nosey Parker datastore to explore')
    p.add_argument('--force-unlock', action='store_true', help='(danger zone) forcibly unlock the datastore')
    p.add_argument('--blobs-dir', '-b', metavar='DIR', required=False, help='path to the gathered blobs directory (default: DATASTORE/blobs)')
    p.add_argument('--exclusions', '-x', metavar='FILE', required=False, help='a file listing blob_ids to ignore')
    p.add_argument('--version', '-V', action='version', version='%(prog)s v' + version)

    opts = p.parse_args()
    if opts.blobs_dir is None:
        opts.blobs_dir = opts.datastore / 'blobs'

    return opts


def main() -> None:
    """
    The entry point to Nosey Parker Explorer.
    """

    # Do argument parsing as soon as possible, before any expensive imports or
    # other checks, to make startup time with `--help` or invalid arguments as
    # fast as possible for a snappy CLI experience.
    opts = _get_options()

    # Run some environmental checks to try to fail fast with a better error
    # message if something is wrong with the runtime environment.
    _check_sanity()

    # Check if the datastore exists at all first
    if not opts.datastore.is_dir():
        sys.exit(f'Error: {opts.datastore} does not appear to be a datastore; try `--help`')

    # Nosey Parker Explorer doesn't support concurrent access to a datastore.
    # Acquire a lockfile on the datastore to try to prevent it from getting
    # clobbered by mistake (e.g., two instances of the application open at a time)
    lockfile = os.path.join(opts.datastore, '.noseyparker-explorer-lock')

    def delete_lockfile() -> None:
        try:
            os.unlink(lockfile)
        except FileNotFoundError:
            pass

    # Delete the lockfile if the `--force-unlock` option is specified.
    if opts.force_unlock:
        delete_lockfile()

    # Import these things as late as possible, again, to make the CLI snappy in
    # error-handling cases.
    import asyncio
    import filelock

    lock = filelock.FileLock(lockfile, timeout=0)
    try:
        with lock.acquire():
            try:
                # Everything checks out so far -- start the app finally!
                from .app import NoseyParkerExplorer
                NoseyParkerExplorer(
                    opts.datastore,
                    max_findings = opts.max_findings,
                    max_matches = opts.max_matches,
                    max_provenance = opts.max_provenance,
                    suppress_redundant = opts.suppress_redundant,
                    min_score = opts.min_score,
                    blobs_dir = opts.blobs_dir,
                    exclusions_file = opts.exclusions,
                ).run()
            finally:
                delete_lockfile()
    except filelock.Timeout:
        from textwrap import dedent
        sys.exit(dedent(f'''\
            Error: the datastore at {opts.datastore} is locked.
            It is most likely opened by another instance of `noseyparker-explorer`.

            If you are *sure* this is not the case, you can run with the `--force-unlock` option to unlock the datastore.'''))
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    main()
