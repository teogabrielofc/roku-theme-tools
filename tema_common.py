"""Leitura de dumps mitmproxy e extracao de temas. Apenas biblioteca padrao."""
import gzip
import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit


def key(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def slug(name):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")[:70] or "tema"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def flows(path):
    b = Path(path).read_bytes()
    def parse(p):
        c = b.index(b":", p)
        length = int(b[p:c]); start = c + 1; end = start + length
        if end >= len(b):
            raise ValueError("Registro truncado no dump")
        raw = b[start:end]; tag = chr(b[end])
        if tag in ("}", "]"):
            items = []; q = start
            while q < end:
                item, q = parse(q); items.append(item)
            if q != end:
                raise ValueError("Comprimento invalido")
            value = dict(zip(items[::2], items[1::2])) if tag == "}" else items
        elif tag == ";": value = raw.decode("utf-8")
        elif tag == ",": value = raw
        elif tag == "#": value = int(raw)
        elif tag == "^": value = float(raw)
        elif tag == "!": value = raw == b"true"
        elif tag == "~": value = None
        else: raise ValueError("Formato de registro desconhecido")
        return value, end + 1
    pos = 0
    while pos < len(b):
        record, pos = parse(pos)
        if isinstance(record, dict):
            yield record


def text(value):
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)


def records(path):
    for flow in flows(path):
        req = flow.get("request") or {}; resp = flow.get("response") or {}
        if resp.get("status_code") != 200 or not resp.get("content"):
            continue
        host = req.get("host", "")
        if host not in ("cloudservices.roku.com", "themes-service.sr.roku.com"):
            continue
        scheme = text(req.get("scheme", b"https"))
        port = req.get("port", 443 if scheme == "https" else 80)
        authority = host if port in (80, 443) else f"{host}:{port}"
        url = f"{scheme}://{authority}{text(req.get('path', b'/'))}"
        headers = {text(k).lower(): text(v) for k, v in resp.get("headers", [])}
        body = resp["content"]
        encoding = headers.get("content-encoding", "").lower()
        if encoding == "gzip": body = gzip.decompress(body)
        elif encoding == "deflate":
            try: body = zlib.decompress(body)
            except zlib.error: body = zlib.decompress(body, -15)
        elif encoding and encoding != "identity":
            raise ValueError(f"Compressao {encoding} nao suportada neste flow; use o coletor ao vivo")
        yield url, body, headers.get("content-type", "application/octet-stream")


def catalog_entries(data):
    found = {}
    def walk(obj, trail=()):
        if isinstance(obj, dict):
            url = obj.get("url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                path = urlsplit(url).path.lower()
                if path.endswith(".xml") or "/wallpapers/" in path:
                    context = ".".join(trail).lower()
                    category = "seasonal" if "season" in context else "sponsored" if "sponsor" in context else "catalog"
                    found[url] = {"name": str(obj.get("name") or Path(path).stem),
                                  "url": url, "category": category, "catalog_path": ".".join(trail)}
            for k, value in obj.items(): walk(value, trail + (str(k),))
        elif isinstance(obj, list):
            for value in obj: walk(value, trail)
    walk(data)
    return list(found.values())


def theme_xml(body):
    try:
        root = ET.fromstring(body)
        return root if root.tag.lower() == "theme" else None
    except (ET.ParseError, ValueError):
        return None


def pkg_refs(root):
    result = set()
    for element in root.iter():
        value = (element.text or "").strip()
        if value.startswith("pkg:/theme/"):
            relative = value[len("pkg:/theme/"):]
            if (relative and ".." not in relative.split("/")
                    and not relative.startswith("/") and "\\" not in relative and ":" not in relative):
                result.add(relative)
    return sorted(result)


def fetch(url, timeout=20):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Somente URLs HTTP/HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "RokuThemeTools/1.0", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            body = gzip.decompress(body)
        return response.geturl(), body, response.headers.get_content_type()


def save_theme(out, url, body, cache, entries, download=False):
    root = theme_xml(body)
    if root is None:
        raise ValueError("Resposta nao e um XML de tema Roku")
    name = root.findtext("name") or "Tema"
    matches = [e for e in entries if e["name"].casefold() == name.casefold() or key(e["url"]) == key(url)]
    identity = hashlib.sha256(key(url).encode()).hexdigest()[:8]
    folder = Path(out) / "themes" / (slug(name) + "-" + identity)
    assets = folder / "assets"; assets.mkdir(parents=True, exist_ok=True)
    xml_name = Path(urlsplit(url).path).name or "Theme.xml"
    (assets / xml_name).write_bytes(body)
    files = {xml_name: "assets/" + xml_name}
    missing = []; errors = []
    routes = {key(url): "assets/" + xml_name}
    for e in matches: routes[key(e["url"])] = "assets/" + xml_name
    refs = pkg_refs(root)
    for rel in refs:
        asset_url = urljoin(url, rel)
        resource = cache.get(key(asset_url))
        if resource is None and download:
            try:
                _, content, mime = fetch(asset_url)
                resource = (content, mime); cache[key(asset_url)] = resource
            except Exception as exc:
                errors.append({"path": rel, "error": str(exc)})
        if resource is None:
            missing.append(rel); continue
        destination = assets / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(resource[0])
        files[rel] = "assets/" + rel
        routes[key(asset_url)] = "assets/" + rel
    info = {"format": 1, "name": name, "category": matches[0]["category"] if matches else "captured",
            "source_url": key(url), "xml": "assets/" + xml_name,
            "aliases": sorted({key(url)} | {key(e["url"]) for e in matches}),
            "package_root": key(url).rsplit("/", 1)[0] + "/", "files": files,
            "routes": routes, "missing": missing, "errors": errors,
            "complete": not missing}
    write_json(folder / "theme.json", info)
    return folder, info
