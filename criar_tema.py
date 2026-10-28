"""Create a Roku theme package with wallpaper, colors, preview and a portable addon."""
import argparse
import re
import shutil
import uuid
import zipfile
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from tema_common import client_ip, read_json, write_json, safe_relative, slug


def hex_color(value):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise argparse.ArgumentTypeError("Use a color such as #3291FF")
    return value


def main(argv=None):
    interactive = not (sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, help="Dump directory containing theme.json")
    p.add_argument("--name", "--nome", dest="name", help="Theme name")
    p.add_argument("--wallpaper", "--fundo", dest="wallpaper", type=Path, help="PNG/JPEG/WebP wallpaper")
    p.add_argument("--accent", type=hex_color, default="#3291FF")
    p.add_argument("--background", type=hex_color, default="#000000")
    p.add_argument("--text", "--texto", dest="text", type=hex_color, default="#FFFFFF")
    def address(value):
        try: return client_ip(value)
        except ValueError as exc: raise argparse.ArgumentTypeError(str(exc)) from exc
    p.add_argument("--client", type=address, help="Required TV IPv4/IPv6 address")
    p.add_argument("--hide-ad", "--ocultar-anuncio", dest="hide_ad", action="store_true", help="Transparent Google/simgad sidebar image")
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    if interactive and not sys.stdin.isatty():
        p.error("Provide --base and --client; the wizard requires a terminal")
    if not a.client:
        if not interactive:
            p.error("--client is required; enter your TV's IP address")
        try: a.client = address(input("TV IP address: ").strip())
        except argparse.ArgumentTypeError as exc: p.error(str(exc))
    if not a.base and not interactive:
        p.error("--base is required; provide a complete theme dump directory")
    if not a.base:
        value = input("Base theme folder containing theme.json: ").strip().strip('"')
        if not value: p.error("Download a base theme first, then enter its folder")
        a.base = Path(value)
    if not a.name: a.name = (input("Theme name: ").strip() if interactive else "") or "My Theme"
    if interactive and not a.wallpaper:
        value = input("Wallpaper path (drag a file; Enter to generate a background): ").strip().strip('"')
        if value: a.wallpaper = Path(value)
        try: a.accent = hex_color(input("Accent color [#3291FF]: ").strip() or "#3291FF")
        except argparse.ArgumentTypeError as exc: p.error(str(exc))
    try:
        from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageColor
    except ImportError:
        p.error("Install Pillow: python -m pip install -r requirements.txt")
    base = a.base.resolve()
    if base.is_file(): base = base.parent
    info = read_json(base / "theme.json")
    if info.get("missing"):
        p.error("Base theme is incomplete. Complete the dump with --download first.")
    for resource, rel in info["files"].items():
        if not safe_relative(resource) or not safe_relative(rel):
            p.error("Unsafe path in base manifest")
        source = (base / rel).resolve()
        if base not in source.parents or not source.is_file(): p.error("Missing or invalid base asset: " + rel)
    if info.get("xml") not in info["files"].values():
        p.error("The theme XML must be listed in the base manifest's files")
    root = ET.parse(base / info["xml"]).getroot()
    backdrops = set()
    for bitmap in root.iter("bitmap"):
        if bitmap.get("name") == "BackgroundBitmap":
            for node in bitmap:
                value = (node.text or "").strip()
                if value.startswith("pkg:/theme/"):
                    backdrops.add(value[len("pkg:/theme/"):])
    if not backdrops or not backdrops.issubset(info["files"]):
        p.error("Base theme needs a BackgroundBitmap and all its referenced assets")
    if any(rel not in info["files"].values() for rel in info["routes"].values()):
        p.error("Base routes must point to files listed in the manifest")
    out = (a.out or Path("created-themes") / slug(a.name)).resolve()
    archive = Path(str(out) + ".zip")
    if archive.exists(): p.error("ZIP already exists; choose another --out")
    if out == base or base in out.parents or out in base.parents:
        p.error("Output must be separate from the base theme directory")
    if out.exists() and not out.is_dir(): p.error("Output path must be a directory")
    if out.exists() and any(out.iterdir()): p.error("Output directory is not empty; choose another --out")
    size = (1280, 720)
    if a.wallpaper:
        with Image.open(a.wallpaper) as source:
            background = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), size, Image.Resampling.LANCZOS)
    else:
        background = Image.new("RGB", size, a.background)
        draw = ImageDraw.Draw(background)
        font = None
        for candidate in ["C:/Windows/Fonts/segoeuib.ttf", "DejaVuSans.ttf"]:
            try: font = ImageFont.truetype(candidate, 52); break
            except OSError: pass
        if font is None: font = ImageFont.load_default(size=52)
        draw.text((1190, 590), a.name, fill=a.text, font=font, anchor="ra")
        draw.rectangle((1050, 200, 1052, 450), fill=a.accent)
    out.mkdir(parents=True, exist_ok=True)
    for rel in set(info["files"].values()):
        destination = out / rel; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base / rel, destination)
    if root.find("name") is not None: root.find("name").text = a.name
    if root.find("version") is not None:
        try: root.find("version").text = str(int(root.find("version").text) + 1)
        except (ValueError, TypeError): root.find("version").text = "1"
    rgba = lambda c: "0x" + c[1:].upper() + "FF"
    fonts = root.find("FONTS")
    if fonts is not None:
        for c in fonts.iter("rgba"): c.text = rgba(a.text)
    for color in root.iter("color"):
        name = color.get("name", ""); value = color.find("rgba")
        if value is not None and any(x in name for x in ("Focus", "Divider")): value.text = rgba(a.accent)
    for rel, stored in info["files"].items():
        file = out / stored
        if rel in backdrops:
            background.save(file)
        elif file.name.lower() in ("thumb.jpg", "thumb.png"):
            with Image.open(file) as src: sz = src.size
            background.resize(sz, Image.Resampling.LANCZOS).save(file)
        elif file.name.lower() == "overhang_background.png":
            with Image.open(file) as src: sz = src.size
            Image.new("RGBA", sz, ImageColor.getrgb(a.background) + (255,)).save(file)
        elif file.name.lower().startswith("focus_") and file.suffix.lower() == ".png":
            with Image.open(file) as src: old = src.convert("RGBA")
            focus = ImageOps.colorize(ImageOps.grayscale(old), a.background, a.accent).convert("RGBA")
            focus.putalpha(old.getchannel("A"))
            if ".9.png" in file.name:
                w, h = old.size
                for box in ((0,0,w,1),(0,h-1,w,h),(0,0,1,h),(w-1,0,w,h)):
                    focus.paste(old.crop(box), box[:2])
            focus.save(file)
    ET.ElementTree(root).write(out / info["xml"], encoding="utf-8", xml_declaration=True)
    background.save(out / "wallpaper.png")
    background.resize((480, 270), Image.Resampling.LANCZOS).save(out / "preview.png")
    Image.new("RGBA", (289, 405), (0,0,0,0)).save(out / "transparent.webp", "WEBP", lossless=True)
    xml_key = next(k for k, v in info["files"].items() if v == info["xml"])
    revision = "custom-" + slug(a.name).lower() + "-" + uuid.uuid4().hex[:8]
    config = {"name": a.name, "base_name": info["name"], "client": a.client,
              "revision": revision, "xml_key": xml_key, "files": info["files"],
              "routes": info["routes"], "aliases": info["aliases"], "hide_google_ad": a.hide_ad}
    write_json(out / "config.json", config)
    shutil.copy2(Path(__file__).with_name("aplicar_template.py"), out / "apply_theme.py")
    instructions = (f"THEME: {a.name}\nBASE: {info['name']}\nTV: {a.client}\n\n"
        "Extract the entire ZIP. In your working mitmweb command, replace earlier\n"
        "theme/routing addons with: -s ./apply_theme.py\n"
        "Run from this directory, or use the addon's absolute path. Keep your\n"
        "working connection options. This package does not install TV certificates.\n"
        "Configure DNS for this TV only so cloudservices.roku.com and\n"
        "themes-service.sr.roku.com resolve to your proxy PC. If hiding the sidebar\n"
        "image, also include images.sr.roku.com. HTTPS still requires TV trust.\n"
        f"Select the default theme, then {info['name']} (or {a.name}).\n"
        "Cached catalogs may retain the old name. Look for LOCAL THEME in the log.\n"
        "For a different TV, set --set custom_client=YOUR_TV_IP in mitmweb.\n"
        "To restore: select the default theme, stop the addon, and remove the\n"
        "DNS overrides you added for this TV. Re-download the base theme if needed.\n")
    (out / "HOW-TO-APPLY.txt").write_text(instructions, encoding="utf-8")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(out.rglob("*")):
            if file.is_file(): z.write(file, Path(out.name) / file.relative_to(out))
    print("Theme created:", out)
    print("ZIP:", archive)
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (OSError, ValueError) as exc: raise SystemExit("Error: " + str(exc))
