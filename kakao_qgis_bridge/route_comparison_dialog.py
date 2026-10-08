"""Native comparison UI, also available without an embedded browser."""
from qgis.core import QgsCoordinateTransform, QgsProject, QgsRectangle
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QFileDialog, QGroupBox,
                                QHBoxLayout, QLabel, QMessageBox, QPushButton,
                                QTableWidget, QTableWidgetItem, QVBoxLayout)

from .route_comparison import condition_message, display_layer, read_routes


class RouteComparisonDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("GPKG 경로 비교 · 카카오 / 네이버")
        self.resize(800, 680)
        self.rows = [[], []]
        self.layer_ids = []
        self.choices = []
        self.file_labels = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("두 GPKG 파일을 열고 비교할 경로를 선택하세요. A: 파랑 실선 / B: 주황 점선"))
        for index, letter in enumerate(("A", "B")):
            box = QGroupBox(f"경로 {letter}")
            inner = QVBoxLayout(box)
            button = QPushButton("GPKG 열기…")
            button.clicked.connect(lambda checked=False, i=index: self.open_file(i))
            inner.addWidget(button)
            label = QLabel("파일을 선택하세요")
            label.setWordWrap(True)
            inner.addWidget(label)
            self.file_labels.append(label)
            choice = QComboBox()
            choice.currentIndexChanged.connect(self.refresh)
            inner.addWidget(choice)
            self.choices.append(choice)
            layout.addWidget(box)
        self.table = QTableWidget(6, 3)
        self.table.setMinimumHeight(240)
        self.table.setHorizontalHeaderLabels(["항목", "A", "B"])
        from qgis.PyQt.QtWidgets import QAbstractItemView, QHeaderView
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.conditions = QLabel("")
        self.conditions.setWordWrap(True)
        layout.addWidget(self.conditions)
        buttons = QHBoxLayout()
        self.show_button = QPushButton("두 경로 지도에 표시")
        self.show_button.clicked.connect(self.show_routes)
        buttons.addWidget(self.show_button)
        clear = QPushButton("비교 표시 지우기")
        clear.clicked.connect(self.clear_layers)
        buttons.addWidget(clear)
        layout.addLayout(buttons)
        self.refresh()
        QgsProject.instance().aboutToBeCleared.connect(self.project_reset)

    def open_file(self, index):
        filename, _ = QFileDialog.getOpenFileName(self, "비교할 경로 GPKG", "", "GeoPackage (*.gpkg)")
        if not filename:
            return
        try:
            rows = read_routes(filename)
        except Exception as exc:
            QMessageBox.warning(self, "경로 비교", str(exc))
            return
        self.clear_layers()
        self.rows[index] = rows
        choice = self.choices[index]
        choice.blockSignals(True)
        choice.clear()
        for row in rows:
            v = row["values"]
            choice.addItem(f"{row['provider']} · {v.get('origin_name') or '출발'} → "
                           f"{v.get('destination_name') or '도착'} · {v.get('searched_at') or '시점 미상'} · "
                           f"{v.get('history_id') or row['feature_id']}")
        choice.blockSignals(False)
        self.file_labels[index].setText(filename)
        self.refresh()

    def selected(self):
        return [rows[choice.currentIndex()] if rows and choice.currentIndex() >= 0 else None
                for rows, choice in zip(self.rows, self.choices)]

    def refresh(self, *_):
        self.clear_layers()
        selected = self.selected()
        specs = [("출처", None), ("조회 시점", "searched_at"),
                 ("출발", "origin_name"), ("도착", "destination_name"),
                 ("거리", "distance_m"), ("소요 시간", "duration_s")]
        for i, (label, field) in enumerate(specs):
            self.table.setItem(i, 0, QTableWidgetItem(label))
            for j, row in enumerate(selected, 1):
                value = (row["provider"] if field is None else row["values"].get(field)) if row else None
                text = str(value) if value is not None and value != "" else "정보 없음"
                if value is not None and field == "distance_m":
                    text = f"{value / 1000:.3f} km"
                if value is not None and field == "duration_s":
                    text = f"{value / 60:.1f}분"
                self.table.setItem(i, j, QTableWidgetItem(text))
        ready = all(row is not None for row in selected)
        self.show_button.setEnabled(ready)
        text = ""
        if ready:
            a, b = selected
            text = condition_message(a, b)
            for field, name, divisor, unit in (("distance_m", "거리", 1, "m"),
                                               ("duration_s", "시간", 60, "분")):
                av, bv = a["values"].get(field), b["values"].get(field)
                if av is not None and bv is not None:
                    text += f"\n{name} 차이 (B − A): {(bv - av) / divisor:+.1f}{unit}"
        self.conditions.setText(text)
        self.table.resizeRowsToContents()

    def clear_layers(self):
        project = QgsProject.instance()
        for layer_id in self.layer_ids:
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        self.layer_ids = []

    def project_reset(self):
        # Project clearing owns removal; never remove layers from its signal handler.
        self.layer_ids = []

    def show_routes(self):
        rows = self.selected()
        if any(row is None for row in rows):
            return
        self.clear_layers()
        try:
            layers = [display_layer(row, f"{letter} · {row['provider']} 비교 경로", color)
                      for row, letter, color in zip(rows, ("A", "B"), ("35,110,230", "240,120,25"))]
            project = QgsProject.instance()
            canvas = self.iface.mapCanvas()
            extent = QgsRectangle()
            for layer in layers:
                transform = QgsCoordinateTransform(layer.crs(), canvas.mapSettings().destinationCrs(), project)
                bounds = transform.transformBoundingBox(layer.extent())
                extent.combineExtentWith(bounds)
            for layer in layers:
                project.addMapLayer(layer)
                self.layer_ids.append(layer.id())
            extent.scale(1.15)
            canvas.setExtent(extent)
            canvas.refresh()
        except Exception as exc:
            self.clear_layers()
            QMessageBox.warning(self, "경로 비교", str(exc))

    def dispose(self):
        QgsProject.instance().aboutToBeCleared.disconnect(self.project_reset)
        self.clear_layers()
        self.close()
        self.deleteLater()
