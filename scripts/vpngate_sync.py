#!/usr/bin/env python3
"""Fetch musicmeta over temporary VPN Gate tunnels on a Linux CI runner."""

import base64
import csv
import io
import ipaddress
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlsplit


API_URL = "https://www.vpngate.net/api/iphone/"
REPO_DIR = Path(__file__).resolve().parent.parent
INTERFACE = "vpngate0"


def make_config(encoded, addresses):
    """Rebuild a minimal config; never run directives from the public feed."""
    raw = base64.b64decode(encoded, validate=True).decode("utf-8-sig")
    blocks = {}
    for name in ("ca", "cert", "key"):
        matches = re.findall(rf"<{name}>\s*(.*?)\s*</{name}>", raw, re.S)
        if len(matches) != 1 or not re.fullmatch(
            r"-----BEGIN ([A-Z ]+)-----\s+[A-Za-z0-9+/=\s]+-----END \1-----",
            matches[0],
        ):
            raise ValueError(f"Missing or invalid {name} PEM block")
        blocks[name] = matches[0]

    directives = re.sub(r"<(ca|cert|key)>.*?</\1>", "", raw, flags=re.S)
    remotes = re.findall(r"^remote\s+(\S+)\s+(\d+)\s*$", directives, re.M)
    protocols = re.findall(r"^proto\s+(\S+)\s*$", directives, re.M)
    if len(remotes) != 1 or len(protocols) != 1:
        raise ValueError("Expected exactly one remote and protocol")
    remote, port = remotes[0]
    remote = ipaddress.IPv4Address(remote)
    if not remote.is_global or not 1 <= int(port) <= 65535:
        raise ValueError("Invalid VPN endpoint")
    protocol = {"tcp": "tcp-client", "tcp-client": "tcp-client", "udp": "udp"}.get(protocols[0])
    if protocol is None:
        raise ValueError("Unsupported VPN protocol")

    lines = [
        "client", f"dev {INTERFACE}", "dev-type tun", f"proto {protocol}",
        f"remote {remote} {int(port)}", "nobind", "resolv-retry 5",
        "connect-retry-max 1", "connect-timeout 10", "auth-nocache",
        "cipher AES-128-CBC", "data-ciphers AES-128-CBC",
        "data-ciphers-fallback AES-128-CBC", "auth SHA1",
        # VPN Gate's shared client certificate is signed with SHA-1.
        "tls-cipher DEFAULT:@SECLEVEL=0", "script-security 1",
        # Ignore pushed routes/DNS; only upstream IPv4 addresses use the VPN.
        "route-nopull", 'pull-filter ignore "redirect-gateway"',
        "verb 3",
    ]
    lines.extend(f"route {ipaddress.IPv4Address(address)} 255.255.255.255 vpn_gateway" for address in addresses)
    lines.extend(f"<{name}>\n{pem}\n</{name}>" for name, pem in blocks.items())
    return "\n".join(lines) + "\n", str(remote)


def candidates(feed, addresses, countries):
    lines = feed.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "*vpn_servers":
        raise ValueError("Unexpected VPN Gate API response")
    reader = csv.DictReader(io.StringIO("\n".join(lines[1:])))
    if not {"IP", "Score", "CountryShort", "OpenVPN_ConfigData_Base64"}.issubset(reader.fieldnames or []):
        raise ValueError("Missing VPN Gate API fields")

    nodes = []
    for row in reader:
        if not row.get("OpenVPN_ConfigData_Base64"):
            continue
        try:
            config, address = make_config(row["OpenVPN_ConfigData_Base64"], addresses)
            if address != row["IP"]:
                continue
            country = row["CountryShort"]
            rank = countries.index(country) if country in countries else len(countries)
            nodes.append((rank, -int(row["Score"]), address, config))
        except (ValueError, UnicodeError):
            continue

    # Spread attempts across networks instead of trying the same /24 repeatedly.
    first, rest, networks, seen = [], [], set(), set()
    for _, _, address, config in sorted(nodes):
        if address in seen:
            continue
        seen.add(address)
        network = ipaddress.ip_network(f"{address}/24", strict=False)
        (rest if network in networks else first).append((address, config))
        networks.add(network)
    return first + rest


class Tunnel:
    def __init__(self, directory):
        self.config = directory / "client.ovpn"
        self.pidfile = directory / "openvpn.pid"
        self.log = directory / "openvpn.log"

    def start(self, config, timeout):
        self.config.write_text(config)
        self.config.chmod(0o600)
        # Pre-create these as the runner user so root's restrictive umask cannot
        # prevent readiness checks and cleanup from reading them.
        self.pidfile.touch(mode=0o600)
        self.log.touch(mode=0o600)
        subprocess.run([
            "sudo", "-n", "openvpn", "--config", str(self.config),
            "--daemon", "--writepid", str(self.pidfile), "--log", str(self.log),
        ], check=True, timeout=15)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            log = self.log.read_text(errors="replace") if self.log.exists() else ""
            if "Initialization Sequence Completed" in log:
                return
            if any(message in log for message in ("Exiting due to fatal error", "AUTH_FAILED", "SIGTERM[", "Options error")):
                break
            time.sleep(1)
        raise RuntimeError("VPN did not become ready before the connection deadline")

    def stop(self):
        if not self.pidfile.exists():
            return
        value = self.pidfile.read_text().strip()
        if not value:
            return
        pid = int(value)
        if pid <= 1:
            raise RuntimeError("Invalid OpenVPN PID")
        subprocess.run(["sudo", "-n", "kill", "-TERM", str(pid)], check=False, capture_output=True, timeout=10)
        for _ in range(50):
            if not Path(f"/proc/{pid}").exists():
                return
            time.sleep(0.1)
        subprocess.run(["sudo", "-n", "kill", "-KILL", str(pid)], check=True, timeout=10)


def fetch(environment, timeout):
    # A process group lets timeout/cancellation also stop curl and run bash's EXIT trap.
    process = subprocess.Popen(["bash", "scripts/sync.sh"], cwd=REPO_DIR, env=environment, start_new_session=True)
    try:
        return process.wait(timeout=timeout) == 0
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def main():
    source = os.environ.get("SRC", "https://sekai-data.3-3.dev")
    url = urlsplit(source)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("VPN sync requires an HTTPS SRC without credentials")
    port = url.port or 443
    addresses = sorted({result[4][0] for result in socket.getaddrinfo(url.hostname, port, socket.AF_INET, socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.IPv4Address(address).is_global for address in addresses):
        raise ValueError("SRC must resolve to public IPv4 addresses")
    countries = [value.strip().upper() for value in os.environ.get("VPNGATE_COUNTRIES", "JP,KR").split(",") if value.strip()]
    max_nodes = int(os.environ.get("VPNGATE_MAX_NODES", "6"))
    connect_timeout = int(os.environ.get("VPNGATE_CONNECT_TIMEOUT", "35"))
    fetch_timeout = int(os.environ.get("VPNGATE_FETCH_TIMEOUT", "180"))
    if min(max_nodes, connect_timeout, fetch_timeout) < 1:
        raise ValueError("VPN Gate limits must be positive")

    response = subprocess.run([
        "curl", "--fail", "--silent", "--show-error", "--location",
        "--connect-timeout", "10", "--max-time", "45", "--retry", "2", API_URL,
    ], check=True, capture_output=True, text=True, timeout=150)
    nodes = candidates(response.stdout, addresses, countries)[:max_nodes]
    if not nodes:
        raise RuntimeError("VPN Gate returned no usable OpenVPN nodes")
    environment = {
        **os.environ, "SRC": source, "FETCH_ONLY": "1", "CURL_RETRIES": "0",
        "CURL_MAX_TIME": "40", "VPN_INTERFACE": INTERFACE,
        "VPN_RESOLVE": f"{url.hostname}:{port}:{','.join(addresses)}",
    }
    for index, (address, config) in enumerate(nodes, 1):
        print(f"Trying VPN Gate node {index}/{len(nodes)}: {address}", flush=True)
        with tempfile.TemporaryDirectory(prefix="musicmeta-vpngate-") as directory:
            tunnel = Tunnel(Path(directory))
            try:
                tunnel.start(config, connect_timeout)
                if fetch(environment, fetch_timeout):
                    print("All five files fetched through VPN Gate.", flush=True)
                    return
                print("Upstream download failed; trying the next node.", flush=True)
            except (RuntimeError, subprocess.SubprocessError) as error:
                print(f"Node failed: {error}", flush=True)
                if tunnel.log.exists():
                    print("\n".join(tunnel.log.read_text(errors="replace").splitlines()[-12:]), flush=True)
            finally:
                tunnel.stop()
    raise RuntimeError(f"All {len(nodes)} VPN Gate nodes failed; data was not updated")


def interrupted(signum, frame):
    raise SystemExit(128 + signum)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    main()
