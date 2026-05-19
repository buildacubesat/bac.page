#!/usr/bin/env python3
"""bac.page URL shortener CLI.

Usage:
    bac <url>               # auto-generates 8-char UID
    bac <url> <slug>        # custom slug (1–12 alphanumeric chars)
"""

import argparse
import os
import random
import re
import string
import subprocess
import sys
from pathlib import Path

DOMAIN = "bac.page"
REPO_PATH = Path(__file__).parent.parent
UID_LENGTH = 8
SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9-]{1,12}$")


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


def slug_exists(slug: str) -> bool:
    return (REPO_PATH / slug / "index.html").exists()


def create_redirect(slug: str, target: str) -> None:
    slug_dir = REPO_PATH / slug
    slug_dir.mkdir(exist_ok=True)
    (slug_dir / "index.html").write_text(redirect_html(target))


def git_commit_push(slug: str, target: str) -> None:
    subprocess.run(["git", "add", str(REPO_PATH / slug)], cwd=REPO_PATH, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"add redirect: /{slug} → {target}"],
        cwd=REPO_PATH,
        check=True,
    )
    subprocess.run(["git", "push"], cwd=REPO_PATH, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a bac.page short URL.")
    parser.add_argument("url", help="Target URL to redirect to")
    parser.add_argument("slug", nargs="?", help="Custom slug (1–12 alphanumeric chars)")
    args = parser.parse_args()

    target = args.url

    if args.slug:
        slug = args.slug
        if not SLUG_PATTERN.match(slug):
            print(f"Error: slug must be 1–12 alphanumeric characters (hyphens allowed).", file=sys.stderr)
            sys.exit(1)
        if slug_exists(slug):
            print(f"Error: /{slug} already exists.", file=sys.stderr)
            sys.exit(1)
    else:
        slug = generate_uid()
        while slug_exists(slug):  # collision guard
            slug = generate_uid()

    create_redirect(slug, target)
    git_commit_push(slug, target)

    print(f"https://{DOMAIN}/{slug}")


if __name__ == "__main__":
    main()