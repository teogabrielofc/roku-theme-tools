"""Addon: inclui sazonais na consulta e grava apenas catalogos/recursos de temas."""
from pathlib import Path
import hashlib
import json
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
from mitmproxy import ctx
from tema_common import theme_xml, write_json


class DumpTemas:
    def load(self, loader):
        loader.add_option("temas_dir", str, "dump-ao-vivo", "Pasta para recursos capturados")
        loader.add_option("temas_sazonais", bool, True, "Retirar seasonal do parametro exclude")
        loader.add_option("temas_client", str, "192.168.18.76", "IP da TV")

    def ours(self, flow):
        peer = flow.client_conn.peername
        return peer and peer[0] == ctx.options.temas_client

    def requestheaders(self, flow):
        if not self.ours(flow): return
        host = (flow.request.host_header or "").split(":")[0].lower()
        parts = urlsplit(flow.request.path)
        if host == "themes-service.sr.roku.com" and parts.path == "/themes-service/v1/dynamic":
            if ctx.options.temas_sazonais:
                query = []
                for k, v in parse_qsl(parts.query, keep_blank_values=True):
                    if k == "exclude":
                        v = ",".join(x for x in v.split(",") if x.strip().lower() != "seasonal")
                    query.append((k, v))
                flow.request.path = urlunsplit(("", "", parts.path, urlencode(query), ""))
            for header in ("if-none-match", "if-modified-since"):
                flow.request.headers.pop(header, None)

    def response(self, flow):
        if not self.ours(flow) or not flow.response or flow.response.status_code != 200: return
        host = (flow.request.host_header or "").split(":")[0].lower()
        path = flow.request.path.split("?", 1)[0]
        catalog = host == "themes-service.sr.roku.com" and path == "/themes-service/v1/dynamic"
        resource = host == "cloudservices.roku.com" and (path.startswith("/proxy/assets/") or "/wallpapers/" in path)
        if not (catalog or resource): return
        body = flow.response.content
        if not body: return
        folder = Path(ctx.options.temas_dir).resolve()
        url = flow.request.url
        digest = hashlib.sha256(url.encode()).hexdigest()
        file = "cache/" + digest + ".bin"
        (folder / "cache").mkdir(parents=True, exist_ok=True)
        (folder / file).write_bytes(body)
        index_file = folder / "index.json"
        index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else []
        index = [item for item in index if item["url"] != url]
        index.append({"url": url, "file": file, "mime": flow.response.headers.get("content-type", "")})
        write_json(index_file, index)
        ctx.log.info(f"DUMP TEMAS: {host}{path}")


addons = [DumpTemas()]
