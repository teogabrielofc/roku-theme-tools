# Step-by-step guide

## 1. Choose a workflow

- **Have a theme XML URL?** Download it on the PC, then create a theme. No TV,
  proxy or firmware change is needed for these two steps.
- **Have mitmproxy captures?** Extract them offline. Add `--download` only if you
  want the PC to fetch missing resources.
- **Want to collect or apply themes on the TV?** You need a working network
  interception setup. The tools do not set up routing, change firmware, install
  certificates, unlock a TV or enable developer mode.

The tools have a command-line interface and interactive terminal prompts, not a
graphical UI. Existing `.py` filenames are retained for compatibility.

## 2. Install on your PC

Use Python 3.10 or newer. Download and extract this repository or clone it:

```console
git clone https://github.com/teogabrielofc/roku-theme-tools.git
cd roku-theme-tools
python -m venv .venv
```

Activate the environment in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If activation is restricted, use `.\.venv\Scripts\python.exe` in place of
`python`; activation is optional. On Linux/macOS use `source .venv/bin/activate`.
Then install and check both tools:

```console
python -m pip install .
roku-theme-dump --help
roku-theme-create --help
```

You can also run `python dump_temas.py` and `python criar_tema.py` from the
repository. `dump.cmd`, `create.cmd` and the legacy `criar.cmd` are Windows
shortcuts; these use the Python launcher (`py`).

For live collection/application, install mitmproxy in the same environment:

```console
python -m pip install ".[proxy]"
mitmweb --version
```

The generated theme addon is standalone; live collection also needs
`tema_common.py` beside the source addons. If using another mitmproxy installation,
check which executable is being launched (`Get-Command mitmweb -All` on Windows).
That installation must support the addons and Python version you are using.

## 3. Download a base theme

Example URLs may change or be removed by the server:

```console
roku-theme-dump "http://cloudservices.roku.com/proxy/assets/r14.6.0/Daydream_pkg/DaydreamTheme_pkg.xml" --out my-dump
```

XML URLs automatically download referenced assets. You can supply several URLs.
For offline extraction:

```console
roku-theme-dump --flows captures.mitm --out my-dump
```

To fetch missing assets using the PC's connection:

```console
roku-theme-dump --flows captures.mitm --download --out my-dump
```

Look in `my-dump/report.json` and `my-dump/themes/`. Each theme directory contains
`theme.json` and `assets/`. Exit code **0** means recovered themes are complete;
**2** means failure, missing resources or no recovered themes. An inaccessible
URL does not prove that a theme never existed. Resources requiring an
authenticated TV session may need live capture instead.

Only use a complete base: `theme.json` should have `complete: true` and an empty
`missing` list. Do not manually change these fields to bypass missing assets.

## 4. Create your custom theme

Find the actual generated base directory under `my-dump/themes/`. Find your TV's
IP under its network settings, or in the router's device list. The IP belongs
to the TV, not the PC running the proxy. Replace `YOUR_TV_IP` and the base path:

```console
roku-theme-create --base "my-dump/themes/Daydream-REPLACE_WITH_ACTUAL_ID" --client YOUR_TV_IP --name "My Theme" --wallpaper "wallpaper.png" --accent "#3291FF" --background "#000000" --text "#FFFFFF" --out my-theme
```

For a wizard, run `roku-theme-create` without arguments. The creator asks for
an IP, base directory, name, wallpaper and accent color. Without a wallpaper it
creates a simple background. Wallpaper is cropped to 1280×720; this is the
creator's supported output size, not automatic model-specific resolution detection.
The base must have a supported `BackgroundBitmap` XML definition.

The output is `my-theme/` plus `my-theme.zip`, containing:

- `assets/`: modified base assets and XML.
- `config.json`: TV address, asset mapping and custom theme settings.
- `apply_theme.py`: portable mitmproxy addon.
- `HOW-TO-APPLY.txt`: instructions for that package.
- `wallpaper.png`, `preview.png` and `transparent.webp`.

Existing output directories containing files and existing ZIPs are refused.
Use a new output path for each revision. A package includes the chosen TV IP
in `config.json` and instructions; review it before sharing. Theme assets keep
their original ownership even when distributed with a custom package.

`--hide-ad` optionally replaces images whose encoded origin is
`tpc.googlesyndication.com/simgad/` on `images.sr.roku.com` with a transparent WebP.
It does not remove layout space or block every Roku advertisement.

## 5. Prepare live interception

Skip this section when only preserving or creating themes offline.

Use a stable LAN IP for both TV and proxy PC, preferably DHCP reservations.
Configure DNS overrides **for this TV only**, pointing relevant hostnames to the
proxy PC: `cloudservices.roku.com` and `themes-service.sr.roku.com`; add
`images.sr.roku.com` only for the optional sidebar image replacement. Configure
your DNS software's client rules according to its documentation. Do not point
all Roku domains at the proxy or change DNS for every LAN device.

DNS redirection preserves port numbers: HTTP arrives on port 80 and HTTPS on
443. The PC firewall must allow the TV to reach those listener ports. Another
web server may already be using them. On some systems binding these ports
requires additional OS permissions.

**HTTPS requires the TV/app to trust the certificate presented by the proxy.**
DNS changes alone do not establish trust. `unknown ca`, TLS disconnects or no
HTTP flows are not fixed by changing theme files. `--ssl-insecure` only affects
mitmproxy's verification of upstream servers; it does not make the TV trust it.
A successful `curl -k` test on the PC does not establish TV compatibility.
No custom CA impersonation flags or certificate workarounds are supplied here.

If you already have a working mitmweb command, keep its listener/connection
options and replace only the addon and client settings below. Do not stack
multiple routing or theme substitution addons: they may override each other.

For stock mitmproxy, this PowerShell example sets up reverse listeners and
explicitly asks for your own addresses. It still requires the DNS and trust
conditions above:

```powershell
$proxyIp = Read-Host 'Proxy PC LAN IP'
$tvIp = Read-Host 'TV LAN IP'
mitmweb --mode reverse:http://example.invalid@80 --mode reverse:https://example.invalid@443 --listen-host $proxyIp --set keep_host_header=true --set connection_strategy=lazy --set upstream_cert=false -s ./rotear_roku.py -s ./dump_ao_vivo.py --set "route_client=$tvIp" --set "theme_client=$tvIp"
```

`example.invalid` is a placeholder upstream: the routing addon replaces it with
the permitted Roku hostname from the request. `keep_host_header` preserves that
hostname. `upstream_cert=false` avoids attempting certificate lookup against the
placeholder; it does not disable the TV's verification. Keep the mitmweb UI bound
to its default localhost address. These addons serve one explicitly selected
client and allow only `roku.com`/`rokuapi.net` hostnames.

## 6. Collect normal and available seasonal themes

Run the collector pair from the repository directory. The full command above
collects themes as requested normally. To also request available seasonal
entries, append `--set include_seasonal=true`. This removes `seasonal` from the
catalog query's `exclude` field, preserving other query parameters.

Open the TV's theme selection screen and select themes to load their resources.
The live collector defaults to `live-themes/`; set `--set theme_dir=PATH` to
change it. Both `route_client` and `theme_client` are required: empty values
block routing and capture nothing. No personal IP is built into the tools.

Stop the proxy, then extract the capture:

```console
roku-theme-dump --live live-themes --download --out my-dump
```

The live collector saves response bodies, resource URLs and MIME types, not
request headers. Catalog bodies and URLs can still contain identifiers or
session data. Raw mitmproxy flow files can contain authentication data. Review
and sanitize captures before sharing or publishing them.

Seasonal availability depends on server, region, account, model and date; this
is not a historical archive of every seasonal theme.

## 7. Apply, verify and restore

Extract the entire ZIP and open a terminal in the generated theme directory.
Replace the collector/routing addons in your working command with:

```console
-s ./apply_theme.py
```

Keep the same listener options. The generated addon includes its own hostname
routing and uses the TV address in `config.json`. To use a different TV, add
`--set custom_client=YOUR_TV_IP`. Do not combine it with `rotear_roku.py` or other
substitution addons. Select the default theme on the TV, then select the
original base theme again. Look for `LOCAL THEME` in the terminal and successful
XML/image responses in mitmweb. Cached catalogs may still show the base name.

To restore: choose the default theme, stop the addon, remove the per-TV DNS
overrides and reload the original base theme if needed. The tool does not
write firmware or change system partitions. A downloaded theme may remain in
the TV's cache until it is reloaded.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `Client not allowed` / HTTP 403 | TV address versus PC address; `route_client` or `custom_client`; DHCP changes |
| Live directory is empty | `theme_client`, hostnames, TV actually loading a theme, matching request IP |
| Only connect/disconnect events | TLS trust and correct listener/port; no HTTP request has been decoded yet |
| Dump exits with code 2 | `report.json`, each manifest's `missing` and `errors` lists |
| Theme name or wallpaper stays unchanged | DNS overrides, base selection, cache, `LOCAL THEME` logs |
| Import error for mitmproxy | Run addons with mitmweb, not with `python addon.py` |
| Import error for tema_common | Keep source collector/router files together or install the project in mitmproxy's environment |
| `ZIP already exists` | Pick another `--out`; existing packages are preserved |
| Missing `BackgroundBitmap` | The base format is unsupported; use another complete theme |

Report your OS, Python/mitmproxy versions, command with private values removed,
error message and a synthetic XML if possible. Do not post account tokens or
raw authenticated captures.
