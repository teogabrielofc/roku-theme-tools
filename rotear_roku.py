"""Roteamento por hostname para usar o coletor sem modificar os temas."""
from urllib.parse import urlsplit
from mitmproxy import ctx, http


class Rotear:
    def load(self, loader):
        loader.add_option("route_client", str, "192.168.18.76", "IP da Roku TV")

    def requestheaders(self, flow):
        peer = flow.client_conn.peername
        if not peer or peer[0] != ctx.options.route_client:
            flow.response = http.Response.make(403, b"Cliente nao permitido"); return
        try: host = (urlsplit("//" + (flow.request.host_header or "")).hostname or "").lower().rstrip(".")
        except ValueError: host = ""
        if not any(host == suffix or host.endswith("." + suffix) for suffix in ("roku.com", "rokuapi.net")):
            flow.response = http.Response.make(403, b"Dominio nao permitido"); return
        flow.request.host = host
        flow.request.scheme = "https" if flow.client_conn.tls else "http"
        flow.request.port = 443 if flow.client_conn.tls else 80
        flow.server_conn.sni = host if flow.client_conn.tls else None


addons = [Rotear()]
