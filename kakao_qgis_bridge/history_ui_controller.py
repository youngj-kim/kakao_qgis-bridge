"""History selection, input restoration and deletion UI orchestration."""

from dataclasses import dataclass
from typing import Callable

from qgis.PyQt.QtWidgets import QMessageBox

from .compat import MSGBOX_NO, MSGBOX_YES
from .history_operations import HistoryOperationError
from .history_values import safe_number


@dataclass(frozen=True)
class HistoryUiCallbacks:
    current_epoch: Callable
    active_history: Callable
    show_history: Callable
    load_input: Callable
    clear_display: Callable
    publish_history: Callable
    update_actions: Callable
    handle_error: Callable


class HistoryUiController:
    """Queries history directly; delegates display and transport via callbacks."""

    def __init__(self, iface, repository, callbacks):
        self.iface = iface
        self.repository = repository
        self.callbacks = callbacks

    def payload(self, selected_history_id=None):
        if self.repository.route_layer is None:
            return {
                "selected_history_id": selected_history_id or "",
                "items": [],
            }

        history_index = self.repository.route_layer.fields().indexOf("history_id")
        items = []
        for feature in self.repository.route_layer.getFeatures():
            history_id = str(feature[history_index] or "")
            if not history_id:
                continue
            items.append(
                {
                    "history_id": history_id,
                    "searched_at": str(feature["searched_at"] or ""),
                    "origin_name": str(feature["origin_name"] or "출발지"),
                    "destination_name": str(
                        feature["destination_name"] or "도착지"
                    ),
                    "distance_m": safe_number(feature["distance_m"]),
                    "duration_s": safe_number(feature["duration_s"]),
                    "guidance_count": safe_number(
                        feature["guidance_count"]
                    ),
                    "result_summary": str(feature["result_summary"] or ""),
                    "priority": str(feature["priority"] or ""),
                    "avoid": str(feature["avoid"] or ""),
                    "car_type": safe_number(feature["car_type"]),
                    "car_fuel": str(feature["car_fuel"] or ""),
                    "car_hipass": bool(safe_number(feature["car_hipass"])),
                }
            )

        items.sort(key=lambda item: item["searched_at"], reverse=True)
        return {
            "selected_history_id": selected_history_id or "",
            "items": items,
        }

    def focus(self, history_id):
        if not history_id or self.repository.route_layer is None:
            return

        route_feature = self.repository.route_for_history(history_id)
        if route_feature is None:
            return

        self.repository.route_layer.removeSelection()
        self.repository.route_layer.selectByIds([route_feature.id()])

        guide_features = self.repository.guidance_for_history(history_id)
        if self.repository.guidance_layer is not None:
            self.repository.guidance_layer.removeSelection()
            self.repository.guidance_layer.selectByIds(
                [feature.id() for feature in guide_features]
            )

        self.callbacks.show_history(route_feature, guide_features, history_id)
        self.iface.messageBar().pushInfo(
            "Kakao QGIS Bridge",
            f"경로 이력 선택: {route_feature['result_summary']}",
        )

    def load_input(self, history_id):
        route_feature = self.repository.route_for_history(history_id)
        if route_feature is None:
            return
        self.callbacks.load_input(route_feature)
        self.iface.messageBar().pushInfo(
            "Kakao QGIS Bridge",
            "선택한 이력을 경로 입력창으로 불러왔습니다.",
        )

    def delete(self, history_id):
        epoch = self.callbacks.current_epoch()
        route_feature = self.repository.route_for_history(history_id)
        if route_feature is None:
            return

        answer = QMessageBox.question(
            self.iface.mainWindow(),
            "Kakao QGIS Bridge",
            (
                "선택한 경로 이력을 삭제할까요?\n\n"
                f"{route_feature['origin_name']} → "
                f"{route_feature['destination_name']}"
            ),
            MSGBOX_YES | MSGBOX_NO,
            MSGBOX_NO,
        )
        if answer != MSGBOX_YES or epoch != self.callbacks.current_epoch():
            return

        was_active_history = history_id == self.callbacks.active_history()

        try:
            self.repository.delete_history(history_id)
        except HistoryOperationError as exc:
            self.callbacks.handle_error(exc)
            return

        if was_active_history:
            self.callbacks.clear_display()

        self.callbacks.publish_history()
        self.callbacks.update_actions()
        self.iface.messageBar().pushInfo(
            "Kakao QGIS Bridge",
            "선택한 경로 이력을 삭제했습니다.",
        )

    def delete_all(self):
        epoch = self.callbacks.current_epoch()
        if (
            self.repository.route_layer is None
            or self.repository.route_layer.featureCount() == 0
        ):
            return

        answer = QMessageBox.question(
            self.iface.mainWindow(),
            "Kakao QGIS Bridge",
            "현재 세션의 모든 경로 이력을 삭제할까요?",
            MSGBOX_YES | MSGBOX_NO,
            MSGBOX_NO,
        )
        if answer != MSGBOX_YES or epoch != self.callbacks.current_epoch():
            return

        try:
            self.repository.delete_all()
        except HistoryOperationError as exc:
            self.callbacks.handle_error(exc)
            return

        self.callbacks.clear_display()
        self.callbacks.publish_history()
        self.callbacks.update_actions()
        self.iface.messageBar().pushInfo(
            "Kakao QGIS Bridge",
            "전체 경로 이력을 삭제했습니다.",
        )
