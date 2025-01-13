import subprocess

from textwrap import dedent


def noseyparker_explorer(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['noseyparker-explorer'] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding='utf-8',
    )


EXPECTED_SHORT_HELP = dedent('''
    usage: noseyparker-explorer [-h] [--max-findings N] [--max-matches N] --datastore DIR
                   [--force-unlock] [--blobs-dir DIR] [--exclusions FILE]
                   [--version]

    noseyparker-explorer: error: the following arguments are required: --datastore/-d
''')

EXPECTED_LONG_HELP = dedent('''
    usage: noseyparker-explorer [-h] [--max-findings N] [--max-matches N] --datastore DIR
                       [--force-unlock] [--blobs-dir DIR] [--exclusions FILE]
                       [--version]

    Interactively explore and annotate findings from Nosey Parker++

    options:
      -h, --help            show this help message and exit
      --max-findings N      maximum number of findings to display in the findings
                            pane; negative means "no limit" (default: 500)
      --max-matches N       maximum number of matches to display in the findings
                            details pane; negative means "no limit" (default: 10)
      --datastore DIR, -d DIR
                            path to the Nosey Parker datastore to explore
      --force-unlock        (danger zone) forcibly unlock the datastore
      --blobs-dir DIR, -b DIR
                            path to the gathered blobs directory (default:
                            DATASTORE/blobs)
      --exclusions FILE, -x FILE
                            a file listing blob_ids to ignore
      --version, -V         show program's version number and exit
''')

def test_cli_noarg() -> None:
    p = noseyparker_explorer()
    assert p.returncode == 1
    assert p.stdout == ''
    # XXX problematic flaky test; output gets wrapped according to terminal width
    # assert p.stderr.strip() == EXPECTED_SHORT_HELP.strip()

def test_cli_help() -> None:
    p = noseyparker_explorer('--help')
    assert p.returncode == 0
    # XXX problematic flaky test; output gets wrapped according to terminal width
    # assert p.stdout.strip() == EXPECTED_LONG_HELP.strip()
    assert p.stderr == ''
