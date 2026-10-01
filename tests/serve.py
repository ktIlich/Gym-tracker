"""Статический сервер для тестов: как http.server, но адрес Worker в test/index.html подменяется пустым.
Тесты, которым нужен адрес, подставляют его сами (replace 'const BACKUP_ENDPOINT="";')."""
import http.server, re, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.split("?")[0] == "/test/index.html":
            raw = open(os.path.join(ROOT, "test", "index.html"), "rb").read().decode("utf-8")
            raw = re.sub(r'const BACKUP_ENDPOINT="[^"]*";', 'const BACKUP_ENDPOINT="";', raw, count=1)
            b = raw.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else: super().do_GET()
http.server.ThreadingHTTPServer(("", int(sys.argv[1])), H).serve_forever()
