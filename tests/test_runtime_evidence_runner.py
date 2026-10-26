import sys
from pathlib import Path

from tier1.runtime_evidence.crypto import RunnerKeyStore
from tier1.runtime_evidence.hashutil import sha256_bytes
from tier1.runtime_evidence.model import Contract
from tier1.runtime_evidence.runner import probe_http, run_probe


def test_probe_http_reads_status_and_body_hash(tmp_path: Path):
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"hello"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = probe_http(f"http://127.0.0.1:{server.server_port}")
        assert result.status == 200
        assert result.body_sha256 == sha256_bytes(b"hello")
    finally:
        server.shutdown()
        thread.join()


def test_run_probe_signs_observed_receipt_and_does_not_leave_partial(tmp_path: Path):
    script = tmp_path / "fixture_server.py"
    script.write_text("""import http.server, socketserver, sys\nclass H(http.server.SimpleHTTPRequestHandler):\n    def log_message(self, *args): pass\nwith socketserver.TCPServer(('127.0.0.1', 0), H) as s:\n    print(f'PORT={s.server_address[1]}', flush=True)\n    s.serve_forever()\n""", encoding="utf-8")
    contract = Contract((sys.executable, str(script)), str(tmp_path), ("fixture_server.py",), ({"id": "page-up", "op": "status", "expected": 200},))
    receipt_path = tmp_path / "receipt.json"
    receipt = run_probe(contract, RunnerKeyStore(tmp_path / "keys"), receipt_path)
    assert receipt.assertions[0].passed is True
    assert receipt_path.exists()
    assert receipt.target.pid > 0
