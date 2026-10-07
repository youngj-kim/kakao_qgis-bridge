"""Checked changes and compensating recovery for a pair of history layers."""
from collections import Counter

from qgis.core import Qgis, QgsFeature, QgsVariantUtils, QgsVectorDataProvider


class HistoryOperationError(RuntimeError):
    def __init__(self, operation, detail, recovered=True):
        self.operation = operation
        self.recovered = recovered
        state = "기존 이력은 유지되었습니다." if recovered else (
            "일부 변경이 남아 복구가 필요합니다. 현재 이력을 내보내 보관하고 "
            "새 세션에서 저장된 이력을 다시 불러오세요."
        )
        super().__init__(f"{operation} 실패: {detail}\n{state}")


class HistoryOperations:
    def __init__(self):
        self.needs_recovery = False

    @staticmethod
    def _successful(result):
        return bool(result[0]) if isinstance(result, tuple) else bool(result)

    @staticmethod
    def _provider_add(layer, features):
        return layer.dataProvider().addFeatures(features)

    @staticmethod
    def _provider_delete(layer, ids):
        return layer.dataProvider().deleteFeatures(ids)

    @staticmethod
    def _features(layer):
        return {feature.id(): QgsFeature(feature) for feature in layer.getFeatures()}

    @staticmethod
    def _key(feature):
        # Exact built-in types need no Qt NULL conversion; other types retain
        # the provider's NULL semantics, including QVariant and date values.
        attributes = tuple(None if value is None else str(value)
                           if type(value) in (str, int, float, bool)
                           else None if QgsVariantUtils.isNull(value) else str(value)
                           for value in feature.attributes())
        return (bytes(feature.geometry().asWkb()), attributes)

    @classmethod
    def _contents(cls, features):
        return Counter(cls._key(feature) for feature in features.values())

    @staticmethod
    def _preflight(layer):
        if not layer.isValid() or layer.dataProvider() is None:
            raise RuntimeError("이력 레이어를 사용할 수 없습니다.")
        if layer.isEditable():
            raise RuntimeError("이력 레이어의 편집을 종료한 뒤 다시 시도하세요.")
        scope = getattr(Qgis, "VectorProviderCapability", QgsVectorDataProvider)
        required = scope.AddFeatures | scope.DeleteFeatures
        if (layer.dataProvider().capabilities() & required) != required:
            raise RuntimeError("이력 레이어에 추가·삭제 및 복구 권한이 없습니다.")

    def apply(self, operation, changes):
        """Apply (layer, additions, deletion IDs) as one recoverable operation.

        Success returns actual additions/deletions. Failure raises with recovery
        status. This is compensation, not a cross-provider database transaction.
        """
        if self.needs_recovery:
            raise HistoryOperationError(operation, "이전 작업의 복구가 완료되지 않아 변경을 차단했습니다.", False)
        changes = [(layer, list(additions), set(ids)) for layer, additions, ids in changes
                   if additions or ids]
        snapshots = []
        try:
            # Check both layers before touching either, including undo capability.
            for layer, additions, ids in changes:
                self._preflight(layer)
                before = self._features(layer)
                if not ids <= before.keys():
                    raise RuntimeError("삭제 대상 이력이 변경되었습니다. 다시 선택하세요.")
                snapshots.append((layer, before, set(layer.selectedFeatureIds())))
        except Exception as exc:
            raise HistoryOperationError(operation, str(exc)) from exc

        added_total = deleted_total = 0
        try:
            for (layer, additions, ids), (_layer, before, _selected) in zip(changes, snapshots):
                if ids and not self._successful(self._provider_delete(layer, list(ids))):
                    raise RuntimeError(f"{layer.name()} 삭제를 반영하지 못했습니다.")
                if additions and not self._successful(self._provider_add(layer, additions)):
                    raise RuntimeError(f"{layer.name()} 추가를 반영하지 못했습니다.")
                after = self._features(layer)
                new_ids = after.keys() - before.keys()
                if ids & after.keys() or len(new_ids) != len(additions):
                    raise RuntimeError(f"{layer.name()} 실제 반영 건수가 요청과 다릅니다.")
                for fid in before.keys() - ids:
                    if fid not in after or self._key(before[fid]) != self._key(after[fid]):
                        raise RuntimeError(f"{layer.name()}의 기존 이력이 변경되었습니다.")
                added_total += len(new_ids)
                deleted_total += len(ids)
                layer.updateExtents()
            return added_total, deleted_total
        except Exception as exc:
            recovered = self._recover(snapshots)
            self.needs_recovery = not recovered
            raise HistoryOperationError(operation, str(exc), recovered) from exc

    def _recover(self, snapshots):
        recovered = True
        # Continue restoring the other layer even if one provider refuses undo.
        for layer, before, selected in reversed(snapshots):
            try:
                current = self._features(layer)
                extra_ids = set(current) - set(before)
                changed_ids = {fid for fid in current.keys() & before.keys()
                               if self._key(current[fid]) != self._key(before[fid])}
                if extra_ids or changed_ids:
                    self._provider_delete(layer, list(extra_ids | changed_ids))
                current = self._features(layer)
                missing = [QgsFeature(feature) for fid, feature in before.items() if fid not in current]
                if missing:
                    self._provider_add(layer, missing)
                current = self._features(layer)
                if self._contents(current) != self._contents(before):
                    recovered = False
                # Re-added features may receive new IDs. Restore selection by data.
                wanted = Counter(self._key(before[fid]) for fid in selected if fid in before)
                selected_ids = []
                for fid, feature in sorted(current.items(), key=lambda item: item[0] not in selected):
                    key = self._key(feature)
                    if wanted[key] > 0:
                        selected_ids.append(fid)
                        wanted[key] -= 1
                layer.selectByIds(selected_ids)
                layer.updateExtents()
            except Exception:
                recovered = False
        return recovered
