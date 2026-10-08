"""History export dialogs and notifications, independent of map/web display."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from qgis.core import QgsFeature, QgsMessageLog, QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .compat import MSGBOX_YES, MSGBOX_NO, MSG_CRITICAL, MSG_WARNING
from .history_export_service import HistoryExportService
from .history_formats import ROUTE_HISTORY_LAYER_NAME, GUIDANCE_HISTORY_LAYER_NAME

LOG_TAG = "Kakao QGIS Bridge"


@dataclass(frozen=True)
class HistoryExportCallbacks:
    """Explicit lifecycle and writer dependencies; no plugin object is retained."""

    current_epoch: Callable
    current_iface: Callable
    write_geopackage: Callable
    write_geojson: Callable
    write_shapefile: Callable
    write_gpx: Callable


class HistoryExportController:
    def __init__(self, repository, callbacks):
        self.repository = repository
        self.callbacks = callbacks

    @property
    def iface(self):
        return self.callbacks.current_iface()

    @property
    def route_history_layer(self):
        return self.repository.route_layer

    @property
    def guidance_history_layer(self):
        return self.repository.guidance_layer

    _geojson_output_paths = staticmethod(HistoryExportService._geojson_output_paths)
    _paired_output_paths = staticmethod(HistoryExportService._paired_output_paths)
    _shapefile_sidecar_paths = staticmethod(HistoryExportService._shapefile_sidecar_paths)
    _route_shapefile_fields = staticmethod(HistoryExportService._route_shapefile_fields)
    _guidance_shapefile_fields = staticmethod(HistoryExportService._guidance_shapefile_fields)

    def _export_single_route_history(self, history_id):
        route_feature = self.repository.route_for_history(history_id)
        if route_feature is None:
            return

        self._export_route_histories(
            [history_id],
            self._history_export_basename(route_feature),
            "선택 경로 이력 내보내기",
            "선택 이력 내보내기",
        )

    def _export_selected_route_histories(self, history_ids_json):
        try:
            history_ids = json.loads(history_ids_json or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            history_ids = []

        if not isinstance(history_ids, list):
            history_ids = []

        history_ids = [
            str(history_id)
            for history_id in history_ids
            if str(history_id).strip()
        ]
        if not history_ids:
            self.iface.messageBar().pushWarning(
                "Kakao QGIS Bridge",
                "내보낼 경로 이력을 선택하세요.",
            )
            return

        self._export_route_histories(
            history_ids,
            self._selected_history_export_basename(len(history_ids)),
            "선택 경로 이력 다수 내보내기",
            "선택 이력 다수 내보내기",
        )

    def _export_route_histories(
        self,
        history_ids,
        base_name,
        dialog_title,
        success_label,
    ):
        if self.route_history_layer is None:
            return

        unique_history_ids = []
        seen_history_ids = set()
        for history_id in history_ids:
            if history_id in seen_history_ids:
                continue
            seen_history_ids.add(history_id)
            unique_history_ids.append(history_id)

        route_features = []
        guidance_features = []
        for history_id in unique_history_ids:
            route_feature = self.repository.route_for_history(history_id)
            if route_feature is None:
                continue
            route_features.append(QgsFeature(route_feature))
            guidance_features.extend(
                self.repository.guidance_for_history(history_id)
            )

        if not route_features:
            self.iface.messageBar().pushWarning(
                "Kakao QGIS Bridge",
                "내보낼 수 있는 경로 이력이 없습니다.",
            )
            return

        formats = [
            "GeoPackage (*.gpkg)",
            "GeoJSON (*.geojson)",
            "Shapefile (*.shp)",
            "GPX (*.gpx)",
        ]
        epoch = self.callbacks.current_epoch()
        selected_format, accepted = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Kakao QGIS Bridge",
            "선택한 경로 이력을 내보낼 형식",
            formats,
            0,
            False,
        )
        if not accepted or epoch != self.callbacks.current_epoch():
            return

        project_home = QgsProject.instance().homePath()
        extension = {
            formats[0]: ".gpkg",
            formats[1]: ".geojson",
            formats[2]: ".shp",
            formats[3]: ".gpx",
        }[selected_format]
        default_name = f"{base_name}{extension}"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        epoch = self.callbacks.current_epoch()
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            dialog_title,
            default_path,
            selected_format,
        )
        if not filename or epoch != self.callbacks.current_epoch():
            return

        route_layer = self._single_history_layer(
            self.route_history_layer,
            route_features,
            "LineString",
            "Selected Kakao Route History",
        )
        guidance_layer = self._single_history_layer(
            self.guidance_history_layer,
            guidance_features,
            "Point",
            "Selected Kakao Guidance History",
        )

        shapefile_warning = ""
        try:
            if selected_format == formats[0]:
                output_path = Path(filename)
                if output_path.suffix.lower() != ".gpkg":
                    output_path = output_path.with_suffix(".gpkg")
                route_count = self.callbacks.write_geopackage(
                    route_layer,
                    output_path,
                    ROUTE_HISTORY_LAYER_NAME,
                    "LineString",
                )
                guidance_count = self.callbacks.write_geopackage(
                    guidance_layer,
                    output_path,
                    GUIDANCE_HISTORY_LAYER_NAME,
                    "Point",
                )
                output_parent = output_path.parent
            elif selected_format == formats[1]:
                route_path, guidance_path = self._geojson_output_paths(filename)
                route_count = self.callbacks.write_geojson(
                    route_layer,
                    route_path,
                    "Kakao Route History",
                )
                guidance_count = self.callbacks.write_geojson(
                    guidance_layer,
                    guidance_path,
                    "Kakao Guidance History",
                )
                output_parent = route_path.parent
            elif selected_format == formats[2]:
                shapefile_warning = self._shapefile_loss_warning(route_layer, guidance_layer)
                route_path, guidance_path = self._paired_output_paths(
                    filename,
                    ".shp",
                )
                route_count = self.callbacks.write_shapefile(
                    route_layer,
                    route_path,
                    "LineString",
                    "Kakao Route History",
                    self._route_shapefile_fields(),
                )
                guidance_count = self.callbacks.write_shapefile(
                    guidance_layer,
                    guidance_path,
                    "Point",
                    "Kakao Guidance History",
                    self._guidance_shapefile_fields(),
                )
                output_parent = route_path.parent
            else:
                output_path = Path(filename)
                if output_path.suffix.lower() != ".gpx":
                    output_path = output_path.with_suffix(".gpx")
                route_count, guidance_count = self.callbacks.write_gpx(
                    route_layer,
                    guidance_layer,
                    output_path,
                )
                output_parent = output_path.parent
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"{dialog_title}에 실패했습니다.\n\n{exc}",
            )
            return

        message = (f"{success_label} 완료: 경로 {route_count}건, "
                   f"안내 {guidance_count}건 ({output_parent})")
        if shapefile_warning:
            self.iface.messageBar().pushWarning("Kakao QGIS Bridge", message + " " + shapefile_warning)
        else:
            self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    @staticmethod
    def _single_history_layer(source_layer, features, geometry_name, layer_name):
        layer = QgsVectorLayer(
            f"{geometry_name}?crs={source_layer.crs().authid()}",
            layer_name,
            "memory",
        )
        provider = layer.dataProvider()
        provider.addAttributes(list(source_layer.fields()))
        layer.updateFields()
        copied_features = []
        for source_feature in features:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(source_feature.geometry())
            feature.setAttributes(source_feature.attributes())
            copied_features.append(feature)
        if copied_features:
            provider.addFeatures(copied_features)
            layer.updateExtents()
        layer.setRenderer(source_layer.renderer().clone())
        return layer

    @staticmethod
    def _history_export_basename(route_feature):
        searched = str(route_feature["searched_at"] or "")
        date_part = searched[:10].replace("-", "") or datetime.now().strftime("%Y%m%d")
        origin = str(route_feature["origin_name"] or "origin").strip()
        destination = str(route_feature["destination_name"] or "destination").strip()
        raw_name = f"kakao_route_{date_part}_{origin}_to_{destination}"
        safe = "".join(
            character if character.isalnum() or character in ("-", "_") else "_"
            for character in raw_name
        )
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe[:120].strip("_") or f"kakao_route_{date_part}"

    @staticmethod
    def _selected_history_export_basename(history_count):
        date_part = datetime.now().strftime("%Y%m%d")
        return f"kakao_routes_{date_part}_selected_{history_count}"

    def _save_route_history_geopackage(self, _checked=False):
        if (
            self.route_history_layer is None
            or self.route_history_layer.featureCount() == 0
        ):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "저장할 경로 검색 이력이 없습니다. 경로를 먼저 생성해 주세요.",
            )
            return

        project_home = QgsProject.instance().homePath()
        default_name = f"kakao_route_history_{datetime.now():%Y%m%d}.gpkg"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        epoch = self.callbacks.current_epoch()
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "경로 이력 GeoPackage 저장",
            default_path,
            "GeoPackage (*.gpkg)",
        )
        if not filename or epoch != self.callbacks.current_epoch():
            return

        output_path = Path(filename)
        if output_path.suffix.lower() != ".gpkg":
            output_path = output_path.with_suffix(".gpkg")

        try:
            route_count = self.callbacks.write_geopackage(
                self.route_history_layer,
                output_path,
                ROUTE_HISTORY_LAYER_NAME,
                "LineString",
            )
            guidance_count = self.callbacks.write_geopackage(
                self.guidance_history_layer,
                output_path,
                GUIDANCE_HISTORY_LAYER_NAME,
                "Point",
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"GeoPackage 저장에 실패했습니다.\n\n{exc}",
            )
            return

        if route_count == 0 and guidance_count == 0:
            message = "선택한 GeoPackage에 현재 세션 이력이 이미 저장되어 있습니다."
        else:
            message = (
                f"GeoPackage 저장 완료: 경로 {route_count}건, "
                f"안내 {guidance_count}건"
            )
        message = f"{message} ({output_path})"
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _export_route_history_geojson(self, _checked=False):
        if (
            self.route_history_layer is None
            or self.route_history_layer.featureCount() == 0
        ):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "내보낼 경로 검색 이력이 없습니다. 경로를 먼저 생성해 주세요.",
            )
            return

        project_home = QgsProject.instance().homePath()
        default_name = f"kakao_route_history_{datetime.now():%Y%m%d}.geojson"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        epoch = self.callbacks.current_epoch()
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "경로·안내 이력 GeoJSON 내보내기",
            default_path,
            "GeoJSON (*.geojson)",
        )
        if not filename or epoch != self.callbacks.current_epoch():
            return

        route_path, guidance_path = self._geojson_output_paths(filename)
        output_paths = [
            route_path,
            guidance_path,
            route_path.with_suffix(".qml"),
            guidance_path.with_suffix(".qml"),
        ]
        existing_paths = [path for path in output_paths if path.exists()]
        if existing_paths:
            filenames = "\n".join(path.name for path in existing_paths)
            answer = QMessageBox.question(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "다음 파일을 덮어쓸까요?\n\n" + filenames,
                MSGBOX_YES
                | MSGBOX_NO,
                MSGBOX_NO,
            )
            if answer != MSGBOX_YES or epoch != self.callbacks.current_epoch():
                return

        try:
            route_count = self.callbacks.write_geojson(
                self.route_history_layer,
                route_path,
                "Kakao Route History",
            )
            guidance_count = self.callbacks.write_geojson(
                self.guidance_history_layer,
                guidance_path,
                "Kakao Guidance History",
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"GeoJSON 내보내기에 실패했습니다.\n\n{exc}",
            )
            return

        message = (
            f"GeoJSON 내보내기 완료: 경로 {route_count}건, "
            f"안내 {guidance_count}건 ({route_path.parent})"
        )
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _export_route_history_shapefile(self, _checked=False):
        if (
            self.route_history_layer is None
            or self.route_history_layer.featureCount() == 0
        ):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "내보낼 경로 검색 이력이 없습니다. 경로를 먼저 생성해 주세요.",
            )
            return

        project_home = QgsProject.instance().homePath()
        default_name = f"kakao_route_history_{datetime.now():%Y%m%d}.shp"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        epoch = self.callbacks.current_epoch()
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "경로·안내 이력 Shapefile 내보내기",
            default_path,
            "Shapefile (*.shp)",
        )
        if not filename or epoch != self.callbacks.current_epoch():
            return

        route_path, guidance_path = self._paired_output_paths(
            filename,
            ".shp",
        )
        output_paths = self._shapefile_sidecar_paths(route_path)
        output_paths.extend(self._shapefile_sidecar_paths(guidance_path))
        existing_paths = [path for path in output_paths if path.exists()]
        if existing_paths:
            filenames = "\n".join(path.name for path in existing_paths)
            answer = QMessageBox.question(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "다음 파일을 덮어쓸까요?\n\n" + filenames,
                MSGBOX_YES
                | MSGBOX_NO,
                MSGBOX_NO,
            )
            if answer != MSGBOX_YES or epoch != self.callbacks.current_epoch():
                return

        try:
            shapefile_warning = self._shapefile_loss_warning(
                self.route_history_layer, self.guidance_history_layer,
            )
            route_count = self.callbacks.write_shapefile(
                self.route_history_layer,
                route_path,
                "LineString",
                "Kakao Route History",
                self._route_shapefile_fields(),
            )
            guidance_count = self.callbacks.write_shapefile(
                self.guidance_history_layer,
                guidance_path,
                "Point",
                "Kakao Guidance History",
                self._guidance_shapefile_fields(),
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"Shapefile 내보내기에 실패했습니다.\n\n{exc}",
            )
            return

        message = (
            f"Shapefile 내보내기 완료: 경로 {route_count}건, "
            f"안내 {guidance_count}건 ({route_path.parent})"
        )
        if shapefile_warning:
            self.iface.messageBar().pushWarning("Kakao QGIS Bridge", message + " " + shapefile_warning)
        else:
            self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _export_route_history_gpx(self, _checked=False):
        if (
            self.route_history_layer is None
            or self.route_history_layer.featureCount() == 0
        ):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "내보낼 경로 검색 이력이 없습니다. 경로를 먼저 생성해 주세요.",
            )
            return

        project_home = QgsProject.instance().homePath()
        default_name = f"kakao_route_history_{datetime.now():%Y%m%d}.gpx"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        epoch = self.callbacks.current_epoch()
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "경로·안내 이력 GPX 내보내기",
            default_path,
            "GPX (*.gpx)",
        )
        if not filename or epoch != self.callbacks.current_epoch():
            return

        output_path = Path(filename)
        if output_path.suffix.lower() != ".gpx":
            output_path = output_path.with_suffix(".gpx")
        if output_path.exists():
            answer = QMessageBox.question(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"{output_path.name} 파일을 덮어쓸까요?",
                MSGBOX_YES
                | MSGBOX_NO,
                MSGBOX_NO,
            )
            if answer != MSGBOX_YES or epoch != self.callbacks.current_epoch():
                return

        try:
            route_count, guidance_count = self.callbacks.write_gpx(
                self.route_history_layer,
                self.guidance_history_layer,
                output_path,
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"GPX 내보내기에 실패했습니다.\n\n{exc}",
            )
            return

        message = (
            f"GPX 내보내기 완료: 경로 {route_count}건, "
            f"안내 {guidance_count}건 ({output_path.parent})"
        )
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _shapefile_loss_warning(self, routes, guides):
        affected = []
        for label, layer, specs in (
            ("경로", routes, self._route_shapefile_fields()),
            ("안내", guides, self._guidance_shapefile_fields()),
        ):
            if layer is None:
                continue
            counts = HistoryExportService.shapefile_loss_counts(layer, specs)
            affected.extend(f"{label} {field} {count}건" for field, count in counts.items())
        if not affected:
            return ""
        message = ("SHP 문자열 제한으로 일부 속성이 잘립니다. "
                   "경유지 등 전체 속성을 보존하려면 GeoPackage 또는 GeoJSON을 사용하세요.")
        QgsMessageLog.logMessage(message + "\n" + ", ".join(affected), LOG_TAG, MSG_WARNING)
        return message
