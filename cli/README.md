# bac-page v0.4.0

Build a CubeSat – CLI for the [bac.page](https://github.com/buildacubesat/bac.page) URL shortener. Each short link is a directory with an `index.html` redirect in the bac.page GitHub Pages repo; the tool writes the file, commits, and pushes.

## Install

```sh
uv tool install ./cli
bac-page --init
```

`--init` asks for the path to your local clone of the bac.page repo and writes it to `~/.config/bac/bac-page.toml`. A `BAC_PAGE_REPO` environment variable (or `--env-file PATH`) overrides the config file.

## Usage

```sh
bac-page <url> [slug] [--qr]    # create a redirect; random 8-char slug if omitted
bac-page list                   # all redirects, sorted by short name
bac-page edit                   # change slug or destination, or generate a QR code
bac-page init                   # (re)configure the repo path
```

Slugs are 1–24 characters: letters, digits, and hyphens. `add` is an optional explicit form of the create command (`bac-page add <url> [slug]`).

QR options for `add`: `--format svg|png|webp` (default svg), `--invert`, `--alpha`, `--ec L|M|Q|H` (default M), `--size PX` (default 1000), `--output DIR` (default `~`). Files are named `bac-page-<slug>.<format>`.

Standard flags: `-v/--version`, `-l/--list`, `--init`, `--config PATH`, `--env-file PATH`, `--dry-run`, `--debug` (hidden; prints tracebacks). `list` prints a table in a terminal and tab-separated `short-url<TAB>destination` lines when piped or with `--plain`.

Exit codes: 0 success, 1 runtime error, 2 bad arguments.

## Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.4.0 | 2026-08-28 | `list` (slug and destination columns) and `edit` become subcommands (`--list`/`--edit` flag forms kept as `-l/--list`; `--edit` removed). `list` sorts alphabetically by slug and renders a Rich table. Aligned with BAC Project & Tooling Guide v0.11 and Interface Design Guide v0.1: Rich output and spinner during git operations, `v`-prefixed version, `--config`/`--env-file`/`--dry-run`/`--debug` flags, TOML config at `~/.config/bac/bac-page.toml` (legacy `~/.config/bac-page/.env` still read), InquirerPy prompts with confirmation before pushes, `git mv` for renames, target URL validation, MIT license and pinned minimum dependency versions in `pyproject.toml`. Fixed slug error message (limit is 24, not 12). |
| 0.3.5 | – | `--list`, `--edit`, `--version` flags; QR generation with format, inversion, transparency, error correction, and size options; python-dotenv config. |
