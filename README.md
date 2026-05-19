# bac.page

Short URL forwarding service for [Build a CubeSat](https://buildacubesat.space) – an open-source electronics project for accessible space hardware.

Slugs resolve via static HTML redirects hosted on GitHub Pages. Like everything in the BAC project, this tool is fully open source.

## Usage

Install the CLI from the `cli/` directory:

    uv tool install --editable ./cli

Create a short URL with an auto-generated slug:

    bac https://docs.buildacubesat.space/some/long/path
    # → https://bac.page/aB3x9kLm

Or specify your own (1–12 alphanumeric characters, hyphens allowed):

    bac https://docs.buildacubesat.space/some/long/path eps-v2r1
    # → https://bac.page/eps-v2r1

The CLI creates the redirect file, commits, and pushes in one step. The short URL is live within ~30 seconds once GitHub Pages deploys.

## Repo structure

    cli/               Python CLI source
    <slug>/            One folder per short URL, each containing an index.html redirect
    index.html         Landing page served at bac.page/
    CNAME              GitHub Pages custom domain config

## License

[MIT](LICENSE)