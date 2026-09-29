"""Create the real Dock widget briefly in a GUI-enabled QGIS runtime."""

import json
import sys
import traceback
from pathlib import Path


def run(repo_root):
    sys.path.insert(0, str(Path(repo_root).resolve()))

    # Qt WebEngine requires this import before QApplication is constructed.
    try:
        from qgis.PyQt.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except ImportError:
        pass

    from qgis.core import QgsApplication, Qgis
    from qgis.PyQt.QtCore import QTimer

    from kakao_qgis_bridge.dock_widget import (
        WEB_RUNTIME_IMPORT_ERRORS,
        KakaoMapDockWidget,
    )

    app = QgsApplication([], True)
    app.initQgis()
    dock = KakaoMapDockWidget()
    dock.resize(900, 700)
    dock.show()

    result = {}

    def finish():
        result.update(
            {
                "qgis_version": Qgis.QGIS_VERSION,
                "dock_visible": dock.isVisible(),
                "runtime_mode": (
                    "webengine" if dock.web_view is not None else "external-browser"
                ),
                "web_runtime_import_errors": WEB_RUNTIME_IMPORT_ERRORS,
            }
        )
        print(
            "WIDGET_SMOKE_RESULT="
            + json.dumps(result, ensure_ascii=False, sort_keys=True),
            flush=True,
        )
        dock.close()
        dock.deleteLater()
        app.quit()

    QTimer.singleShot(2_500, finish)
    execute = getattr(app, "exec", None) or app.exec_
    exit_code = execute()
    app.exitQgis()
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(run(sys.argv[1]))
    except Exception:
        traceback.print_exc()
        raise
