"""QGIS --code script for verifying the Dock inside the full desktop app."""

import json
import os
import traceback
from pathlib import Path

from qgis.core import Qgis
from qgis.PyQt.QtCore import QTimer, Qt
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface


output_path = Path(os.environ["KAKAO_SMOKE_OUTPUT"])
dock = None


def write_result(payload):
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def finish():
    global dock
    try:
        payload = {
            "qgis_version": Qgis.QGIS_VERSION,
            "dock_visible": dock is not None and dock.isVisible(),
            "runtime_mode": (
                "webengine"
                if dock is not None and dock.web_view is not None
                else "external-browser"
            ),
            "viewer_url": (
                dock.web_view.page().url().toString()
                if dock is not None and dock.web_view is not None
                else ""
            ),
            "status": "ok",
        }
        write_result(payload)
    except Exception:
        write_result({"status": "error", "traceback": traceback.format_exc()})
    finally:
        if dock is not None:
            dock.close()
            iface.removeDockWidget(dock)
            dock.deleteLater()
        QApplication.instance().quit()


try:
    from kakao_qgis_bridge.dock_widget import KakaoMapDockWidget

    dock = KakaoMapDockWidget(iface.mainWindow())
    iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    dock.show()
    dock.raise_()
    QTimer.singleShot(4_000, finish)
except Exception:
    write_result({"status": "error", "traceback": traceback.format_exc()})
    QTimer.singleShot(0, QApplication.instance().quit)
