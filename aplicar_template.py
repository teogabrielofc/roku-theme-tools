"""Addon gerado: serve um tema local e substitui sua entrada no catalogo da TV."""
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit, unquote
from mitmproxy import ctx, http

BASE = Path(__file__).resolve().parent


def load_config():
    config = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    def checked(relative):
        p = (BASE / relative).resolve()
        if BASE not in p.parents or not p.is_file():
            raise ValueError("Arquivo do pacote ausente ou fora da pasta: " + relative)
        return p
    files = {k: checked(v) for k, v in config["files"].items()}
    routes = {}
    for url, relative in config["routes"].items():
        p = urlsplit(url)
        routes[(p.hostname, p.path)] = checked(relative)
    return config, files, routes


class TemaLocal:
    def load(self, loader):
        self.config, self.files, self.routes = load_config()
        loader.add_option("custom_client", str, self.config["client"], "IP da TV")
        self.prefix = "/proxy/assets/" + self.config["revision"] + "/pkg/"
        self.preview = "/proxy/images/" + self.config["revision"] + ".png"
        ctx.log.info("TEMA LOCAL: " + self.config["name"])

    def reply(self, flow, path):
        try: body = path.read_bytes()
        except OSError as exc:
            ctx.log.error(str(exc)); flow.response = http.Response.make(503, b"Asset indisponivel"); return
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        flow.response = http.Response.make(200, body, {"Content-Type": mime, "Cache-Control": "no-store"})
        flow.metadata["theme_local"] = True
        ctx.log.info("TEMA LOCAL: " + path.relative_to(BASE).as_posix())

    def requestheaders(self, flow):
        peer = flow.client_conn.peername
        if not peer or peer[0] != ctx.options.custom_client:
            flow.response = http.Response.make(403, b"Cliente nao permitido"); return
        try: host = (urlsplit("//" + (flow.request.host_header or "")).hostname or "").lower().rstrip(".")
        except ValueError: host = ""
        if not any(host == suffix or host.endswith("." + suffix) for suffix in ("roku.com", "rokuapi.net")):
            flow.response = http.Response.make(403, b"Dominio nao permitido"); return
        flow.request.host = host
        flow.request.scheme = "https" if flow.client_conn.tls else "http"
        flow.request.port = 443 if flow.client_conn.tls else 80
        flow.server_conn.sni = host if flow.client_conn.tls else None
        path = flow.request.path.split("?", 1)[0]
        if self.config.get("hide_google_ad") and host == "images.sr.roku.com":
            decoded = flow.request.path
            for _ in range(3): decoded = unquote(decoded)
            original = urlsplit(decoded.lstrip("/"))
            if original.hostname == "tpc.googlesyndication.com" and original.path.startswith("/simgad/"):
                self.reply(flow, BASE / "transparente.webp"); return
        local = self.routes.get((host, path))
        if host == "cloudservices.roku.com":
            if path == self.preview: local = BASE / "preview.png"
            elif path.startswith(self.prefix): local = self.files.get(path[len(self.prefix):])
        if local:
            self.reply(flow, local); return
        if host == "themes-service.sr.roku.com" and path == "/themes-service/v1/dynamic":
            flow.metadata["theme_catalog"] = True
            for name in ("if-none-match", "if-modified-since"): flow.request.headers.pop(name, None)

    def response(self, flow):
        if not flow.metadata.get("theme_catalog") or not flow.response or flow.response.status_code != 200: return
        try: data = json.loads(flow.response.text)
        except (ValueError, TypeError): return
        count = 0
        def walk(item):
            nonlocal count
            if isinstance(item, dict):
                if (str(item.get("name", "")).casefold() == self.config["base_name"].casefold()
                        or item.get("url") in self.config["aliases"]):
                    item["name"] = self.config["name"]
                    item["description"] = "Tema pessoal criado com Roku Theme Tools"
                    item["url"] = "http://cloudservices.roku.com" + self.prefix + self.config["xml_key"]
                    item["thumbnail"] = {k: "http://cloudservices.roku.com" + self.preview for k in ("hd", "fhd")}
                    count += 1
                for value in item.values(): walk(value)
            elif isinstance(item, list):
                for value in item: walk(value)
        walk(data)
        if count:
            flow.response.text = json.dumps(data, ensure_ascii=False)
            flow.response.headers["Cache-Control"] = "no-store"
            for name in ("etag", "content-md5"): flow.response.headers.pop(name, None)
            ctx.log.info(f"TEMA LOCAL: {count} entrada(s) substituida(s)")


addons = [TemaLocal()]
