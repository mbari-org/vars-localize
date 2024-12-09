"""
Alternative view to entry list.
"""

import webbrowser
from datetime import datetime, timedelta
from http.client import HTTPException
from typing import Iterable, List

from PyQt6 import QtCore
from PyQt6.QtGui import QFont, QColor, QKeyEvent, QAction
from PyQt6.QtWidgets import (
    QProgressDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QAbstractItemView,
    QDialog,
    QMessageBox,
    QMenu,
    QApplication,
    QVBoxLayout,
    QLabel,
    QDialogButtonBox,
)
from qdarkstyle.dark.palette import DarkPalette

from vars_localize.util.m3 import (
    get_imaged_moment,
    delete_observation,
    get_video_by_video_reference_uuid,
    get_all_concepts,
    rename_observation,
)
from vars_localize.util.utils import extract_bounding_boxes, log
from vars_localize.ui.ConceptSearchbar import ConceptSearchbar


class EntryTreeItem(QTreeWidgetItem):
    __slots__ = ["metadata"]

    def __init__(self, parent):
        super(EntryTreeItem, self).__init__(parent)

    def set_background(self, header: str, background: QColor):
        """
        Set the background color of one or all columns
        :param header: Title of the column, or 'all' for all
        :param background: Background QColor
        :return: None
        """
        if header == "all":
            for col in range(self.columnCount()):
                self.setBackground(col, background)
        if header in self.treeWidget().header_map.keys():
            col = self.treeWidget().header_map[header]
            self.setBackground(col, background)

    def update(self):
        """
        Update the text fields within the entry based metadata
        :return: None
        """
        for header, datum in self.metadata.items():
            if header in self.treeWidget().header_map.keys():
                col = self.treeWidget().header_map[header]
                self.setText(col, str(datum))


class EntryTree(QTreeWidget):
    def __init__(
        self, headers: Iterable[str], association_text_widget: QLabel, parent=None
    ):
        super(EntryTree, self).__init__(parent)

        self.setFont(QFont("Courier"))

        self.setHeaderLabels(headers)
        self.header_map = dict(
            [tup[::-1] for tup in enumerate(headers)]
        )  # header -> column lookup

        self.association_text_widget = association_text_widget

        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menu)

    def add_item(self, data, parent=None):
        """
        Create an entry tree item from dictionary of data, add to tree, and return item
        :param data: dict of data attributes
        :param parent: Parent object
        :return: Entry tree item
        """
        item = EntryTreeItem(parent if parent else self)
        item.metadata = data

        if data:
            item.update()
        else:
            item.setText(0, "No results found.")

        return item

    def menu(self, point):
        item = self.itemAt(point)
        if item is None:
            return

        menu = QMenu("Context menu", self)
        copy_action = QAction("Copy UUID")

        def do_copy():
            clipboard = QApplication.clipboard()
            clipboard.setText(item.metadata["uuid"])

        copy_action.triggered.connect(do_copy)
        menu.addAction(copy_action)

        menu.exec(self.viewport().mapToGlobal(point))


def update_imaged_moment_entry(entry: EntryTreeItem):
    localized = 0
    for obs_item in [entry.child(idx) for idx in range(entry.childCount())]:
        if obs_item.metadata["boxes"]:  # This observation has been localized
            localized += 1
        obs_item.metadata["status"] = len(obs_item.metadata["boxes"])
        if not obs_item.metadata["status"]:
            obs_item.set_background("status", QColor(DarkPalette.COLOR_BACKGROUND_6))
        else:
            obs_item.set_background("status", QColor(DarkPalette.COLOR_BACKGROUND_1))
        obs_item.update()

    percent_localized = localized / len(entry.metadata["observations"])
    if percent_localized < 0.25:
        entry.set_background("status", QColor(DarkPalette.COLOR_ACCENT_3))
    elif percent_localized < 1:
        entry.set_background("status", QColor(DarkPalette.COLOR_ACCENT_2))
    else:
        entry.set_background("status", QColor(DarkPalette.COLOR_ACCENT_1))
    entry.metadata["status"] = "{}/{}".format(
        localized, len(entry.metadata["observations"])
    )
    entry.update()


class ImagedMomentTree(EntryTree):
    def __init__(self, association_text_widget: QLabel, parent=None):
        super(ImagedMomentTree, self).__init__(
            ("uuid", "concept", "observer", "status"),
            association_text_widget=association_text_widget,
            parent=parent,
        )

        self.uuids = []
        self.editable_uuids = set()

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        header = self.header()
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header.setCascadingSectionResizes(True)

        self.currentItemChanged.connect(self.item_changed)

    def load_uuids(self, uuids: List[str]):
        # Update the internal list of UUIDs
        self.uuids = uuids

        # Munge the results into dicts
        results = [
            {"uuid": uuid, "type": "imaged_moment", "status": "unknown"}
            for uuid in uuids
        ]

        # Clear the tree
        self.clear()
        if not results:
            self.add_item(None, self)
            return

        # Load the results into the tree, showing a progress dialog
        progress = QProgressDialog(
            "Loading imaged moments...", "Cancel", 0, len(results), self
        )
        progress.setModal(True)
        for idx, result in enumerate(results):
            progress.setValue(idx)
            if progress.wasCanceled():
                progress.close()
                break

            item = self.add_item(result)
            self.load_imaged_moment_entry(
                item
            )  # Fetch imaged moment observation/metadata

        progress.setValue(idx + 1)  # Last call, just to finish out the progress dialog

    def load_imaged_moment_entry(self, entry: EntryTreeItem):
        """
        Load imaged moment entry data into tree.
        :param entry: Imaged moment entry item
        :return: None
        """
        while entry.childCount():  # Remove children
            entry.removeChild(entry.child(0))

        entry.metadata = get_imaged_moment(
            entry.metadata["uuid"]
        )  # Fetch original imaged moment data
        meta = entry.metadata
        meta["type"] = "imaged_moment"

        imaged_moment_uuid = meta["uuid"]

        # Pick the image reference to use
        png_image_references = list(
            filter(
                lambda x: x.get("format", None) == "image/png", meta["image_references"]
            )
        )
        jpeg_image_references = list(
            filter(
                lambda x: x.get("format", None) == "image/jpeg",
                meta["image_references"],
            )
        )
        valid_image_references = png_image_references + jpeg_image_references
        if not valid_image_references:  # No valid image reference found
            log(
                "No valid image reference found for imaged moment {}".format(
                    imaged_moment_uuid
                ),
                level=1,
            )
            meta["image_reference_uuid"] = None
            meta["url"] = None
        else:
            image_reference = valid_image_references[0]
            meta["image_reference_uuid"] = image_reference["uuid"]
            meta["url"] = image_reference["url"]

        for observation in meta["observations"]:
            obs_item = self.add_item(observation, parent=entry)
            obs_item.metadata["type"] = "observation"
            observation_boxes = list(
                extract_bounding_boxes(
                    observation["associations"],
                    observation["concept"],
                    observation["uuid"],
                )
            )

            # Distinguish boxes that correspond to the image reference from those that were drawn on the video (may or may not be the same frame)
            image_reference_boxes = [
                box
                for box in observation_boxes
                if box.image_reference_uuid == meta["image_reference_uuid"]
            ]
            video_boxes = [
                box for box in observation_boxes if box.image_reference_uuid is None
            ]

            obs_item.metadata["boxes"] = image_reference_boxes
            obs_item.metadata["video_boxes"] = video_boxes

            if observation["uuid"] in self.editable_uuids:
                obs_item.set_background("uuid", QColor("#b9ff96"))

        update_imaged_moment_entry(entry)

    def item_changed(self, current: EntryTreeItem, previous: EntryTreeItem):
        """
        Slot for item selection change
        :param current: Current item
        :param previous: Previous item
        :return: None
        """
        if not current or not current.metadata:
            self.association_text_widget.setText("")
            return
        if current.metadata["type"] == "imaged_moment":
            if not current.childCount():
                self.load_imaged_moment_entry(current)
            self.association_text_widget.setText("")
        elif current.metadata["type"] == "observation":
            associations = current.metadata["associations"]
            assoc_lines = [
                "{} | {} | {}".format(
                    assoc["link_name"], assoc["to_concept"], assoc["link_value"]
                )
                for assoc in associations
            ]
            self.association_text_widget.setText("\n".join(assoc_lines))

    def open_video_for_item(self, item: EntryTreeItem) -> bool:
        """
        Open the video for a given item in a web browser
        :param item: Item to open video
        :return: True if video opened, False if not
        """
        if item.metadata["type"] == "imaged_moment":
            im_item = item
        elif item.metadata["type"] == "observation":
            im_item = item.parent()

        video_reference_uuid = im_item.metadata.get("video_reference_uuid", None)
        if not video_reference_uuid:
            QMessageBox.warning(
                self,
                "No video reference",
                "No video reference found for this imaged moment",
            )
            return False

        # Get the video corresponding to the given video reference UUID from M3
        try:
            video_data = get_video_by_video_reference_uuid(video_reference_uuid)
        except HTTPException:
            QMessageBox.warning(
                self, "Failed to fetch video", "Failed to fetch video data from M3"
            )
            return False

        # Extract the relevant info from the video data
        video_references = video_data["video_references"]
        video_start_timestamp = video_data.get("start_timestamp", None)
        if not video_start_timestamp:
            QMessageBox.warning(
                self,
                "No video start timestamp",
                "No video start timestamp found for this video reference",
            )
            return False

        # Parse video start timestamp into datetime object
        video_start_datetime = None
        try:
            video_start_datetime = datetime.strptime(
                video_start_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        except ValueError:
            video_start_datetime = datetime.strptime(
                video_start_timestamp, "%Y-%m-%dT%H:%M:%SZ"
            )

        # Parse the annotation timestamp into a timedelta object
        annotation_timedelta = None
        if "recorded_timestamp" in im_item.metadata:
            recorded_timestamp = im_item.metadata["recorded_timestamp"]
            recorded_datetime = None
            try:
                recorded_datetime = datetime.strptime(
                    recorded_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ"
                )
            except ValueError:
                recorded_datetime = datetime.strptime(
                    recorded_timestamp, "%Y-%m-%dT%H:%M:%SZ"
                )
            annotation_timedelta = recorded_datetime - video_start_datetime
        elif "timecode" in im_item.metadata:
            hours, minutes, seconds, frames = map(
                int, im_item.metadata["timecode"].split(":")
            )
            annotation_timedelta = timedelta(
                hours=hours, minutes=minutes, seconds=seconds
            )
        elif "elapsed_time_millis" in im_item.metadata:
            elapsed_time_millis = int(im_item.metadata["elapsed_time_millis"])
            annotation_timedelta = timedelta(milliseconds=elapsed_time_millis)
        else:
            QMessageBox.warning(
                self,
                "No annotation timestamp",
                "No annotation timestamp found for this imaged moment",
            )
            return False

        # Find an HTTP MP4 video URL from the video references
        video_url = None
        for video_reference in video_references:
            video_uri = video_reference.get("uri", None)
            if not video_uri:
                continue

            if video_uri.startswith("http") and video_uri.endswith(".mp4"):
                video_url = video_uri
                break
        else:
            QMessageBox.warning(
                self,
                "No valid video URL",
                "No valid video URL found for this video reference",
            )
            return False

        # Format the video URL to include the start/end times
        annotation_seconds = annotation_timedelta.total_seconds()
        video_url_fragment = video_url + "#t={},{}".format(
            annotation_seconds, annotation_seconds + 1e-3
        )
        webbrowser.open(video_url_fragment)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.parent().parent().parent().parent().parent().admin_mode:
            if event.key() == QtCore.Qt.Key.Key_Delete:
                observations_to_delete = [
                    el
                    for el in self.selectedItems()
                    if el.metadata["type"] == "observation"
                ]
                if (
                    not observations_to_delete
                ):  # Ensure at least one observation selected
                    return

                observation_uuids = [
                    obs.metadata["uuid"] for obs in observations_to_delete
                ]

                # Show confirmation dialog
                res = QMessageBox.warning(
                    self,
                    "Confirm Observation Bulk Delete",
                    "Are you sure you want to delete the following observation(s)?\n\t"
                    + "\n\t".join(observation_uuids),
                    buttons=QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.Cancel,
                )
                if (
                    res == QMessageBox.StandardButton.Yes
                ):  # Do deletion and reload imaged moment
                    for observation_uuid in observation_uuids:
                        delete_observation(observation_uuid)
                    self.parent().parent().parent().display_panel.image_view.reload_moment()
            elif (
                event.key() == QtCore.Qt.Key.Key_R
                and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier
            ):
                # Rename all selected observations
                observations_to_rename = [
                    el
                    for el in self.selectedItems()
                    if el.metadata["type"] == "observation"
                ]
                if not observations_to_rename:
                    return

                observation_uuids = [
                    obs.metadata["uuid"] for obs in observations_to_rename
                ]

                # Show rename dialog
                dialog = QDialog(self)
                dialog.setWindowTitle("Rename Observations")
                dialog_layout = QVBoxLayout()
                dialog_layout.addWidget(QLabel("Enter new name for observation(s):"))
                concept_searchbar = ConceptSearchbar(dialog)
                dialog_layout.addWidget(concept_searchbar)
                button_box = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok
                    | QDialogButtonBox.StandardButton.Cancel
                )
                ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
                ok_button.setEnabled(False)
                button_box.accepted.connect(dialog.accept)
                button_box.rejected.connect(dialog.reject)
                concept_to_set = None

                def on_concept_update(concept: str):
                    nonlocal concept_to_set
                    valid = concept in get_all_concepts()
                    ok_button.setEnabled(valid)
                    if valid:
                        concept_to_set = concept

                concept_searchbar.set_callback(on_concept_update)
                dialog_layout.addWidget(concept_searchbar)
                dialog_layout.addWidget(button_box)
                dialog.setLayout(dialog_layout)
                result = dialog.exec()

                if result == QDialog.DialogCode.Accepted:
                    confirmed = QMessageBox.warning(
                        self,
                        "Confirm Observation Bulk Rename",
                        f"Are you sure you want to rename the following observation(s) to {concept_to_set}?\n\t"
                        + "\n\t".join(observation_uuids),
                        buttons=QMessageBox.StandardButton.Yes
                        | QMessageBox.StandardButton.Cancel,
                    )
                    if confirmed == QMessageBox.StandardButton.Yes:
                        for observation_uuid in observation_uuids:
                            rename_observation(
                                observation_uuid,
                                concept_to_set,
                                self.parent().parent().parent().observer,
                            )
                        self.parent().parent().parent().display_panel.image_view.reload_moment()
        else:
            super().keyPressEvent(event)
