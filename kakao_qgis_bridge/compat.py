from qgis.core import Qgis, QgsMapLayer, QgsVectorFileWriter
from qgis.PyQt.QtWidgets import QMessageBox


def _enum_value(scope, name, fallback_scope=None, fallback_name=None):
    if hasattr(scope, name):
        return getattr(scope, name)
    if fallback_scope is not None:
        return getattr(fallback_scope, fallback_name or name)
    raise AttributeError(name)


_message_level = getattr(Qgis, "MessageLevel", Qgis)
MSG_WARNING = _enum_value(_message_level, "Warning", Qgis, "Warning")
MSG_CRITICAL = _enum_value(_message_level, "Critical", Qgis, "Critical")

_message_button = getattr(QMessageBox, "StandardButton", QMessageBox)
MSGBOX_YES = _enum_value(_message_button, "Yes", QMessageBox, "Yes")
MSGBOX_NO = _enum_value(_message_button, "No", QMessageBox, "No")

_writer_action = getattr(
    QgsVectorFileWriter,
    "ActionOnExistingFile",
    QgsVectorFileWriter,
)
WRITE_APPEND_ADD_FIELDS = _enum_value(
    _writer_action,
    "AppendToLayerAddFields",
    QgsVectorFileWriter,
    "AppendToLayerAddFields",
)
WRITE_APPEND_NO_FIELDS = _enum_value(
    _writer_action,
    "AppendToLayerNoNewFields",
    QgsVectorFileWriter,
    "AppendToLayerNoNewFields",
)
WRITE_OVERWRITE_FILE = _enum_value(
    _writer_action,
    "CreateOrOverwriteFile",
    QgsVectorFileWriter,
    "CreateOrOverwriteFile",
)
WRITE_OVERWRITE_LAYER = _enum_value(
    _writer_action,
    "CreateOrOverwriteLayer",
    QgsVectorFileWriter,
    "CreateOrOverwriteLayer",
)


def save_style_to_database(layer, name, description, use_as_default):
    if hasattr(layer, "saveStyleToDatabaseV2"):
        result, error_message = layer.saveStyleToDatabaseV2(
            name,
            description,
            use_as_default,
            "",
        )
        success_value = _enum_value(
            getattr(QgsMapLayer, "SaveStyleResult", QgsMapLayer),
            "Success",
            QgsMapLayer,
            "Success",
        )
        return result == success_value, error_message or str(result)

    result = layer.saveStyleToDatabase(name, description, use_as_default, "")
    if isinstance(result, tuple):
        bool_values = [value for value in result if isinstance(value, bool)]
        error_values = [value for value in result if isinstance(value, str)]
        if bool_values:
            return bool_values[-1], (error_values[0] if error_values else "")
    return True, ""
