import contextlib
import gzip
import io
import json
from pathlib import Path
import runpy
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import zipfile

from PIL import Image
import criar_tema
import dump_temas
from tema_common import client_ip, catalog_entries, pkg_refs, read_json, save_theme, theme_xml

EXCEPTIONS = types.ModuleType("mitmproxy.exceptions")
EXCEPTIONS.OptionsError = ValueError

ROOT = Path(__file__).resolve().parents[1]


def xml(name="Regular"):
    return (f'<theme><name>{name}</name><version>1</version>'
            '<FONTS><color name="TextColor"><rgba>0xFFFFFFFF</rgba></color></FONTS>'
            '<bitmap name="BackgroundBitmap"><hdurl>pkg:/theme/Base/HD/background.png</hdurl></bitmap>'
            '</theme>').encode()


def tnet(value):
    if isinstance(value, dict):
        body = b"".join(tnet(k) + tnet(v) for k, v in value.items()); tag = b"}"
    elif isinstance(value, list): body = b"".join(tnet(v) for v in value); tag = b"]"
    elif isinstance(value, str): body = value.encode(); tag = b";"
    elif isinstance(value, bytes): body = value; tag = b","
    elif isinstance(value, int): body = str(value).encode(); tag = b"#"
    else: raise TypeError(value)
    return str(len(body)).encode() + b":" + body + tag


class ToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        b = io.BytesIO(); Image.new("RGB", (1280, 720), "#123456").save(b, "PNG")
        cls.png = b.getvalue()
        png = cls.png
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/regular.xml":
                    self.send_response(302); self.send_header("Location", "/regular/Theme.xml"); self.end_headers(); return
                if path.endswith(".xml"):
                    body = xml("Holiday" if "holiday" in path.lower() else "Regular")
                elif path.endswith("/Base/HD/background.png"): body = png
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.end_headers(); self.wfile.write(body)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.worker.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def dump(self, args):
        with contextlib.redirect_stdout(io.StringIO()):
            return dump_temas.main(args)

    def test_direct_urls_download_assets_without_flag(self):
        out = self.root / "dump"
        self.assertEqual(self.dump([self.url + "/regular.xml", self.url + "/holiday/Theme.xml", "--out", str(out)]), 0)
        report = read_json(out / "report.json")
        self.assertEqual(len(report["themes"]), 2)
        self.assertTrue(all(t["complete"] for t in report["themes"]))
        for t in report["themes"]:
            manifest = out / t["manifest"]
            info = read_json(manifest)
            self.assertEqual(len(info["files"]), 2)
            with Image.open(manifest.parent / info["files"]["Base/HD/background.png"]) as image:
                image.verify()

    def test_interactive_urls(self):
        out = self.root / "dump"
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value=self.url + "/regular.xml"):
            self.assertEqual(self.dump(["--out", str(out)]), 0)

    def test_seasonal_catalog(self):
        catalog = {"network": [{"name": "Regular", "url": self.url + "/regular.xml"}],
                   "seasonal": [{"name": "Holiday", "url": self.url + "/holiday/Theme.xml"}]}
        source = self.root / "catalog.json"; source.write_text(json.dumps(catalog))
        out = self.root / "dump"
        self.assertEqual(self.dump(["--catalog", str(source), "--download", "--out", str(out)]), 0)
        report = read_json(out / "report.json")
        self.assertIn("seasonal", [t["category"] for t in report["themes"]])

    def test_offline_compressed_flow(self):
        prefix = "/proxy/assets/TestPkg/"
        def flow(path, body, headers):
            return {"request": {"host": "cloudservices.roku.com", "scheme": b"http", "port": 80, "path": path.encode()},
                    "response": {"status_code": 200, "content": body, "headers": headers}}
        source = self.root / "flows"
        source.write_bytes(tnet(flow(prefix + "Theme.xml", gzip.compress(xml()), [[b"content-encoding", b"gzip"]]))
                           + tnet(flow(prefix + "Base/HD/background.png", self.png, [])))
        out = self.root / "dump"
        self.assertEqual(self.dump(["--flows", str(source), "--out", str(out)]), 0)
        self.assertTrue(read_json(out / "report.json")["themes"][0]["complete"])

    def test_missing_assets_are_reported(self):
        folder, info = save_theme(self.root, self.url + "/regular/Theme.xml", xml(), {}, [], False)
        self.assertFalse(info["complete"])
        self.assertEqual(info["missing"], ["Base/HD/background.png"])

    def test_unsafe_asset_references_are_rejected(self):
        root = theme_xml(b'<theme><hdurl>pkg:/theme/../../escape.png</hdurl><hdurl>pkg:/theme/C:\\escape.png</hdurl><hdurl>pkg:/theme/safe.png</hdurl></theme>')
        with self.assertRaisesRegex(ValueError, "Unsafe theme asset"):
            pkg_refs(root)
        self.assertEqual(pkg_refs(theme_xml(b'<theme><url>pkg:/theme/safe.png</url></theme>')), ["safe.png"])

    def test_creator_and_generated_addon(self):
        base, _ = save_theme(self.root / "bases", "http://cloudservices.roku.com/pkg/Theme.xml", xml(),
                             {"http://cloudservices.roku.com/pkg/Base/HD/background.png": (self.png, "image/png")}, [], False)
        wallpaper = self.root / "wallpaper.png"; wallpaper.write_bytes(self.png)
        out = self.root / "custom theme"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(criar_tema.main(["--base", str(base), "--name", "Custom", "--wallpaper", str(wallpaper),
                                             "--text", "#FFFFFF", "--client", "192.0.2.50", "--hide-ad", "--out", str(out)]), 0)
        config = read_json(out / "config.json")
        self.assertEqual(config["name"], "Custom")
        self.assertEqual(config["client"], "192.0.2.50")
        self.assertTrue(config["hide_google_ad"])
        self.assertIn("LOCAL THEME", (out / "HOW-TO-APPLY.txt").read_text())
        self.assertTrue((out / "transparent.webp").is_file())
        with zipfile.ZipFile(str(out) + ".zip") as z:
            self.assertIsNone(z.testzip())
        class Response:
            def __init__(self, status, content, headers=None):
                self.status_code = status; self.content = content; self.headers = headers or {}
            @property
            def text(self): return self.content.decode()
            @text.setter
            def text(self, value): self.content = value.encode()
        module = types.ModuleType("mitmproxy")
        module.ctx = types.SimpleNamespace(options=types.SimpleNamespace(custom_client="192.0.2.50"),
                                            log=types.SimpleNamespace(info=lambda x: None, error=lambda x: None))
        module.http = types.SimpleNamespace(Response=types.SimpleNamespace(make=Response))
        with patch.dict("sys.modules", {"mitmproxy": module, "mitmproxy.exceptions": EXCEPTIONS}):
            addon = runpy.run_path(str(out / "apply_theme.py"))["addons"][0]
            addon.load(types.SimpleNamespace(add_option=lambda *args: None))
            def flow(ip):
                return types.SimpleNamespace(client_conn=types.SimpleNamespace(peername=(ip, 123), tls=False),
                    server_conn=types.SimpleNamespace(sni=None), metadata={}, response=None,
                    request=types.SimpleNamespace(host_header="cloudservices.roku.com", path=addon.prefix + config["xml_key"], headers={}))
            good = flow("192.0.2.50"); addon.requestheaders(good)
            self.assertEqual(good.response.status_code, 200)
            bad = flow("192.0.2.99"); addon.requestheaders(bad)
            self.assertEqual(bad.response.status_code, 403)
            denied = flow("192.0.2.50")
            denied.request.host_header = "roku.com.attacker.invalid"
            addon.requestheaders(denied)
            self.assertEqual(denied.response.status_code, 403)
            module.ctx.options.custom_client = ""
            empty = flow("192.0.2.50"); addon.requestheaders(empty)
            self.assertEqual(empty.response.status_code, 403)

    def test_collector_includes_seasonal(self):
        module = types.ModuleType("mitmproxy")
        module.ctx = types.SimpleNamespace(options=types.SimpleNamespace(theme_client="192.0.2.50", include_seasonal=True))
        with patch.dict("sys.modules", {"mitmproxy": module, "mitmproxy.exceptions": EXCEPTIONS}):
            addon = runpy.run_path(str(ROOT / "dump_ao_vivo.py"))["addons"][0]
            flow = types.SimpleNamespace(client_conn=types.SimpleNamespace(peername=("192.0.2.50", 1)),
                request=types.SimpleNamespace(host_header="themes-service.sr.roku.com", path="/themes-service/v1/dynamic?env=PROD&exclude=seasonal%2Cscreensaver", headers={}))
            addon.requestheaders(flow)
            self.assertNotIn("seasonal", flow.request.path)
            self.assertIn("screensaver", flow.request.path)
            self.assertIn("env=PROD", flow.request.path)

    def base_theme(self):
        base, _ = save_theme(self.root / "bases", "http://cloudservices.roku.com/pkg/Theme.xml", xml(),
                            {"http://cloudservices.roku.com/pkg/Base/HD/background.png": (self.png, "image/png")}, [], False)
        return base

    def create_args(self, base, out):
        return ["--base", str(base), "--client", "192.0.2.50", "--name", "Test", "--out", str(out)]

    def assert_creator_rejected(self, args):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            criar_tema.main(args)
        self.assertEqual(error.exception.code, 2)

    def test_creator_requires_explicit_tv_and_validates_address(self):
        self.assert_creator_rejected(["--name", "Test"])
        for value in ("", "YOUR_TV_IP", "0.0.0.0", "::", "224.0.0.1", "192.0.2.0/24"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                client_ip(value)
        self.assertEqual(client_ip("2001:db8::50"), "2001:db8::50")

    def test_existing_zip_does_not_create_output(self):
        base = self.base_theme(); out = self.root / "new-theme"
        archive = Path(str(out) + ".zip"); archive.write_bytes(b"original")
        self.assert_creator_rejected(self.create_args(base, out))
        self.assertFalse(out.exists())
        self.assertEqual(archive.read_bytes(), b"original")

    def test_creator_rejects_unsafe_manifest_before_writing(self):
        base = self.base_theme(); manifest = base / "theme.json"
        original = read_json(manifest)
        for bad in (str(base / "assets/Theme.xml"), "../outside.png", "C:/outside.png"):
            with self.subTest(path=bad):
                info = dict(original); info["files"] = {**original["files"], "extra.png": bad}
                manifest.write_text(json.dumps(info))
                out = self.root / "rejected"
                self.assert_creator_rejected(self.create_args(base, out))
                self.assertFalse(out.exists())

    def test_unlisted_xml_and_missing_background_do_not_create_output(self):
        base = self.base_theme(); manifest = base / "theme.json"; info = read_json(manifest)
        xml_path = base / info["xml"]
        xml_path.write_bytes(b"<theme><name>Unsupported</name></theme>")
        out = self.root / "unsupported"
        self.assert_creator_rejected(self.create_args(base, out))
        self.assertFalse(out.exists())
        info["xml"] = "../outside.xml"; manifest.write_text(json.dumps(info))
        self.assert_creator_rejected(self.create_args(base, out))
        self.assertFalse(out.exists())

    def test_base_output_overlap_preserves_base(self):
        base = self.base_theme(); manifest = (base / "theme.json").read_bytes()
        self.assert_creator_rejected(self.create_args(base, base / "nested"))
        self.assertFalse((base / "nested").exists())
        self.assertEqual((base / "theme.json").read_bytes(), manifest)

    def test_collector_default_is_empty_and_seasonal_is_opt_in(self):
        module = types.ModuleType("mitmproxy")
        module.ctx = types.SimpleNamespace(options=types.SimpleNamespace(theme_client="", include_seasonal=False))
        with patch.dict("sys.modules", {"mitmproxy": module, "mitmproxy.exceptions": EXCEPTIONS}):
            addon = runpy.run_path(str(ROOT / "dump_ao_vivo.py"))["addons"][0]
            defaults = {}
            addon.load(types.SimpleNamespace(add_option=lambda name, kind, default, help: defaults.update({name: default})))
            self.assertEqual(defaults["theme_client"], "")
            self.assertFalse(defaults["include_seasonal"])
            path = "/themes-service/v1/dynamic?exclude=seasonal"
            flow = types.SimpleNamespace(client_conn=types.SimpleNamespace(peername=("192.0.2.50", 1)),
                request=types.SimpleNamespace(host_header="themes-service.sr.roku.com", path=path, headers={}))
            self.assertFalse(addon.ours(flow))
            module.ctx.options.theme_client = "192.0.2.50"
            addon.requestheaders(flow)
            self.assertEqual(flow.request.path, path)

    def test_router_has_no_default_client(self):
        module = types.ModuleType("mitmproxy")
        module.ctx = types.SimpleNamespace(options=types.SimpleNamespace(route_client=""))
        module.http = types.SimpleNamespace(Response=types.SimpleNamespace(
            make=lambda status, body: types.SimpleNamespace(status_code=status)))
        with patch.dict("sys.modules", {"mitmproxy": module, "mitmproxy.exceptions": EXCEPTIONS}):
            addon = runpy.run_path(str(ROOT / "rotear_roku.py"))["addons"][0]
            defaults = {}
            addon.load(types.SimpleNamespace(add_option=lambda name, kind, default, help: defaults.update({name: default})))
            self.assertEqual(defaults["route_client"], "")
            flow = types.SimpleNamespace(client_conn=types.SimpleNamespace(peername=("192.0.2.50", 1)), response=None)
            addon.requestheaders(flow)
            self.assertEqual(flow.response.status_code, 403)
            module.ctx.options.route_client = "0.0.0.0"
            with self.assertRaises(ValueError): addon.configure({"route_client"})

    def test_missing_dump_input_is_actionable_in_noninteractive_mode(self):
        with patch("sys.stdin.isatty", return_value=False), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            dump_temas.main([])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__": unittest.main()
