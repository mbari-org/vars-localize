"""
Custom QGraphicsView widget for controlling image/localization graphics and input.
"""

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QLineF
from PyQt6.QtGui import (
    QResizeEvent,
    QMouseEvent,
    QPixmap,
    QColor,
    QKeyEvent,
    QPen,
    QFont,
)
from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QDialog,
    QVBoxLayout,
    QPushButton,
    QInputDialog,
    QMessageBox,
)

from vars_localize.ui.ConceptSearchbar import ConceptSearchbar
from vars_localize.ui.EntryTree import EntryTreeItem, update_imaged_moment_entry
from vars_localize.ui.BoundingBox import (
    BoundingBoxManager,
    GraphicsBoundingBox,
    SourceBoundingBox,
)
from vars_localize.ui.PropertiesDialog import PropertiesDialog
from vars_localize.util.m3 import (
    delete_box,
    create_box,
    modify_box,
    create_observation,
    fetch_image,
    get_all_parts,
    get_video_data,
)


class ImageView(QGraphicsView):
    def __init__(self, parent=None):
        super(ImageView, self).__init__(parent)

        self.setStyleSheet("border: 0px;")
        self.setMinimumSize(1200, 675)
        self.setViewportMargins(-2, -2, -2, -2)
        self.setMouseTracking(True)

        self.image_scene = QGraphicsScene()
        self.setScene(self.image_scene)
        self.refit()

        self.observation_uuid = None
        self.observer = None
        self.moment = None
        self.observation_map = None
        self.enabled_observations = None

        self.pixmap_src = None
        self.pixmap_scalar = None
        self.pixmap_pos = None

        self.select_next = None
        self.select_prev = None

        # Graphical box selection
        self.pt_1 = None
        self.pt_2 = None
        self.selected_box = None
        self.hovered_box = None
        self.mouse_line_pen = QPen(Qt.GlobalColor.red)
        self.mouse_hline = QLineF()
        self.mouse_vline = QLineF()

        self.hov_tl_rect = None
        self.hov_tr_rect = None
        self.hov_bl_rect = None
        self.hov_br_rect = None
        self.resize_type = None
        self.resize_offset = None

        self.hov_pt_1 = None

    def redraw(self):
        """
        Redraw scene with all necessary components
        :return: None
        """
        self.clear()
        self.refit()
        self.scene().setBackgroundBrush(QColor(0, 0, 0))
        if self.pixmap_src:  # Image loaded, draw image + relevant components
            self.draw_pixmap(self.pixmap_src)

            self.draw_ancillary_data()

            if self.enabled_observations:
                for uuid, enabled in self.enabled_observations.items():
                    if not enabled:
                        continue

                    item = self.observation_map[uuid]
                    box_manager = item.metadata["box_manager"]
                    boxes = item.metadata["boxes"]
                    video_boxes = item.metadata["video_boxes"]
                    for box in boxes:
                        box_item = self.draw_bounding_box(box, box_manager)
                        if self.selected_box == box:
                            box_item.set_highlighted(True)
                        if self.hovered_box == box:
                            self.draw_drag_corners(box_item)
                    for video_box in video_boxes:
                        self.draw_bounding_box(video_box, box_manager, editable=False)

            # Draw crosshairs
            self.scene().addLine(self.mouse_hline, self.mouse_line_pen)
            self.scene().addLine(self.mouse_vline, self.mouse_line_pen)
            self.setCursor(Qt.CursorShape.BlankCursor)

            drag_rect = self.calc_drag_rect()
            if drag_rect:  # Drag rectangle should be drawn
                top_left = self.get_scene_rel_point(
                    QPointF(drag_rect.x(), drag_rect.y())
                )
                scaled_size = drag_rect.size() * self.pixmap_scalar
                self.scene().addRect(
                    QRectF(QPointF(top_left), scaled_size), QColor(0, 255, 0)
                )
        else:  # No image loaded
            text_item = self.scene().addText("No image loaded.", QFont("Courier New"))
            text_item.setDefaultTextColor(QColor(255, 255, 255))
            text_item.setPos(
                self.width() / 2 - text_item.boundingRect().width() / 2,
                self.height() / 2 - text_item.boundingRect().height() / 2,
            )
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def clear(self):
        """
        Empty everything from the scene, reset bounding box managers
        :return: None
        """
        self.scene().clear()
        if self.observation_map:
            for box_manager in [
                entry.metadata["box_manager"] for entry in self.observation_map.values()
            ]:
                box_manager.clear()

    def set_entry(self, entry: EntryTreeItem):
        """
        Set the selected entry, load associated data
        :param entry: Entry tree item to from
        :return: None
        """
        if entry.metadata["type"] == "imaged_moment":
            entry.setExpanded(True)
            if entry != self.moment:
                self.load_moment(entry)
            self.select_observation("all")
        elif entry.metadata["type"] == "observation":
            if entry.parent() != self.moment:
                self.load_moment(entry.parent())
            self.select_observation(entry.metadata["uuid"])

    def load_moment(self, entry: EntryTreeItem):
        """
        Load pertinent data from imaged moment entry
        :param entry: Entry tree item of imaged moment
        :return: None
        """
        self.moment = entry
        if "cached_image" not in entry.metadata.keys():  # Cache pixmap
            entry.metadata["cached_image"] = fetch_image(entry.metadata["url"])
        self.set_pixmap(entry.metadata["cached_image"])  # Set pixmap
        observation_entries = [entry.child(idx) for idx in range(entry.childCount())]
        self.observation_map = dict(
            [(entry.metadata["uuid"], entry) for entry in observation_entries]
        )  # observation uuid -> entry tree item
        self.enabled_observations = dict()
        for observation_entry in observation_entries:
            uuid = observation_entry.metadata["uuid"]
            observation_entry.metadata["box_manager"] = (
                BoundingBoxManager()
            )  # Construct new bounding box manager
            observation_entry.metadata["box_manager"].set_box_click_callback(
                self.show_box_properties_dialog
            )

            def override_obs_selection(obs_entry):
                def wrapped(_):
                    self.parent().parent().parent().load_entry(obs_entry, None)
                    self.parent().parent().parent().search_panel.select_entry(obs_entry)

                return wrapped

            observation_entry.metadata["box_manager"].set_box_right_click_callback(
                override_obs_selection(observation_entry)
            )
            self.enabled_observations[uuid] = True

    def draw_drag_corners(self, box: GraphicsBoundingBox):
        length = 10
        tl_rect = self.scene().addRect(
            box.x(), box.y(), length, length, pen=box.color.lighter()
        )
        tr_rect = self.scene().addRect(
            box.x() + box.width - length,
            box.y(),
            length,
            length,
            pen=box.color.lighter(),
        )
        bl_rect = self.scene().addRect(
            box.x(),
            box.y() + box.height - length,
            length,
            length,
            pen=box.color.lighter(),
        )
        br_rect = self.scene().addRect(
            box.x() + box.width - length,
            box.y() + box.height - length,
            length,
            length,
            pen=box.color.lighter(),
        )

        self.hov_tl_rect = tl_rect.rect()
        self.hov_tr_rect = tr_rect.rect()
        self.hov_bl_rect = bl_rect.rect()
        self.hov_br_rect = br_rect.rect()

    def set_pixmap(self, pixmap):
        """
        Set source pixmap, clear corner points
        :return: None
        """
        self.pixmap_src = pixmap
        self.pt_1 = None
        self.pt_2 = None

    def select_observation(self, observation_uuid: str):
        """
        Select and display bounding boxes for specified observation only
        :param observation_uuid: Observation UUID to source
        :return: None
        """
        for uuid in self.enabled_observations.keys():
            self.enabled_observations[uuid] = (
                True
                if (observation_uuid == uuid or observation_uuid == "all")
                else False
            )
        self.observation_uuid = observation_uuid if observation_uuid != "all" else None

    def refit(self):
        """
        Refit sceneRect to fit entire view
        :return: None
        """
        self.setSceneRect(0, 0, self.width(), self.height())

    def draw_pixmap(self, pixmap: QPixmap):
        """
        Scale and draw pixmap in scene
        :param pixmap: Pixmap object to draw
        :return: None
        """
        if not pixmap or pixmap.isNull():
            return
        scaled_pixmap = pixmap.scaled(
            self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatio
        )
        self.pixmap_scalar = scaled_pixmap.width() / pixmap.width()
        self.pixmap_pos = QPointF(
            self.width() / 2 - scaled_pixmap.width() / 2,
            self.height() / 2 - scaled_pixmap.height() / 2,
        )

        pixmap_item = self.scene().addPixmap(scaled_pixmap)
        pixmap_item.setPos(self.pixmap_pos)
        return pixmap_item

    def draw_ancillary_data(self):
        """
        Draw ancillary data on the image, if there is any
        :return: None
        """
        text_dict = {}

        if "ancillary_data" in self.moment.metadata.keys():
            ancillary_data = self.moment.metadata["ancillary_data"]

            if "depth_meters" in ancillary_data:
                text_dict["Depth (m): {:<10.2f}"] = ancillary_data["depth_meters"]

            if "latitude" in ancillary_data:
                text_dict["Latitude: {:<10.3f}"] = ancillary_data["latitude"]

            if "longitude" in ancillary_data:
                text_dict["Longitude: {:<10.3f}"] = ancillary_data["longitude"]

        if "recorded_timestamp" in self.moment.metadata.keys():
            text_dict["Recorded: {:<20}"] = (
                self.moment.metadata["recorded_timestamp"]
                .replace("T", " ")
                .replace("Z", "")
            )

        if "video_data" not in self.moment.metadata.keys():
            video_data = get_video_data(self.moment.metadata["video_reference_uuid"])
            self.moment.metadata["video_data"] = video_data

        if (
            self.moment.metadata["video_data"]
            and "uri" in self.moment.metadata["video_data"]
        ):
            uri = self.moment.metadata["video_data"]["uri"]
            if uri.startswith("urn:"):
                video_sequence_name = self.moment.metadata["video_data"]["uri"].split(
                    ":"
                )[-1]
                text_dict["Video: {:<10}"] = video_sequence_name

        text_str = " ".join(k.format(v) for k, v in text_dict.items())
        text_item = self.scene().addText(text_str, QFont("Courier New"))
        text_item.setDefaultTextColor(QColor(255, 255, 255))
        text_item.setPos(10, self.height() - text_item.boundingRect().height() - 10)

    def draw_bounding_box(
        self,
        box_src: SourceBoundingBox,
        manager: BoundingBoxManager,
        editable: bool = True,
    ):
        """
        Draw a bounding box in the scene, add to box manager
        :param box_src: Source bounding box to add
        :param manager: Bounding box manager
        :param editable: Box should be editable
        :return: Graphical bounding box item
        """
        box_pos = self.get_scene_rel_point(QPointF(box_src.x(), box_src.y()))
        box_item = manager.make_box(
            box_pos.x(),
            box_pos.y(),
            self.pixmap_scalar * box_src.width(),
            self.pixmap_scalar * box_src.height(),
            box_src.label,
            box_src,
            editable=editable,
        )
        self.scene().addItem(box_item)
        return box_item

    def get_im_rel_point(self, pt: QPoint):
        """
        Convert a scene-relative point to an image-relative point
        :return: Point relative to the image
        """
        return QPointF(
            (pt.x() - self.pixmap_pos.x()) / self.pixmap_scalar,
            (pt.y() - self.pixmap_pos.y()) / self.pixmap_scalar,
        )

    def get_scene_rel_point(self, pt: QPointF):
        """
        Convert an image-relative point to a scene-relative point
        :return: Point relative to the scene
        """
        return QPoint(
            int(self.pixmap_scalar * pt.x() + self.pixmap_pos.x()),
            int(self.pixmap_scalar * pt.y() + self.pixmap_pos.y()),
        )

    def show_box_properties_dialog(self, box: GraphicsBoundingBox):
        """
        Construct a dialog for bounding box properties
        :param box: Graphical bounding box object to manipulate
        :return: None
        """
        self.selected_box = box.source
        self.redraw()

        box_json_before = box.source.get_json()

        dialog = PropertiesDialog(box.source)
        dialog.setup_form(self.pixmap_src, self.redraw)
        dialog.set_delete_callback(self.delete_box)

        dialog.setModal(True)
        dialog.exec()

        box_json_after = box.source.get_json()
        if box_json_after != box_json_before:
            box.source.observer = self.observer  # Update observer field
            modify_box(
                box_json_after, box.source.observation_uuid, box.source.association_uuid
            )  # Call modification request
            update_imaged_moment_entry(self.moment)  # Update tree

        self.pt_1 = None
        self.pt_2 = None

        self.selected_box = None
        self.redraw()

    def delete_box(self, box: SourceBoundingBox):
        """
        Delete a box from the source, save
        :param box: Source bounding box to delete
        :return: None
        """
        source_boxes = self.observation_map[box.observation_uuid].metadata["boxes"]
        if (
            box in self.observation_map[box.observation_uuid].metadata["boxes"]
        ):  # Protect
            source_boxes.remove(box)
            delete_box(box.association_uuid)  # Call deletion request
            update_imaged_moment_entry(self.moment)  # Update tree

    def calc_drag_rect(self):
        """
        Compute the drag selection rectangle if possible
        :return: Rectangle if possible, else None
        """
        if self.pt_1 and self.pt_2:
            x = self.pt_1.x()
            y = self.pt_1.y()
            w = self.pt_2.x() - x
            h = self.pt_2.y() - y

            if w < 0:
                w = -w
                x = self.pt_2.x()
            if h < 0:
                h = -h
                y = self.pt_2.y()

            return QRectF(x, y, w, h)
        return None

    def calc_crop_rect(self, drag_rect: QRectF):
        """
        Crop a rectangle to the bounds of the image
        :param drag_rect: Drag rectangle
        :return: Cropped rectangle
        """
        x = drag_rect.x()
        y = drag_rect.y()
        w = drag_rect.width()
        h = drag_rect.height()
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        if x + w > self.pixmap_src.width():
            w = self.pixmap_src.width() - x
        if y + h > self.pixmap_src.height():
            h = self.pixmap_src.height() - y

        return QRectF(x, y, w, h)

    def prompt_concept(self):
        """
        Prompt for a concept selection and return selection
        :return: Concept selected
        """
        dialog = QDialog()
        dialog.setLayout(QVBoxLayout())
        dialog.setWindowTitle("Specify a concept")
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        search = ConceptSearchbar()

        submit_button = QPushButton("Submit")
        submit_button.setEnabled(False)
        submit_button.pressed.connect(dialog.close)

        concept_selected = ""

        def update_concept_selected(concept):
            nonlocal concept_selected
            nonlocal submit_button
            concept_selected = concept
            submit_button.setEnabled(True)

        search.set_callback(update_concept_selected)

        dialog.layout().addWidget(search)
        dialog.layout().addWidget(submit_button)

        dialog.setModal(True)
        dialog.exec()

        return concept_selected

    def make_new_observation(self, concept):
        """
        Create a new observation of the specified concept
        :param concept: Concept to observe
        :return: Observation JSON response
        """
        kwargs = dict()
        fields = self.moment.metadata.keys()
        if "timecode" in fields:
            kwargs["timecode"] = self.moment.metadata["timecode"]
        if "elapsed_time_millis" in fields:
            kwargs["elapsed_time_millis"] = self.moment.metadata["elapsed_time_millis"]
        if "recorded_timestamp" in fields:
            kwargs["recorded_timestamp"] = self.moment.metadata["recorded_timestamp"]

        observation = create_observation(  # Call observation creation request
            self.moment.metadata["video_reference_uuid"],
            concept,
            self.observer,
            **kwargs,
        )

        self.moment.treeWidget().editable_uuids.add(observation["observation_uuid"])

        self.reload_moment()

        return observation

    def reload_moment(self):
        """
        Fully reload the imaged moment.
        :return: None
        """
        image = self.moment.metadata.get(
            "cached_image", None
        )  # Backup image, so no re-fetch
        self.moment.treeWidget().load_imaged_moment_entry(
            self.moment
        )  # Reload the tree
        if image is not None:
            self.moment.metadata["cached_image"] = image
        self.load_moment(self.moment)  # Reload imaged moment

    def handle_new_box(self, box: SourceBoundingBox):
        """
        Create a new box, creating new observation if needed
        :param box: Source bounding box
        :return: None
        """
        uuid = self.observation_uuid
        if not uuid:  # Imaged moment selected
            new_concept = self.prompt_concept()
            if not new_concept:  # No concept was specified
                return
            observation = self.make_new_observation(new_concept)
            box.set_label(new_concept)
            uuid = observation["observation_uuid"]

        box.observation_uuid = uuid
        self.draw_bounding_box(box, self.observation_map[uuid].metadata["box_manager"])
        self.observation_map[uuid].metadata["boxes"].append(box)
        response_json = create_box(box.get_json(), uuid, to_concept=box.part)
        box.association_uuid = response_json["uuid"]
        update_imaged_moment_entry(self.moment)  # Update tree

    def reset_mouse(self):
        self.pt_1 = None
        self.pt_2 = None
        self.hov_pt_1 = None
        self.resize_offset = None
        self.resize_type = None
        self.redraw()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            new_rect = self.calc_drag_rect()
            if new_rect:
                new_rect = self.calc_crop_rect(new_rect)
                box_json = {
                    "x": int(new_rect.x()),
                    "y": int(new_rect.y()),
                    "width": int(new_rect.width()),
                    "height": int(new_rect.height()),
                    "image_reference_uuid": self.moment.metadata[
                        "image_reference_uuid"
                    ],
                }

                concept = (
                    self.observation_map[self.observation_uuid].metadata["concept"]
                    if self.observation_uuid
                    else ""
                )
                observer = self.observer

                acceptable_parts = ["self"] + get_all_parts()
                part, part_accepted = QInputDialog.getItem(
                    self, "Part Selection", "Select a part", acceptable_parts, current=0
                )
                if not part_accepted:
                    self.reset_mouse()
                    return

                if part not in acceptable_parts:
                    QMessageBox.critical(
                        self,
                        "Error: Bad Part",
                        'Bad concept part: "{}". Localization not created.'.format(
                            part
                        ),
                    )
                    self.reset_mouse()
                    return

                new_src_box = SourceBoundingBox(box_json, concept, observer, part=part)
                if new_src_box.width() * new_src_box.height() > 100:
                    self.handle_new_box(new_src_box)

            if self.resize_type:
                modify_box(
                    self.hovered_box.get_json(),
                    self.hovered_box.observation_uuid,
                    self.hovered_box.association_uuid,
                )

            self.reset_mouse()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos_f = QPointF(event.pos())
        if self.pixmap_src:
            self.pt_1 = self.get_im_rel_point(pos_f)
        if self.hovered_box:
            corner_box = None
            self.hov_pt_1 = self.get_im_rel_point(pos_f)
            if self.hov_tl_rect.contains(pos_f):
                self.resize_type = 1
                corner_box = self.hov_tl_rect
            elif self.hov_tr_rect.contains(pos_f):
                self.resize_type = 2
                corner_box = self.hov_tr_rect
            elif self.hov_bl_rect.contains(pos_f):
                self.resize_type = 3
                corner_box = self.hov_bl_rect
            elif self.hov_br_rect.contains(pos_f):
                self.resize_type = 4
                corner_box = self.hov_br_rect
            else:
                self.hov_pt_1 = None

            if corner_box:
                self.pt_1 = None
                x, y, _, _ = corner_box.getRect()
                corner = self.get_im_rel_point(QPoint(int(x), int(y)))
                self.resize_offset = self.hov_pt_1 - corner

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            self.pt_2 = self.get_im_rel_point(event.pos())
            if self.hovered_box:
                if self.resize_type == 1:
                    new_tl_corner = (self.pt_2 - self.resize_offset).toPoint()
                    if new_tl_corner.x() < 0:
                        new_tl_corner.setX(0)
                    if new_tl_corner.y() < 0:
                        new_tl_corner.setY(0)
                    self.hovered_box.setTopLeft(new_tl_corner)
                elif self.resize_type == 2:
                    new_tr_corner = (self.pt_2 - self.resize_offset).toPoint()
                    new_tr_corner.setX(
                        int(new_tr_corner.x() + 2 * self.resize_offset.x())
                    )
                    if new_tr_corner.x() > self.pixmap_src.width():
                        new_tr_corner.setX(int(self.pixmap_src.width()))
                    if new_tr_corner.y() < 0:
                        new_tr_corner.setY(0)
                    self.hovered_box.setTopRight(new_tr_corner)
                elif self.resize_type == 3:
                    new_bl_corner = (self.pt_2 - self.resize_offset).toPoint()
                    new_bl_corner.setY(
                        int(new_bl_corner.y() + 2 * self.resize_offset.y())
                    )
                    if new_bl_corner.x() < 0:
                        new_bl_corner.setX(0)
                    if new_bl_corner.y() > self.pixmap_src.height():
                        new_bl_corner.setY(int(self.pixmap_src.height()))
                    self.hovered_box.setBottomLeft(new_bl_corner)
                elif self.resize_type == 4:
                    new_br_corner = (self.pt_2 - self.resize_offset).toPoint()
                    new_br_corner.setX(
                        int(new_br_corner.x() + 2 * self.resize_offset.x())
                    )
                    new_br_corner.setY(
                        int(new_br_corner.y() + 2 * self.resize_offset.y())
                    )
                    if new_br_corner.x() > self.pixmap_src.width():
                        new_br_corner.setX(int(self.pixmap_src.width()))
                    if new_br_corner.y() > self.pixmap_src.height():
                        new_br_corner.setY(int(self.pixmap_src.height()))
                    self.hovered_box.setBottomRight(new_br_corner)

        self.mouse_hline.setLine(
            0, event.pos().y(), self.scene().width(), event.pos().y()
        )
        self.mouse_vline.setLine(
            event.pos().x(), 0, event.pos().x(), self.scene().height()
        )

        if self.enabled_observations and not self.resize_type:
            for uuid, enabled in self.enabled_observations.items():
                if enabled:
                    hov_box_item = (
                        self.observation_map[uuid]
                        .metadata["box_manager"]
                        .get_box_hovered(event.pos())
                    )
                    if hov_box_item:
                        self.hovered_box = hov_box_item.source
                    else:
                        self.hovered_box = None

        self.redraw()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            self.pt_1 = None
            self.pt_2 = None
            for uuid, enabled in self.enabled_observations.items():
                if enabled:
                    self.observation_map[uuid].metadata["box_manager"].check_box_click(
                        event.pos(), event.button() == Qt.MouseButton.RightButton
                    )

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.redraw()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Up:
            self.select_prev()
        elif event.key() == Qt.Key.Key_Down:
            self.select_next()
