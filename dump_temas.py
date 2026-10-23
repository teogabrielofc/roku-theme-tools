"""Extrai temas de flows, captura ao vivo ou catalogos; baixa recursos opcionais."""
import argparse
import json
from pathlib import Path
from tema_common import (records, key, theme_xml, catalog_entries, read_json,
                         write_json, fetch, save_theme)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", nargs="*", help="Cole URLs XML ou caminhos de flows diretamente")
    p.add_argument("--flows", nargs="+", default=[], help="Um ou mais dumps mitmproxy")
    p.add_argument("--live", type=Path, help="Pasta criada por dump_ao_vivo.py")
    p.add_argument("--catalog", nargs="+", default=[], help="Catalogos JSON salvos")
    p.add_argument("--url", action="extend", nargs="+", default=[], help="URLs XML; baixa os recursos automaticamente")
    p.add_argument("--download", action="store_true", help="Baixa temas do catalogo e recursos faltantes")
    p.add_argument("--out", type=Path, default=Path("dump-temas"))
    a = p.parse_args(argv)
    for value in a.inputs:
        if value.lower().startswith(("http://", "https://")):
            a.url.append(value)
        else:
            a.flows.append(value)
    if not (a.flows or a.live or a.catalog or a.url):
        value = input("Cole a URL XML do tema ou arraste um arquivo flows: ").strip().strip('\"\'')
        if not value: p.error("Informe uma URL XML ou captura")
        if value.lower().startswith(("http://", "https://")):
            a.url = [url.strip('\"\'') for url in value.split()]
            if not all(url.lower().startswith(("http://", "https://")) for url in a.url):
                p.error("Cole URLs HTTP/HTTPS separadas por espaco")
        else:
            a.flows = [value]
    download_resources = a.download or bool(a.url)
    cache = {}; xmls = {}; catalogs = []; entries = []
    def add(url, body, mime):
        cache[key(url)] = (body, mime)
        if theme_xml(body) is not None:
            xmls[key(url)] = body
        if url.split("?", 1)[0].endswith("/themes-service/v1/dynamic"):
            try: catalogs.append(json.loads(body))
            except (ValueError, UnicodeError): pass
    for file in a.flows:
        print("Lendo:", file)
        for record in records(file): add(*record)
    if a.live:
        for item in read_json(a.live / "index.json"):
            add(item["url"], (a.live / item["file"]).read_bytes(), item.get("mime", ""))
    for file in a.catalog: catalogs.append(read_json(file))
    for catalog in catalogs: entries.extend(catalog_entries(catalog))
    entries = list({e["url"]: e for e in entries}.values())
    for i, catalog in enumerate(catalogs): write_json(a.out / "catalogs" / f"catalog-{i+1}.json", catalog)
    failures = []
    urls = list(a.url)
    if a.download: urls.extend(e["url"] for e in entries)
    for url in dict.fromkeys(urls):
        if key(url) in xmls: continue
        try:
            print("Baixando XML:", url)
            final_url, body, mime = fetch(url)
            if theme_xml(body) is None: raise ValueError("Servidor nao retornou XML de tema")
            xmls[key(final_url)] = body
            if not any(key(e["url"]) == key(url) for e in entries):
                entries.append({"name": theme_xml(body).findtext("name") or "Tema", "url": url, "category": "direct"})
        except Exception as exc: failures.append({"url": url, "error": str(exc)})
    results = []
    for url, body in xmls.items():
        print("Extraindo XML e recursos:", url)
        folder, info = save_theme(a.out, url, body, cache, entries, download_resources)
        results.append({"name": info["name"], "category": info["category"],
                        "manifest": str(folder.relative_to(a.out) / "theme.json"),
                        "complete": info["complete"], "missing": len(info["missing"])})
        print(f"{info['name']}: {len(info['files'])} arquivos; faltam {len(info['missing'])} -> {folder}")
    write_json(a.out / "catalog-index.json", entries)
    write_json(a.out / "report.json", {"themes": results, "download_errors": failures,
        "note": "Sazonais dependem do catalogo enviado pelo servidor; captured/catalog nao implica tema normal."})
    print(f"Pronto: {len(results)} tema(s) extraido(s), {len(entries)} entrada(s) de catalogo, {len(failures)} erro(s).")
    return 0 if results and not failures and all(t["complete"] for t in results) else 2


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (OSError, ValueError) as exc: raise SystemExit("Erro: " + str(exc))
