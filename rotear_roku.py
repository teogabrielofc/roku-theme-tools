"""Route by hostname to collect themes without changing their content."""
from urllib.parse import urlsplit
from mitmproxy import ctx, http
from mitmproxy.exceptions import OptionsError
from tema_common import client_ip


class Rotear:
    def load(self, loader):
        loader.add_option("route_client", str, "", "Required TV IP address; empty blocks all clients")

    def configure(self, updated):
        if "route_client" in updated and ctx.options.route_client:
            try:
                client_ip(ctx.options.route_client)
            except ValueError as exc:
                raise OptionsError(str(exc)) from exc

    def requestheaders(self, flow):
        peer = flow.client_conn.peername
        if not peer or not ctx.options.route_client or client_ip(peer[0]) != client_ip(ctx.options.route_client):
            flow.response = http.Response.make(403, b"Client not allowed"); return
        try: host = (urlsplit("//" + (flow.request.host_header or "")).hostname or "").lower().rstrip(".")
        except ValueError: host = ""
        if not any(host == suffix or host.endswith("." + suffix) for suffix in ("roku.com", "rokuapi.net")):
            flow.response = http.Response.make(403, b"Domain not allowed"); return
        flow.request.host = host
        flow.request.scheme = "https" if flow.client_conn.tls else "http"
        flow.request.port = 443 if flow.client_conn.tls else 80
        flow.server_conn.sni = host if flow.client_conn.tls else None


addons = [Rotear()]
