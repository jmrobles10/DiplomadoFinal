"""
Servidor de archivos estático con cabeceras CORS (para que n8n pueda "Import from URL" desde el navegador
y para servir el front en local).

Uso: python scripts/serve_cors.py <puerto> <carpeta>
     python scripts/serve_cors.py 8766 C:\Fuentes_Git\rag-f1-n8n\workflows
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args)); sys.stdout.flush()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    directory = sys.argv[2] if len(sys.argv) > 2 else "."
    handler = partial(CORSHandler, directory=directory)
    print(f"Sirviendo {directory} en http://localhost:{port} con CORS", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()
