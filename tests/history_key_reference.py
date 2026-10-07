"""Original fingerprint semantics for differential regression checks."""
from qgis.core import QgsVariantUtils


def reference_key(feature):
    values = tuple(None if QgsVariantUtils.isNull(value) else str(value)
                   for value in feature.attributes())
    return bytes(feature.geometry().asWkb()), values
