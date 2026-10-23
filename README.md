# Roku Theme Tools

Download and preserve Roku TV themes, then build custom themes with your own
wallpaper and colors. Command-line tools with an interactive terminal wizard.

Created by **Teo Gabriel.

## Features

- Download a theme directly from its XML URL, including `pkg:/theme/` assets.
- Extract themes from one or more mitmproxy flow files.
- Collect live theme catalogs and request available seasonal entries.
- Report missing resources instead of labeling partial dumps as complete.
- Create a custom theme with wallpaper, name, text and accent colors.
- Generate a portable ZIP with an application addon and instructions.
- Optionally replace Google `/simgad/` sidebar images with a transparent image.

No Roku theme assets, firmware, network captures or account credentials are
bundled with this repository. The MIT license covers the tool code; downloaded
theme resources retain their respective ownership.

## Requirements

- Python 3.10 or newer.
- Pillow for theme creation.
- mitmproxy separately installed for live collection or theme application.

The dumper itself uses only Python's standard library. CLI help and some
terminal messages are currently in Portuguese; English option aliases are
available for theme creation.

## Install

From the extracted repository:

```console
python -m pip install .
```

Or run the scripts directly:

```console
python -m pip install -r requirements.txt
python dump_temas.py --help
python criar_tema.py --help
```

On Windows, `py` can be used instead of `python`. `dump.cmd` and `criar.cmd`
open the terminal workflows from the repository directory.

## Download directly from XML

```console
roku-theme-dump "http://cloudservices.roku.com/proxy/assets/r14.6.0/Daydream_pkg/DaydreamTheme_pkg.xml"
```

Multiple URLs are supported:

```console
python dump_temas.py "http://cloudservices.roku.com/proxy/assets/r14.6.0/Space_FHD_pkg/newNebula_FHD_pkg.xml" "http://cloudservices.roku.com/proxy/assets/r14.6.0/Daydream_pkg/DaydreamTheme_pkg.xml"
```

Direct URL inputs automatically download referenced assets; `--download` is not
required. Run `dump.cmd` or `roku-theme-dump` without arguments to paste a URL
interactively. Example server URLs may change or stop working over time.

Output is written to `dump-temas/themes/<name>-<id>/`:

| File | Purpose |
| --- | --- |
| `theme.json` | Theme metadata, URL aliases, local routes and missing resources |
| `assets/` | XML and downloaded resources |
| `dump-temas/catalog-index.json` | Discovered catalog entries |
| `dump-temas/report.json` | Completeness and download errors |

The command exits with status `2` when there are incomplete results or download
failures. Files already recovered are kept.

## Extract captures and catalogs

```console
roku-theme-dump --flows flows flows2 --out my-dump
roku-theme-dump --flows flows --download --out my-dump
roku-theme-dump --catalog catalog.json --download --out my-dump
```

Without `--download`, flow extraction stays offline. With `--download`, it also
tries catalog URLs and missing assets. Downloads use the PC's normal connection
and do not reuse captured authentication headers. Resources requiring the TV's
session can instead be collected live while the TV loads the theme.

## Collect normal and seasonal themes

Use these addons with an existing working reverse-proxy setup:

```console
-s ./rotear_roku.py -s ./dump_ao_vivo.py --set temas_sazonais=true
```

Run from the repository directory, or use absolute addon paths. Replace earlier
theme/route addons with this pair to capture original resources. The routing
addon allows the configured TV and Roku domains; the collector saves only theme
catalogs and resources, not request authentication headers.

Open the theme selection screen on the TV. The collector removes `seasonal`
from the catalog query's `exclude` parameter, preserving other query fields.
Then stop the proxy and run:

```console
roku-theme-dump --live dump-ao-vivo --download --out my-dump
```

Seasonal availability depends on the server, TV model, region, account and date.
This does not retrieve every seasonal theme ever released. Catalog groups
identify seasonal/sponsored entries when that information is available;
`catalog` or `captured` means the classification is not established.

The default TV IP is `192.168.18.76`. For another device, set both:

```console
--set route_client=192.168.1.50 --set temas_client=192.168.1.50
```

Keep the DNS/routing and certificate setup that works for your TV. This project
does not configure the router, install TV certificates or alter firmware.

## Create a theme

First download or dump a complete base theme. Use its folder containing
`theme.json`:

```console
roku-theme-create --base "my-dump/themes/Daydream-<id>" --name "My Theme" --wallpaper "wallpaper.png" --accent "#3291FF" --background "#000000" --text "#FFFFFF" --out "my-theme"
```

Or run `criar.cmd` and follow the prompts. This repository does not include a
pre-dumped base theme, so enter the path to your own complete dump.

| Option | Effect |
| --- | --- |
| `--name` / `--nome` | Theme name |
| `--wallpaper` / `--fundo` | PNG, JPEG or WebP; center-cropped to 1280×720 |
| `--accent` | Focus and divider color |
| `--background` | Generated background and header color |
| `--text` / `--texto` | Text colors exposed by the XML `FONTS` block |
| `--client` | TV IP address |
| `--hide-ad` / `--ocultar-anuncio` | Transparent Google `/simgad/` sidebar image |
| `--out` | New output directory; a ZIP is created next to it |

Without a wallpaper, the creator draws a simple background with the theme name.
Nine-patch metadata borders are preserved. Other icons and resources are reused
from the base. The creator supports the `<theme>` XML and `pkg:/theme/`
references seen in the tested captures; other formats may need additional work.

## Apply a generated theme

Extract the generated ZIP. Replace previous theme/routing addons in your working
mitmweb command with:

```console
-s ./aplicar_tema.py
```

Run from the generated theme directory. Its addon includes hostname routing and
reads local assets from `config.json`. Preserve the connection options from your
working setup. Route the relevant Roku services through the proxy for that TV.

Switch to the default theme, then select the original base theme again. If the
catalog is intercepted, it may appear under the new custom name. Cached catalogs
may retain the old name. Look for `TEMA LOCAL` messages in the terminal.

To restore normal behavior, select the default theme and stop the addon. Re-fetch
the original theme without the customization addon if needed.

## Tests

```console
python -m unittest discover -s tests -v
```

Tests use synthetic themes and a local HTTP server. They cover direct URL
downloads, redirects, seasonal catalog parsing, missing assets, custom package
generation and the generated addon. No live Roku account or TV is needed.

The earlier theme substitution workflow was tested on a user's TV; that does
not establish compatibility with every model or firmware. CI defines Windows
and Linux checks; local validation was performed on Linux.

## Contributing

Include the command, Python version and a minimal synthetic XML or sanitized
example when reporting a problem. Avoid attaching raw authenticated captures.

Unofficial project. Not affiliated with Roku.
