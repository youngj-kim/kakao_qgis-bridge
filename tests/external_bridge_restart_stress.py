"""Windows restart observations on temporary ports, including idle connections."""
import http.client
import json
import runpy
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
Server = runpy.run_path(str(root / "tests/test_external_bridge.py"))["KakaoExternalBridgeServer"]

def request(url, path="/api/state", token=None):
    parsed = urlsplit(url)
    headers = {"X-Kakao-Bridge-Token": token or parse_qs(parsed.query)["token"][0]}
    connection = http.client.HTTPConnection("127.0.0.1", parsed.port, timeout=2)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        return response.status, body
    finally:
        connection.close()

result = {"idle_connections": [], "restart_cycles": []}
for partial in (False, True):
    server = Server(port=0)
    url = server.start()
    port = urlsplit(url).port
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    replacement = Server(port=port)
    try:
        if partial:
            token = parse_qs(urlsplit(url).query)["token"][0]
            client.sendall((f"POST /api/move-center HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n"
                            f"X-Kakao-Bridge-Token: {token}\r\nContent-Type: application/json\r\n"
                            "Content-Length: 32\r\n\r\n{").encode("ascii"))
        time.sleep(0.2)  # Allow the accepted request thread to begin reading.
        started = time.perf_counter()
        server.stop()
        record = {"case": "partial POST" if partial else "idle accepted connection",
                  "stop_seconds": round(time.perf_counter() - started, 3)}
        try:
            replacement.start()
            record["rebind_while_client_open"] = "ok"
        except OSError as exc:
            record.update(rebind_while_client_open="failed", winerror=exc.winerror)
        finally:
            replacement.stop()
        # Complete a pending body before closing, avoiding a test-induced broken response.
        if partial:
            client.sendall(b"}" + b" " * 30)
            client.settimeout(2)
            while client.recv(8192):
                pass
        client.close()
        time.sleep(0.1)
        try:
            replacement.start()
            record["rebind_after_client_close"] = "ok"
        except OSError as exc:
            record.update(rebind_after_client_close="failed", after_close_winerror=exc.winerror)
        finally:
            replacement.stop()
        result["idle_connections"].append(record)
        print("IDLE_RESULT=" + json.dumps(record), flush=True)
    finally:
        client.close()
        server.stop()
        replacement.stop()

server = Server(port=0)
current_url = server.start()
lock = threading.Lock()
stop = threading.Event()
stats = {"ok": 0, "http_errors": 0, "transport_errors": 0}

def poll(index):
    while not stop.is_set():
        with lock:
            url = current_url
        try:
            status, body = request(url, "/api/state" if index % 2 else "/api/events?since=0")
            if status == 200:
                json.loads(body)
            with lock:
                stats["ok" if status == 200 else "http_errors"] += 1
        except (OSError, http.client.HTTPException):
            with lock:
                stats["transport_errors"] += 1
        stop.wait(0.4)

workers = [threading.Thread(target=poll, args=(index,), daemon=True) for index in range(4)]
for worker in workers:
    worker.start()
try:
    deadline = time.monotonic() + 60
    sequence = 0
    while time.monotonic() < deadline:
        server.set_center(127 + sequence * 1e-6, 37)
        sequence += 1
        stop.wait(0.04)
    with lock:
        result["soak"] = dict(stats, seconds=60, clients=4)
    assert result["soak"]["ok"] > 500, "polling did not run as expected"
    assert result["soak"]["http_errors"] == 0 and result["soak"]["transport_errors"] == 0
    print("SOAK_RESULT=" + json.dumps(result["soak"]), flush=True)

    # Leave clients polling while replacing the server and session token.
    for cycle in range(12):
        preferred = urlsplit(current_url).port
        old_token = parse_qs(urlsplit(current_url).query)["token"][0]
        server.stop()
        server = Server(port=preferred, fallback_ports=(0,))
        new_url = server.start()
        actual = urlsplit(new_url).port
        assert request(new_url, token=old_token)[0] == 403
        assert request(new_url)[0] == 200
        with lock:
            current_url = new_url
        record = {"cycle": cycle, "same_port": actual == preferred,
                  "old_token": 403, "new_session": 200}
        result["restart_cycles"].append(record)
        stop.wait(0.1)
    result["post_restart"] = dict(stats)
finally:
    stop.set()
    for worker in workers:
        worker.join(timeout=3)
    server.stop()
print("RESTART_STRESS_RESULT=" + json.dumps(result), flush=True)
