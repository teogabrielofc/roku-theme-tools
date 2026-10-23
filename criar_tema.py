"""Cria um pacote de tema Roku com fundo, cores, preview e addon portatil."""
import argparse
import re
import shutil
import uuid
import zipfile
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from tema_common import read_json, write_json, slug


def hex_color(value):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise argparse.ArgumentTypeError("Use uma cor como #3291FF")
    return value


def main(argv=None):
    interactive = not (sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, help="Pasta de um dump contendo theme.json")
    p.add_argument("--name", "--nome", dest="nome", help="Theme name")
    p.add_argument("--wallpaper", "--fundo", dest="fundo", type=Path, help="PNG/JPEG/WebP wallpaper")
    p.add_argument("--accent", type=hex_color, default="#3291FF")
    p.add_argument("--background", type=hex_color, default="#000000")
    p.add_argument("--text", "--texto", dest="texto", type=hex_color, default="#FFFFFF")
    p.add_argument("--client", default="192.168.18.76")
    p.add_argument("--hide-ad", "--ocultar-anuncio", dest="ocultar_anuncio", action="store_true", help="Transparent Google/simgad sidebar image")
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    if not a.base:
        value = input("Base theme folder containing theme.json: ").strip().strip('"')
        if not value: p.error("Download a base theme first, then enter its folder")
        a.base = Path(value)
    if not a.nome: a.nome = input("Nome do tema: ").strip() or "Meu tema"
    if interactive and not a.fundo:
        value = input("Imagem de fundo (arraste o arquivo; Enter para gerar uma simples): ").strip().strip('"')
        if value: a.fundo = Path(value)
        a.accent = hex_color(input("Cor de destaque [#3291FF]: ").strip() or "#3291FF")
    try:
        from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageColor
    except ImportError:
        p.error("Instale Pillow: py -m pip install -r requirements.txt")
    base = a.base.resolve()
    if base.is_file(): base = base.parent
    info = read_json(base / "theme.json")
    if info.get("missing"):
        p.error("Tema base incompleto. Complete o dump com --download antes de criar.")
    for rel in info["files"].values():
        source = (base / rel).resolve()
        if base not in source.parents or not source.is_file(): p.error("Asset base ausente ou invalido: " + rel)
    out = (a.out or Path("temas-criados") / slug(a.nome)).resolve()
    if out.exists() and any(out.iterdir()): p.error("Pasta de saida ja contem arquivos; escolha outra --out")
    out.mkdir(parents=True, exist_ok=True)
    for rel in set(info["files"].values()):
        destination = out / rel; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base / rel, destination)
    size = (1280, 720)
    if a.fundo:
        with Image.open(a.fundo) as source:
            background = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), size, Image.Resampling.LANCZOS)
    else:
        background = Image.new("RGB", size, a.background)
        draw = ImageDraw.Draw(background)
        font = None
        for candidate in ["C:/Windows/Fonts/segoeuib.ttf", "DejaVuSans.ttf"]:
            try: font = ImageFont.truetype(candidate, 52); break
            except OSError: pass
        if font is None: font = ImageFont.load_default(size=52)
        draw.text((1190, 590), a.nome, fill=a.texto, font=font, anchor="ra")
        draw.rectangle((1050, 200, 1052, 450), fill=a.accent)
    root = ET.parse(out / info["xml"]).getroot()
    if root.find("name") is not None: root.find("name").text = a.nome
    if root.find("version") is not None:
        try: root.find("version").text = str(int(root.find("version").text) + 1)
        except (ValueError, TypeError): root.find("version").text = "1"
    rgba = lambda c: "0x" + c[1:].upper() + "FF"
    fonts = root.find("FONTS")
    if fonts is not None:
        for c in fonts.iter("rgba"): c.text = rgba(a.texto)
    for color in root.iter("color"):
        name = color.get("name", ""); value = color.find("rgba")
        if value is not None and any(x in name for x in ("Focus", "Divider")): value.text = rgba(a.accent)
    backdrops = set()
    for bitmap in root.iter("bitmap"):
        if bitmap.get("name") == "BackgroundBitmap":
            for node in bitmap:
                if node.text and node.text.startswith("pkg:/theme/"):
                    backdrops.add(node.text[len("pkg:/theme/"):])
    if not backdrops: p.error("Nao achei BackgroundBitmap no XML; base nao suportada por este criador")
    for rel, stored in info["files"].items():
        file = out / stored
        if rel in backdrops:
            background.save(file, format="PNG")
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
    background.save(out / "fundo.png")
    background.resize((480, 270), Image.Resampling.LANCZOS).save(out / "preview.png")
    Image.new("RGBA", (289, 405), (0,0,0,0)).save(out / "transparente.webp", "WEBP", lossless=True)
    xml_key = next(k for k, v in info["files"].items() if v == info["xml"])
    revision = "custom-" + slug(a.nome).lower() + "-" + uuid.uuid4().hex[:8]
    config = {"name": a.nome, "base_name": info["name"], "client": a.client,
              "revision": revision, "xml_key": xml_key, "files": info["files"],
              "routes": info["routes"], "aliases": info["aliases"], "hide_google_ad": a.ocultar_anuncio}
    write_json(out / "config.json", config)
    shutil.copy2(Path(__file__).with_name("aplicar_template.py"), out / "aplicar_tema.py")
    instructions = (f"TEMA: {a.nome}\nBASE: {info['name']}\nTV: {a.client}\n\n"
        "Extraia o ZIP inteiro. No comando mitmweb que ja funcionou, substitua os\n"
        "addons de tema/roteamento antigos por apenas -s .\\aplicar_tema.py.\n"
        "Mantenha as outras opcoes do comando. A CA/conexao da TV precisa continuar\n"
        "funcionando. Este pacote nao instala certificados na TV.\n"
        "Aponte cloudservices.roku.com e themes-service.sr.roku.com para o PC via\n"
        "DNS somente para esta TV. Se ocultar anuncio, inclua images.sr.roku.com.\n"
        f"Selecione o tema padrao, depois {info['name']} (ou {a.nome}).\n"
        "O catalogo pode estar em cache. Veja TEMA LOCAL no terminal.\n"
        "Para desfazer, selecione o tema padrao e pare o addon.\n")
    (out / "COMO-APLICAR.txt").write_text(instructions, encoding="utf-8")
    archive = Path(str(out) + ".zip")
    if archive.exists(): p.error("ZIP ja existe; escolha outra pasta --out")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(out.rglob("*")):
            if file.is_file(): z.write(file, Path(out.name) / file.relative_to(out))
    print("Tema criado:", out)
    print("ZIP:", archive)
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (OSError, ValueError) as exc: raise SystemExit("Erro: " + str(exc))
