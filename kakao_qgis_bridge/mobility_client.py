"""Qt network adapter for the pure Mobility domain module."""

import json

from qgis.PyQt.QtCore import QObject, QTimer, QUrl, QUrlQuery, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .mobility import (
    MobilityResponseError,
    ROUTE_ENDPOINT,
    parse_route_payload,
    route_query_items,
)


ROUTE_REQUEST_TIMEOUT_MS = 30_000


class MobilityClient(QObject):
    succeeded = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = None

    def request_route(self, rest_key, route_request):
        self.cancel()
        url = QUrl(ROUTE_ENDPOINT)
        query = QUrlQuery()
        for key, value in route_query_items(route_request):
            query.addQueryItem(key, value)
        url.setQuery(query)
        request = QNetworkRequest(url)
        request.setRawHeader(b"Authorization", f"KakaoAK {rest_key}".encode("ascii"))
        request.setRawHeader(b"Content-Type", b"application/json")

        reply = self._manager.get(request)
        self._reply = reply
        timer = QTimer(reply)
        timer.setSingleShot(True)
        timer.setInterval(ROUTE_REQUEST_TIMEOUT_MS)

        def abort_timed_out_reply():
            if reply is self._reply and reply.isRunning():
                reply.setProperty("kakaoRouteTimedOut", True)
                reply.abort()

        timer.timeout.connect(abort_timed_out_reply)
        timer.start()
        reply.finished.connect(
            lambda current=reply: self._handle_reply(current, route_request)
        )

    def cancel(self):
        if self._reply is None:
            return
        reply = self._reply
        self._reply = None
        try:
            reply.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        reply.abort()
        reply.deleteLater()

    def _handle_reply(self, reply, route_request):
        if reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None
        status_code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        timed_out = bool(reply.property("kakaoRouteTimedOut"))
        raw_data = bytes(reply.readAll())
        network_error = reply.error()
        network_error_message = reply.errorString()
        reply.deleteLater()
        try:
            payload = json.loads(raw_data.decode("utf-8")) if raw_data else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}

        if network_error != QNetworkReply.NetworkError.NoError or status_code != 200:
            if timed_out:
                self.failed.emit(
                    "경로 탐색 요청 시간이 초과되었습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요."
                )
                return
            message = (
                payload.get("msg")
                or payload.get("message")
                or network_error_message
                or f"HTTP {status_code}"
            )
            self.failed.emit(f"경로 탐색 실패: {message}")
            return
        try:
            result = parse_route_payload(payload)
        except MobilityResponseError as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result, route_request)
