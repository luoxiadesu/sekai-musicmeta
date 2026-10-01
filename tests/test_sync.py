import base64
from contextlib import contextmanager
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("vpngate_sync", ROOT / "scripts/vpngate_sync.py")
vpn = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vpn)
FILES = ["music_metas.json", "music_metas-cn.json", "music_metas-tc.json", "music_metas-en.json", "music_metas-kr.json"]


def config(address="8.8.8.8", extra=""):
    raw = f"client\nproto tcp\nremote {address} 443\n{extra}\n"
    for name in ("ca", "cert", "key"):
        raw += f"<{name}>\n-----BEGIN CERTIFICATE-----\nYWJj\n-----END CERTIFICATE-----\n</{name}>\n"
    return base64.b64encode(raw.encode()).decode()


class ConfigTests(unittest.TestCase):
    def test_untrusted_directives_and_default_route_are_not_used(self):
        encoded = config(extra="script-security 2\nup /tmp/untrusted\nplugin /tmp/plugin.so\nredirect-gateway def1\ndhcp-option DNS 1.2.3.4")
        result, _ = vpn.make_config(encoded, ["104.21.1.2"])
        self.assertNotIn("/tmp/untrusted", result)
        self.assertNotIn("plugin.so", result)
        self.assertNotIn("redirect-gateway def1", result)
        self.assertNotIn("dhcp-option", result)
        self.assertIn("route-nopull", result)
        self.assertIn("route 104.21.1.2 255.255.255.255 vpn_gateway", result)

    def test_rejects_private_endpoint(self):
        with self.assertRaises(ValueError):
            vpn.make_config(config("127.0.0.1"), ["104.21.1.2"])

    def test_rejects_directive_inside_pem(self):
        raw = base64.b64decode(config()).decode().replace("YWJj", "YWJj\n</ca>\nup /tmp/untrusted\n<ca>", 1)
        with self.assertRaises(ValueError):
            vpn.make_config(base64.b64encode(raw.encode()).decode(), ["104.21.1.2"])

    def test_feed_handles_bom_footer_bad_nodes_and_network_diversity(self):
        output = io.StringIO()
        output.write("\ufeff*vpn_servers\n")
        writer = csv.writer(output)
        writer.writerow(["#HostName", "IP", "Score", "CountryShort", "OpenVPN_ConfigData_Base64"])
        for address, score, encoded in [("8.8.8.8", 100, config()), ("8.8.8.9", 90, config("8.8.8.9")), ("1.1.1.1", 80, config("1.1.1.1")), ("9.9.9.9", 120, "invalid")]:
            writer.writerow(["node", address, score, "JP", encoded])
        output.write("*\n")
        nodes = vpn.candidates(output.getvalue(), ["104.21.1.2"], ["JP", "KR"])
        self.assertEqual([node[0] for node in nodes], ["8.8.8.8", "1.1.1.1", "8.8.8.9"])


@contextmanager
def upstream(responses):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = responses[self.path.removeprefix("/")]
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts/sync.sh", self.repo / "scripts/sync.sh")
        (self.repo / "data").mkdir()
        self.original = b'[{"music_id": 1, "difficulty": "easy"}]\n'
        self.updated = b'[{"music_id": 2, "difficulty": "expert"}]\n'
        for name in FILES:
            (self.repo / "data" / name).write_bytes(self.original)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout.strip()

    def run_sync(self, responses, **env):
        with upstream(responses) as source:
            environment = {key: value for key, value in os.environ.items() if not key.startswith(("VPN_", "CURL_")) and key not in {"SRC", "OUT", "SKIP_PUSH", "FETCH_ONLY"}}
            result = subprocess.run(["bash", "scripts/sync.sh"], cwd=self.repo, env={**environment, "SRC": source, "CURL_RETRIES": "0", "FETCH_ONLY": "1", "NO_PROXY": "127.0.0.1", **env}, capture_output=True, text=True, timeout=15)
        self.assertEqual(list((self.repo / "data").glob(".sync.*")), [])
        return result

    def test_failure_in_last_file_keeps_all_original_data(self):
        responses = {name: (200, self.updated) for name in FILES}
        responses[FILES[-1]] = (403, b"Cloudflare blocked")
        self.assertNotEqual(self.run_sync(responses).returncode, 0)
        for name in FILES:
            self.assertEqual((self.repo / "data" / name).read_bytes(), self.original)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_invalid_json_shapes_cannot_replace_data(self):
        for invalid in [b"<html>challenge</html>", b"[]", b'{"error": "blocked"}', b'[{}]']:
            with self.subTest(invalid=invalid):
                responses = {name: (200, self.updated) for name in FILES}
                responses[FILES[-1]] = (200, invalid)
                self.assertNotEqual(self.run_sync(responses).returncode, 0)
                self.assertEqual(self.git("status", "--porcelain"), "")

    def test_fetch_only_updates_all_data_without_commit(self):
        head = self.git("rev-parse", "HEAD")
        result = self.run_sync({name: (200, self.updated) for name in FILES})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        for name in FILES:
            self.assertEqual((self.repo / "data" / name).read_bytes(), self.updated)

    def test_unchanged_data_does_not_commit(self):
        head = self.git("rev-parse", "HEAD")
        result = self.run_sync({name: (200, self.original) for name in FILES}, FETCH_ONLY="0", SKIP_PUSH="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_sync_does_not_commit_other_staged_files(self):
        (self.repo / "unrelated.txt").write_text("Unrelated staged work")
        self.git("add", "unrelated.txt")
        result = self.run_sync({name: (200, self.updated) for name in FILES}, FETCH_ONLY="0", SKIP_PUSH="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "unrelated.txt")
        changed = self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
        self.assertEqual(sorted(changed), sorted(f"data/{name}" for name in FILES))


if __name__ == "__main__":
    unittest.main()
