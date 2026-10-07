"""Probe restart binding on an OS-assigned port, without using 8081/8082."""
import json
import runpy
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
module = runpy.run_path(str(root / "tests" / "test_external_bridge.py"))
Server = module["KakaoExternalBridgeServer"]
result = []
for trial in range(3):
    server = Server(port=0)
    url = server.start()
    port = urlsplit(url).port
    for _ in range(20):
        with urlopen(Request(url), timeout=3) as response:
            response.read()
    server.stop()
    replacement = Server(port=port)
    try:
        replacement.start()
        result.append({"trial": trial, "port": port, "restart": "ok"})
    except OSError as exc:
        result.append({"trial": trial, "port": port, "restart": "failed",
                       "winerror": exc.winerror, "error": str(exc)})
    finally:
        replacement.stop()
print(json.dumps(result))
