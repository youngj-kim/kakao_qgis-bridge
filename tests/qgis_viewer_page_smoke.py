"""Verify both production HTML assembly paths without a key or SDK network."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import Qgis, QgsApplication
from kakao_qgis_bridge.dock_widget import KakaoMapDockWidget
from kakao_qgis_bridge.external_bridge import KakaoExternalBridgeServer
from kakao_qgis_bridge.viewer_page import VIEWER_SCRIPTS

app = QgsApplication([], False)
app.initQgis()
dock = None
try:
    # Deliberately disable the real WebEngine: never load an SDK or user key.
    with patch("kakao_qgis_bridge.dock_widget.QWebEngineView", None):
        dock = KakaoMapDockWidget()
    dock.web_view = Mock()
    with patch("kakao_qgis_bridge.dock_widget.kakao_javascript_key", return_value="fixture-key"):
        dock._load_viewer()
    dock_html, base_url = dock.web_view.setHtml.call_args.args
    server = KakaoExternalBridgeServer(port=0)
    with patch("kakao_qgis_bridge.external_bridge.kakao_javascript_key", return_value="fixture-key"):
        external_html = server._viewer_html()
    for html in (dock_html, external_html):
        assert "fixture-key" in html
        assert all(marker not in html for marker in VIEWER_SCRIPTS)
        for name in ("Search", "Guidance", "History", "RouteInput"):
            assert html.count("window.createKakao" + name + "Controller =") == 1
            assert html.index("window.createKakao" + name + "Controller =") < html.index("const kakaoAppKey")
    assert "qrc:///qtwebchannel/qwebchannel.js" in dock_html
    assert "qrc:///qtwebchannel/qwebchannel.js" not in external_html
    assert server._token in external_html
    assert base_url.isValid()
    print("VIEWER_PAGE_RESULT=" + json.dumps({
        "qgis": Qgis.QGIS_VERSION, "status": "ok",
        "checks": ["dock and external module assembly/order", "key/token and WebChannel transport"],
        "real_webengine_or_sdk": False
    }))
finally:
    if dock is not None:
        dock.close()
    app.exitQgis()
