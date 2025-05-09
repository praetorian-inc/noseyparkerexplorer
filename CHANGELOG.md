# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project aspires to use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each version of Nosey Parker Explorer corresponds to a version of [Nosey Parker](https://github.com/praetorian-inc/noseyparker).
In general, you want to use matching versions of the tools.
So, for example, use v0.23 of Nosey Parker Explorer when working with datastores produced by v0.23.0 of Nosey Parker.


## [v0.24.0](https://github.com/praetorian-inc/noseyparkerexplorer/releases/v0.24.0) (2025-05-09)

**NOTE: This version of Nosey Parker Explorer works with datastores created by [Nosey Parker v0.24](https://github.com/praetorian-inc/noseyparker/releases/v0.24.0).**

### Changes

- Dependencies have been updated to the latest versions:
    - `aiosqlite>=0.21.0`
    - `duckdb>=1.2.2`
    - `filelock>=3.18.0`
    - `rich>=14.0.0`
    - `textual>=3.2.0`


## [v0.23.0](https://github.com/praetorian-inc/noseyparkerexplorer/releases/v0.23.0) (2025-01-28)

**NOTE: This version of Nosey Parker Explorer works with datastores created by [Nosey Parker v0.23](https://github.com/praetorian-inc/noseyparker/releases/v0.23.0).**

This is the initial public release of Nosey Parker Explorer.
It is a terminal UI (TUI) application that provides a simple interactive filtering and annotation mechanism for results from [Nosey Parker](https://github.com/praetorian-inc/noseyparker).
It is built using the [Textual](https://textual.textualize.io) framework for Python.
