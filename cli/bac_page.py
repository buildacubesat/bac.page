import argparse
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


def parse_target(index_html: Path) -> str | None:
    content = index_html.read_text()
    m = re.search(r'content="0; url=([^"]+)"', content)
    return m.group(1) if m else None


def list_redirects() -> list[tuple[str, str]]:
    entries = []
    for d in sorted(REPO_PATH.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name in ("cli",):
            continue
        index = d / "index.html"
        if index.exists():
            target = parse_target(index)
            if target:
                entries.append((d.name, target))
    return entries


def git_commit_push(slug: str, target: str) -> None:
    subprocess.run(["git", "add", str(REPO_PATH / slug)], cwd=REPO_PATH, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"add redirect: /{slug} → {target}"],
        cwd=REPO_PATH,
        check=True,
    )
    subprocess.run(["git", "push"], cwd=REPO_PATH, check=True)


def git_commit_push_edit(message: str, *paths: Path) -> None:
    for p in paths:
        subprocess.run(["git", "add", str(p)], cwd=REPO_PATH, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=REPO_PATH, check=True)
    subprocess.run(["git", "push"], cwd=REPO_PATH, check=True)


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

    filename = f"bac-page-{slug}.{fmt}"
    dest = (output or Path.home()) / filename

    qr = qrcode.QRCode(error_correction=ec_map[ec], box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)

    if fmt == "svg":
        import qrcode.image.svg
        factory = qrcode.image.svg.SvgPathImage
        img = qr.make_image(image_factory=factory)
        svg_data = img.to_string().decode()
        # Set explicit size
        svg_data = re.sub(
            r'(<svg[^>]*)(width="[^"]*")', f'\\1width="{size}"', svg_data
        )
        svg_data = re.sub(
            r'(<svg[^>]*)(height="[^"]*")', f'\\1height="{size}"', svg_data
        )
        if invert:
            svg_data = svg_data.replace('fill="#000000"', 'fill="TEMP"')
            svg_data = svg_data.replace('fill="#ffffff"', 'fill="#000000"')
            svg_data = svg_data.replace('fill="TEMP"', 'fill="#ffffff"')
        if alpha:
            svg_data = re.sub(r'<rect[^/]*/>', '', svg_data, count=1)
        dest.write_text(svg_data)

    else:
        from PIL import Image
        import numpy as np

        fg = (255, 255, 255) if invert else (0, 0, 0)
        bg = (0, 0, 0) if invert else (255, 255, 255)

        if alpha:
            img = qr.make_image(fill_color=fg, back_color=(0, 0, 0, 0)).convert("RGBA")
            arr = np.array(img)
            bg_mask = (arr[:, :, 0] == bg[0]) & (arr[:, :, 1] == bg[1]) & (arr[:, :, 2] == bg[2])
            arr[bg_mask] = [0, 0, 0, 0]
            img = Image.fromarray(arr)
        else:
            img = qr.make_image(fill_color=fg, back_color=bg).convert("RGB")

        img = img.resize((size, size), Image.NEAREST)

        save_kwargs = {"format": "WEBP"} if fmt == "webp" else {}
        img.save(dest, **save_kwargs)

    return dest


def prompt_qr_params() -> dict:
    fmt = input("Format [png/svg/webp] (default: svg): ").strip().lower() or "svg"
    if fmt not in ("png", "svg", "webp"):
        fmt = "svg"
    invert = input("Invert? [y/N]: ").strip().lower() == "y"
    alpha = input("Transparent background? [y/N]: ").strip().lower() == "y"
    ec = input("Error correction [L/M/Q/H] (default: M): ").strip().upper() or "M"
    if ec not in ("L", "M", "Q", "H"):
        ec = "M"
    size_str = input("Size in pixels (default: 1000): ").strip()
    size = int(size_str) if size_str.isdigit() else 1000
    output_str = input("Output directory (default: ~): ").strip()
    output = Path(output_str) if output_str else None
    return {"fmt": fmt, "invert": invert, "alpha": alpha, "ec": ec, "size": size, "output": output}


def edit_mode() -> None:
    redirects = list_redirects()
    if not redirects:
        print("No redirects found.")
        return

    print("\nCurrent redirects:\n")
    for i, (slug, target) in enumerate(redirects, 1):
        print(f"  {i:>3}.  /{slug}")
        print(f"        → {target}\n")

    choice = input("Select a redirect to edit (number): ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(redirects)):
        print("Invalid selection.", file=sys.stderr)
        sys.exit(1)

    slug, target = redirects[int(choice) - 1]
    short_url = f"https://{DOMAIN}/{slug}"

    print(f"\nEditing /{slug} → {target}\n")
    print("  1. Edit slug")
    print("  2. Edit destination URL")
    print("  3. Regenerate QR code")
    print("  4. Cancel\n")

    action = input("Action: ").strip()

    if action == "1":
        new_slug = input(f"New slug (current: {slug}): ").strip()
        if not SLUG_PATTERN.match(new_slug):
            print("Error: invalid slug.", file=sys.stderr)
            sys.exit(1)
        if slug_exists(new_slug):
            print(f"Error: /{new_slug} already exists.", file=sys.stderr)
            sys.exit(1)
        old_path = REPO_PATH / slug
        new_path = REPO_PATH / new_slug
        old_path.rename(new_path)
        subprocess.run(["git", "rm", "-r", str(old_path)], cwd=REPO_PATH, check=True)
        git_commit_push_edit(
            f"rename redirect: /{slug} → /{new_slug}",
            new_path,
        )
        print(f"https://{DOMAIN}/{new_slug}")

    elif action == "2":
        new_target = input(f"New destination URL (current: {target}): ").strip()
        create_redirect(slug, new_target)
        git_commit_push_edit(
            f"update redirect: /{slug} → {new_target}",
            REPO_PATH / slug,
        )
        print(f"https://{DOMAIN}/{slug} now points to {new_target}")

    elif action == "3":
        params = prompt_qr_params()
        qr_path = generate_qr(short_url, slug, **params)
        print(f"QR code saved to {qr_path}")

    elif action == "4":
        print("Cancelled.")

    else:
        print("Invalid action.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and manage bac.page short URLs.")
    parser.add_argument("url", nargs="?", help="Target URL to redirect to")
    parser.add_argument("slug", nargs="?", help="Custom slug (1–12 alphanumeric chars)")
    parser.add_argument("--edit", action="store_true", help="Edit existing redirects")
    parser.add_argument("--qr", action="store_true", help="Generate a QR code for the short URL")
    parser.add_argument("--format", choices=["png", "svg", "webp"], default="svg", dest="fmt", help="QR output format (default: svg)")
    parser.add_argument("--invert", action="store_true", help="White on black QR code")
    parser.add_argument("--alpha", action="store_true", help="Transparent background")
    parser.add_argument("--ec", choices=["L", "M", "Q", "H"], default="M", help="Error correction level (default: M)")
    parser.add_argument("--size", type=int, default=1000, help="QR code size in pixels (default: 1000)")
    parser.add_argument("--output", type=Path, default=None, help="Output directory for QR code (default: ~)")
    args = parser.parse_args()

    if args.edit:
        edit_mode()
        return

    if not args.url:
        parser.print_help()
        sys.exit(1)

    target = args.url

    if args.slug:
        slug = args.slug
        if not SLUG_PATTERN.match(slug):
            print("Error: slug must be 1–12 alphanumeric characters (hyphens allowed).", file=sys.stderr)
            sys.exit(1)
        if slug_exists(slug):
            print(f"Error: /{slug} already exists.", file=sys.stderr)
            sys.exit(1)
    else:
        slug = generate_uid()
        while slug_exists(slug):
            slug = generate_uid()

    create_redirect(slug, target)
    git_commit_push(slug, target)

    short_url = f"https://{DOMAIN}/{slug}"
    print(short_url)

    if args.qr:
        qr_path = generate_qr(short_url, slug, args.fmt, args.invert, args.alpha, args.ec, args.output, args.size)
        print(f"QR code saved to {qr_path}")


if __name__ == "__main__":
    main()