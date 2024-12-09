"""
JSON tree widget.
"""

from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem


class JSONTree(QTreeWidget):
    def __init__(self, json_data, parent=None):
        super(JSONTree, self).__init__(parent)
        self.setHeaderHidden(True)
        self.setHeaderLabels(("key", "value"))
        self.set_data(json_data)
        self.resizeColumnToContents(0)

    def set_data(self, json_data):
        self._parse_json(json_data)

    def _parse_json(self, json_el, parent=None):
        if parent is None:  # Root node
            parent = self

        if isinstance(json_el, list):  # If a list, remap it to a dict
            json_el = dict(enumerate(json_el))

        for key, val in json_el.items():
            item = QTreeWidgetItem(parent)
            item.setText(0, str(key))
            if isinstance(val, dict) or isinstance(val, list):
                self._parse_json(val, parent=item)
            else:
                item.setText(1, str(val))
