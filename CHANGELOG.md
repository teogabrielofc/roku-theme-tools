# Changelog

## 0.3.0

- English help, prompts, logs, errors, catalog description and generated instructions.
- No built-in TV IP. Theme creation requires `--client` (or asks in the wizard).
  Collector/router defaults accept no client. Explicit addresses are validated.
- Seasonal query rewriting is opt-in instead of enabled by default.
- Base manifest paths, XML membership and required background assets are checked
  before copying files. Existing ZIPs and overlapping base/output directories
  are rejected before writing output. Unsafe XML asset references are errors
  instead of being silently omitted from a supposedly complete dump.
- Background assets retain the image format indicated by their extension.
- Added a full setup/troubleshooting guide, optional proxy dependencies, ignore
  rules and a Windows/Linux GitHub Actions test workflow.

### Migration from 0.2.x

| Old | New |
| --- | --- |
| Implicit TV IP | Supply `--client YOUR_TV_IP` when creating a theme |
| `temas_client` | `theme_client` |
| `temas_dir` | `theme_dir` |
| `temas_sazonais` | `include_seasonal` (default false) |
| `dump-temas/` default | `dump-themes/` |
| `dump-ao-vivo/` default | `live-themes/` |
| `temas-criados/` default | `created-themes/` |
| Generated `aplicar_tema.py` | Generated `apply_theme.py` |
| `COMO-APLICAR.txt` | `HOW-TO-APPLY.txt` |
| Generated `fundo.png` / `transparente.webp` | `wallpaper.png` / `transparent.webp` |

Source script filenames and Portuguese creator option aliases remain compatible.
Old generated packages are self-contained and are not rewritten; regenerate a
package to use the new addon and instructions. Existing dumps can be supplied
with explicit paths regardless of their directory names.
