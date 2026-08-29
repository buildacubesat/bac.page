"""bac-page – create and manage bac.page short URLs.

Build a CubeSat – URL shortener CLI. Implementation follows the BAC Project &
Tooling Guide (v0.11); terminal presentation follows the BAC Interface Design
Guide (v0.1) §10.
"""

import argparse
import os
import random
import re
import string
import subprocess
import sys
import tomllib
import traceback
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

TOOL = "bac-page"
DOMAIN = "bac.page"
UID_LENGTH = 8
SLUG_MAX = 24
SLUG_PATTERN = re.compile(rf"^[a-zA-Z0-9-]{{1,{SLUG_MAX}}}$")
DEFAULT_CONFIG = Path.home() / ".config" / "bac" / "bac-page.toml"
LEGACY_ENV = Path.home() / ".config" / "bac-page" / ".env"
COMMANDS = ("add", "list", "edit", "init")

# Rich colour markup – literal copies of the BAC Identity tokens, per Interface Guide §10.1.
OK = "[#84C45A]✓[/]"
ERR = "[#CE6C63]ERROR[/]"
WARN = "[#F7D400]![/]"

try:
    VERSION = "v" + version(TOOL)
except PackageNotFoundError:
    VERSION = "v0.0.0-dev"

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_env(env_file: Path | None) -> None:
    if env_file:
        if not env_file.exists():
            raise SystemExit(f"Env file not found: {env_file}")
        load_dotenv(dotenv_path=env_file, override=True)
    else:
        load_dotenv()
        if LEGACY_ENV.exists():
            load_dotenv(dotenv_path=LEGACY_ENV)


def load_config(path: Path | None) -> dict:
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG
    if not config_path.exists():
        return {}
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def save_config(path: Path | None, repo: Path) -> Path:
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "# bac-page.toml\n"
        "# Build a CubeSat – bac-page configuration\n"
        "\n"
        "[repo]\n"
        f'path = "{repo}"\n'
    )
    return config_path


def get_repo_path(config_path: Path | None) -> Path:
    """Resolve the bac.page repo: BAC_PAGE_REPO env var, then the TOML config."""
    repo = os.environ.get("BAC_PAGE_REPO")
    if not repo:
        repo = load_config(config_path).get("repo", {}).get("path")
    if not repo:
        raise SystemExit(f"{TOOL} is not configured.\n       Run `{TOOL} --init` to set the repo path.")
    path = Path(repo).expanduser().resolve()
    if not path.is_dir():
        raise SystemExit(f"Repo path does not exist: {path}\n       Run `{TOOL} --init` to update it.")
    return path


def cmd_init(args: argparse.Namespace) -> None:
    from InquirerPy import inquirer

    current = load_config(args.config).get("repo", {}).get("path") or os.environ.get("BAC_PAGE_REPO")
    console.print(f"[bold]Build a CubeSat – {TOOL} {VERSION}[/bold]\n")
    path_str = inquirer.text(
        message="Path to the bac.page git repo:",
        default=current or str(Path.home() / "repos" / "bac.page"),
    ).execute().strip()
    repo = Path(path_str).expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"Directory does not exist: {repo}")
    if not (repo / ".git").exists():
        console.print(f"  {WARN} {repo} does not appear to be a git repository.")
    if args.dry_run:
        console.print(f"  Would write [cyan]{args.config or DEFAULT_CONFIG}[/] [dim](dry run – no changes made)[/dim]")
        return
    written = save_config(args.config, repo)
    console.print(f"  {OK} Config saved to [cyan]{written}[/]")


# ---------------------------------------------------------------------------
# Redirect files
# ---------------------------------------------------------------------------

def generate_uid() -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=UID_LENGTH))


def redirect_html(target: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={target}">
  <link rel="canonical" href="{target}">
  <title>Redirecting…</title>
</head>
<body>
  <p>Redirecting to <a href="{target}">{target}</a></p>
  <script>window.location.replace({target!r});</script>
</body>
</html>
"""


def short_url(slug: str) -> str:
    return f"https://{DOMAIN}/{slug}"


def slug_exists(repo_path: Path, slug: str) -> bool:
    return (repo_path / slug / "index.html").exists()


def validate_slug(repo_path: Path, slug: str) -> None:
    if not SLUG_PATTERN.match(slug):
        raise SystemExit(
            f"Invalid slug: {slug!r}\n"
            f"       Use 1–{SLUG_MAX} characters: letters, digits, and hyphens."
        )
    if slug_exists(repo_path, slug):
        raise SystemExit(f"/{slug} already exists.\n       Run `{TOOL} list` to see current redirects.")


def validate_target(target: str) -> None:
    if not re.match(r"^https?://\S+$", target):
        raise SystemExit(f"Target must be an http(s) URL: {target!r}")


def create_redirect(repo_path: Path, slug: str, target: str) -> None:
    slug_dir = repo_path / slug
    slug_dir.mkdir(exist_ok=True)
    (slug_dir / "index.html").write_text(redirect_html(target))


def parse_target(index_html: Path) -> str | None:
    m = re.search(r'content="0; url=([^"]+)"', index_html.read_text())
    return m.group(1) if m else None


def list_redirects(repo_path: Path) -> list[tuple[str, str]]:
    """Return (slug, target) pairs sorted alphabetically by slug (case-insensitive)."""
    entries = []
    for d in repo_path.iterdir():
        if not d.is_dir() or d.name.startswith(".") or d.name == "cli":
            continue
        index = d / "index.html"
        if index.exists():
            target = parse_target(index)
            if target:
                entries.append((d.name, target))
    return sorted(entries, key=lambda e: (e[0].lower(), e[0]))


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def git(repo_path: Path, *argv: str) -> None:
    result = subprocess.run(["git", *argv], cwd=repo_path, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\n", "\n       ")
        hint = ""
        if argv[0] in ("pull", "push"):
            hint = f"\n       The repo at {repo_path} may have a local commit that is not pushed."
        raise SystemExit(f"git {argv[0]} failed.\n       {detail}{hint}")


def git_commit_push(repo_path: Path, message: str, *paths: Path) -> None:
    with console.status("Committing and pushing…", spinner="dots"):
        for p in paths:
            git(repo_path, "add", str(p))
        git(repo_path, "commit", "-m", message)
        git(repo_path, "pull", "--rebase")
        git(repo_path, "push")


# ---------------------------------------------------------------------------
# QR codes
# ---------------------------------------------------------------------------

def generate_qr(
    url: str,
    slug: str,
    fmt: str,
    invert: bool,
    alpha: bool,
    ec: str,
    output: Path | None,
    size: int = 1000,
) -> Path:
    import qrcode
    import qrcode.constants

    ec_map = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }

    dest = (output or Path.home()).expanduser() / f"bac-page-{slug}.{fmt}"

    qr = qrcode.QRCode(error_correction=ec_map[ec], box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)

    if fmt == "svg":
        import qrcode.image.svg

        img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        svg_data = img.to_string().decode()
        svg_data = re.sub(r'(<svg[^>]*)(width="[^"]*")', f'\\1width="{size}"', svg_data)
        svg_data = re.sub(r'(<svg[^>]*)(height="[^"]*")', f'\\1height="{size}"', svg_data)
        if invert:
            svg_data = svg_data.replace('fill="#000000"', 'fill="TEMP"')
            svg_data = svg_data.replace('fill="#ffffff"', 'fill="#000000"')
            svg_data = svg_data.replace('fill="TEMP"', 'fill="#ffffff"')
        if alpha:
            svg_data = re.sub(r"<rect[^/]*/>", "", svg_data, count=1)
        dest.write_text(svg_data)
    else:
        import numpy as np
        from PIL import Image

        fg = (255, 255, 255) if invert else (0, 0, 0)
        bg = (0, 0, 0) if invert else (255, 255, 255)
        img = qr.make_image(fill_color=fg, back_color=bg).convert("RGB")
        img = img.resize((size, size), Image.NEAREST)
        if alpha:
            arr = np.array(img)
            rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
            rgba[..., :3] = arr
            bg_mask = (arr[:, :, 0] == bg[0]) & (arr[:, :, 1] == bg[1]) & (arr[:, :, 2] == bg[2])
            rgba[..., 3] = np.where(bg_mask, 0, 255)
            img = Image.fromarray(rgba, "RGBA")
        img.save(dest, **({"format": "WEBP"} if fmt == "webp" else {}))

    return dest


def prompt_qr_params() -> dict:
    from InquirerPy import inquirer

    fmt = inquirer.select(message="Format:", choices=["svg", "png", "webp"], default="svg").execute()
    invert = inquirer.confirm(message="Invert (white on black)?", default=False).execute()
    alpha = inquirer.confirm(message="Transparent background?", default=False).execute()
    ec = inquirer.select(message="Error correction:", choices=["L", "M", "Q", "H"], default="M").execute()
    size = inquirer.number(message="Size in pixels:", default=1000, min_allowed=64).execute()
    output = inquirer.text(message="Output directory:", default="~").execute().strip()
    return {"fmt": fmt, "invert": invert, "alpha": alpha, "ec": ec, "size": int(size), "output": Path(output)}


def emit_qr(url: str, slug: str, params: dict, dry_run: bool) -> None:
    if dry_run:
        dest = (params["output"] or Path.home()).expanduser() / f"bac-page-{slug}.{params['fmt']}"
        console.print(f"  Would write QR code to [cyan]{dest}[/]")
        return
    qr_path = generate_qr(url, slug, **params)
    console.print(f"  {OK} QR code saved to [cyan]{qr_path}[/]")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> None:
    repo_path = get_repo_path(args.config)
    target = args.url
    validate_target(target)

    if args.slug:
        slug = args.slug
        validate_slug(repo_path, slug)
    else:
        slug = generate_uid()
        while slug_exists(repo_path, slug):
            slug = generate_uid()

    url = short_url(slug)
    qr_params = {
        "fmt": args.fmt, "invert": args.invert, "alpha": args.alpha,
        "ec": args.ec, "size": args.size, "output": args.output,
    }

    if args.dry_run:
        console.print(f"  Would create [cyan]{url}[/] → {target} [dim](dry run – no changes made)[/dim]")
        if args.qr:
            emit_qr(url, slug, qr_params, dry_run=True)
        return

    create_redirect(repo_path, slug, target)
    git_commit_push(repo_path, f"add redirect: /{slug} → {target}", repo_path / slug)
    console.print(f"  {OK} [cyan]{url}[/] → {target}")

    if args.qr:
        emit_qr(url, slug, qr_params, dry_run=False)


def cmd_list(args: argparse.Namespace) -> None:
    repo_path = get_repo_path(args.config)
    redirects = list_redirects(repo_path)
    if not redirects:
        console.print("No redirects found.")
        return

    if args.plain or not console.is_terminal:
        for slug, target in redirects:
            print(f"{short_url(slug)}\t{target}")
        return

    table = Table(title=f"{DOMAIN} redirects ({len(redirects)})", title_justify="left")
    table.add_column("Slug", style="cyan", no_wrap=True)
    table.add_column("Destination", overflow="ellipsis", no_wrap=True)
    for slug, target in redirects:
        table.add_row(f"/{slug}", target)
    console.print(table)


def cmd_edit(args: argparse.Namespace) -> None:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice

    repo_path = get_repo_path(args.config)
    redirects = list_redirects(repo_path)
    if not redirects:
        console.print("No redirects found.")
        return

    # Match on the slug only – matching on destinations makes typing a slug pick the wrong entry.
    choices = [Choice(value=i, name=f"/{s}") for i, (s, _) in enumerate(redirects)]
    picked = inquirer.fuzzy(message="Redirect to edit:", choices=choices, max_height="70%").execute()
    slug, target = redirects[picked]
    url = short_url(slug)
    console.print(f"  [cyan]{url}[/] → {target}")

    action = inquirer.select(
        message=f"/{slug}:",
        choices=[
            Choice("slug", name="Change slug"),
            Choice("target", name="Change destination URL"),
            Choice("qr", name="Generate QR code"),
            Choice("cancel", name="Cancel"),
        ],
        default="target",
    ).execute()

    if action == "cancel":
        console.print("Cancelled.")
        return

    if action == "qr":
        emit_qr(url, slug, prompt_qr_params(), args.dry_run)
        return

    if action == "slug":
        new_slug = inquirer.text(message="New slug:", default=slug).execute().strip()
        if new_slug == slug:
            console.print("Unchanged.")
            return
        validate_slug(repo_path, new_slug)
        console.print(f"  [cyan]{url}[/] → [cyan]{short_url(new_slug)}[/]")
        if args.dry_run:
            console.print("  [dim](dry run – no changes made)[/dim]")
            return
        if not inquirer.confirm(message="Rename and push?", default=False).execute():
            console.print("Aborted.")
            return
        with console.status("Committing and pushing…", spinner="dots"):
            git(repo_path, "mv", slug, new_slug)
            git(repo_path, "commit", "-m", f"rename redirect: /{slug} → /{new_slug}")
            git(repo_path, "pull", "--rebase")
            git(repo_path, "push")
        console.print(f"  {OK} [cyan]{short_url(new_slug)}[/] → {target}")
        console.print(f"  {WARN} Existing QR codes and links to /{slug} no longer resolve.")
        return

    if action == "target":
        new_target = inquirer.text(message="New destination URL:", default=target).execute().strip()
        if new_target == target:
            console.print("Unchanged.")
            return
        validate_target(new_target)
        console.print(f"  [cyan]{url}[/]\n    [dim]{target}[/dim]\n    → {new_target}")
        if args.dry_run:
            console.print("  [dim](dry run – no changes made)[/dim]")
            return
        if not inquirer.confirm(message="Update and push?", default=False).execute():
            console.print("Aborted.")
            return
        create_redirect(repo_path, slug, new_target)
        git_commit_push(repo_path, f"update redirect: /{slug} → {new_target}", repo_path / slug)
        console.print(f"  {OK} [cyan]{url}[/] → {new_target}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

USAGE = f"""{TOOL} [options] <url> [slug]
       {TOOL} [options] {{add,list,edit,init}} ..."""

DESCRIPTION = "Create and manage bac.page short URLs."

EPILOG = f"""commands:
  <url> [slug]     create a redirect (same as `add`); slug is 1–{SLUG_MAX} chars, random if omitted
  list             list all redirects, sorted by short name
  edit             edit a redirect: change slug, change destination, generate QR code
  init             configure the bac.page repo path (same as --init)

examples:
  {TOOL} https://buildacubesat.space/docs/eps eps-docs --qr
  {TOOL} list
  {TOOL} edit --dry-run
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL,
        usage=USAGE,
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-v", "--version", action="version", version=f"{TOOL} {VERSION}")
    p.add_argument("-l", "--list", action="store_true", help="same as `list`")
    p.add_argument("--init", action="store_true", help="same as `init`")
    p.add_argument("--config", type=Path, metavar="PATH", help="config file (default: ~/.config/bac/bac-page.toml)")
    p.add_argument("--env-file", type=Path, metavar="PATH", help="load a specific .env file")
    p.add_argument("--dry-run", action="store_true", help="show what would happen; write and push nothing")
    p.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    return p


def build_add_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"{TOOL} add", description="Create a redirect and push it.")
    p.add_argument("url", help="target URL to redirect to")
    p.add_argument("slug", nargs="?", help=f"custom slug, 1–{SLUG_MAX} letters/digits/hyphens (default: random)")
    p.add_argument("--qr", action="store_true", help="also generate a QR code for the short URL")
    p.add_argument("--format", choices=["png", "svg", "webp"], default="svg", dest="fmt", help="QR format (default: svg)")
    p.add_argument("--invert", action="store_true", help="white on black")
    p.add_argument("--alpha", action="store_true", help="transparent background")
    p.add_argument("--ec", choices=["L", "M", "Q", "H"], default="M", help="error correction level (default: M)")
    p.add_argument("--size", type=int, default=1000, help="QR size in pixels (default: 1000)")
    p.add_argument("--output", type=Path, default=None, metavar="DIR", help="QR output directory (default: ~)")
    return p


def build_list_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"{TOOL} list", description="List all redirects, sorted by short name.")
    p.add_argument("--plain", action="store_true", help="tab-separated output, no table (automatic when piped)")
    return p


def build_simple_parser(name: str, description: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=f"{TOOL} {name}", description=description)


def parse(argv: list[str]) -> tuple[str, argparse.Namespace]:
    parser = build_parser()
    args, rest = parser.parse_known_args(argv)

    if args.init:
        command = "init"
    elif args.list:
        command = "list"
    elif rest and rest[0] in COMMANDS:
        command = rest.pop(0)
    elif rest and not rest[0].startswith("-"):
        command = "add"
    else:
        parser.print_help()
        raise SystemExit(2)

    sub = {
        "add": build_add_parser,
        "list": build_list_parser,
        "edit": lambda: build_simple_parser("edit", "Edit an existing redirect."),
        "init": lambda: build_simple_parser("init", "Configure the bac.page repo path."),
    }[command]()
    sub_args = sub.parse_args(rest)
    return command, argparse.Namespace(**vars(args), **vars(sub_args))


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    debug = "--debug" in argv
    try:
        command, args = parse(argv)
        load_env(args.env_file)
        {"add": cmd_add, "list": cmd_list, "edit": cmd_edit, "init": cmd_init}[command](args)
    except KeyboardInterrupt:
        err_console.print("\nAborted.")
        sys.exit(1)
    except SystemExit as e:
        if isinstance(e.code, str):
            err_console.print(f"{ERR} {e.code}")
            sys.exit(1)
        raise
    except Exception as e:
        if debug:
            traceback.print_exc()
        err_console.print(f"{ERR} {type(e).__name__}: {e}\n       Re-run with --debug for the traceback.")
        sys.exit(1)


if __name__ == "__main__":
    main()
