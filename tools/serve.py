"""Servidor local de desenvolvimento do AR 75 LAB.

Serve a raiz do repositório e aceita POST /__save?path=<caminho relativo>
para gravar arquivos gerados no navegador (USDZ, poster, og:image).
Uso: python3 tools/serve.py [porta]
"""
import http.server
import mimetypes
import os
import sys
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8833

mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/vnd.usdz+zip", ".usdz")
mimetypes.add_type("text/javascript", ".mjs")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/__save":
            self.send_error(404)
            return
        rel = parse_qs(url.query).get("path", [""])[0]
        dest = os.path.realpath(os.path.join(ROOT, rel))
        if not rel or not dest.startswith(ROOT + os.sep):
            self.send_error(400, "caminho inválido")
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(f"ok {len(body)} bytes -> {rel}".encode())


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
