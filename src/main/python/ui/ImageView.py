# ImageView.py (vars-localize)
import util.requests
from ui.ConceptSearchbar import ConceptSearchbar
from ui.EntryTree import EntryTreeItem
from util.utils import extract_bounding_boxes

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

QGraphicsView custom widget for controlling image/localization graphics and input.

@author: __author__
@status: __status__
@license: __license__
'''
from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF, QLineF
from PyQt5.QtGui import QResizeEvent, QMouseEvent, QPixmap, QColor, QKeyEvent, QPen, QFont
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene, QDialog, QVBoxLayout, QLabel, QPushButton

from ui.BoundingBox import BoundingBoxManager, GraphicsBoundingBox, SourceBoundingBox
from ui.PropertiesDialog import PropertiesDialog
from util import utils
from util.requests import delete_box, create_box, modify_box, create_observation


class ImageView(QGraphicsView):

    def __init__(self, parent=None):
        super(ImageView, self).__init__(parent)

        self.setStyleSheet('border: 0px;')
        self.setMinimumSize(1200, 675)
        self.setMouseTracking(True)

        self.image_scene = QGraphicsScene()
        self.setScene(self.image_scene)
        self.refit()

        self.observation_uuid = None
        self.moment = None
        self.observation_concepts = None
        self.box_managers = None
        self.box_sources = None
        self.enabled_observations = None

        self.pixmap_src = None
        self.pixmap_scalar = None
        self.pixmap_pos = None

        # Graphical box selection
        self.pt_1 = None
        self.pt_2 = None
        self.selected_box = None
        self.mouse_line_pen = QPen(Qt.red)
        # self.mouse_line_pen.setStyle(Qt.DotLine)
        self.mouse_hline = QLineF()
        self.mouse_vline = QLineF()

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

            if self.box_sources:
                for uuid, enabled in self.enabled_observations.items():
                    if not enabled:
                        continue
                    for box in self.box_sources[uuid]:
                        box_item = self.draw_bounding_box(box, self.box_managers[uuid])
                        if self.selected_box == box:
                            box_item.set_highlighted(True)

            # Draw crosshairs
            self.scene().addLine(self.mouse_hline, self.mouse_line_pen)
            self.scene().addLine(self.mouse_vline, self.mouse_line_pen)
            self.setCursor(Qt.BlankCursor)

            drag_rect = self.calc_drag_rect()
            if drag_rect:  # Drag rectangle should be drawn
                top_left = self.get_scene_rel_point(QPointF(drag_rect.x(), drag_rect.y()))
                scaled_size = drag_rect.size() * self.pixmap_scalar
                self.scene().addRect(QRectF(top_left, scaled_size), QColor(0, 255, 0))
        else:  # No image loaded
            text_item = self.scene().addText('No image loaded.', QFont('Courier New'))
            text_item.setDefaultTextColor(QColor(255, 255, 255))
            text_item.setPos(self.width() / 2 - text_item.boundingRect().width() / 2,
                             self.height() / 2 - text_item.boundingRect().height() / 2)
            self.setCursor(Qt.ArrowCursor)

    def clear(self):
        """
        Empty everything from the scene, reset bounding box managers
        :return: None
        """
        self.scene().clear()
        if self.box_managers:
            for box_manager in self.box_managers.values():
                box_manager.clear()

    def set_entry(self, entry: EntryTreeItem):
        """
        Set the selected entry, load associated data
        :param entry: Entry tree item to from
        :return: None
        """
        if entry.metadata['type'] == 'imaged_moment':
            entry.setExpanded(True)
            if entry != self.moment:
                self.load_moment(entry)
            self.select_observation('all')
        elif entry.metadata['type'] == 'observation':
            if entry.parent() != self.moment:
                self.load_moment(entry.parent())
            self.select_observation(entry.metadata['uuid'])

    def load_moment(self, entry: EntryTreeItem):
        """
        Load pertinent data from imaged moment entry
        :param entry: Entry tree item of imaged moment
        :return: None
        """
        self.moment = entry
        if 'cached_image' not in entry.metadata.keys():  # Cache pixmap
            entry.metadata['cached_image'] = util.requests.fetch_image(entry.metadata['url'])
        self.set_pixmap(entry.metadata['cached_image'])  # Set pixmap
        observation_entries = [entry.child(idx) for idx in range(entry.childCount())]
        self.observation_concepts = dict()
        self.box_managers = dict()
        self.box_sources = dict()
        self.enabled_observations = dict()
        for observation_entry in observation_entries:
            uuid = observation_entry.metadata['uuid']
            concept = observation_entry.metadata['concept']
            self.observation_concepts[uuid] = concept
            self.box_managers[uuid] = BoundingBoxManager()  # Construct new bounding box manager
            self.box_managers[uuid].set_box_click_callback(self.show_box_properties_dialog)
            self.box_sources[uuid] = observation_entry.metadata['boxes']
            self.enabled_observations[uuid] = True

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
            self.enabled_observations[uuid] = True if (observation_uuid == uuid or observation_uuid == 'all') else False
        self.observation_uuid = observation_uuid if observation_uuid != 'all' else None

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
        if not pixmap:
            return
        scaled_pixmap = pixmap.scaled(self.width(), self.height(), Qt.KeepAspectRatio)
        self.pixmap_scalar = scaled_pixmap.width() / pixmap.width()
        self.pixmap_pos = QPointF(
            self.width() / 2 - scaled_pixmap.width() / 2,
            self.height() / 2 - scaled_pixmap.height() / 2)

        pixmap_item = self.scene().addPixmap(scaled_pixmap)
        pixmap_item.setPos(self.pixmap_pos)
        return pixmap_item

    def draw_bounding_box(self, box_src: SourceBoundingBox, manager: BoundingBoxManager):
        """
        Draw a bounding box in the scene, add to box manager
        :param box_src: Source bounding box to add
        :param manager: Bounding box manager
        :return: Graphical bounding box item
        """
        box_pos = self.get_scene_rel_point(QPointF(box_src.x(), box_src.y()))
        box_item = manager.make_box(
            box_pos.x(),
            box_pos.y(),
            self.pixmap_scalar * box_src.width(),
            self.pixmap_scalar * box_src.height(),
            box_src.label,
            box_src)
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
            self.pixmap_scalar * pt.x() + self.pixmap_pos.x(),
            self.pixmap_scalar * pt.y() + self.pixmap_pos.y()
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
        dialog.exec_()

        box_json_after = box.source.get_json()
        if box_json_after != box_json_before:
            box.source.observer = self.window().observer  # Update observer field
            box.source.strength = utils.get_observer_confidence(box.source.observer)  # Update strength field
            modify_box(box_json_after, self.observation_uuid, box.source.association_uuid)

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
        if box in self.box_sources[box.observation_uuid]:  # Protect
            self.box_sources[box.observation_uuid].remove(box)
            delete_box(box.association_uuid)

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
        dialog.setWindowTitle('Specify a concept')
        dialog.setWindowFlag(Qt.WindowCloseButtonHint, False)
        search = ConceptSearchbar()

        submit_button = QPushButton('Submit')
        submit_button.setEnabled(False)
        submit_button.pressed.connect(dialog.close)

        concept_selected = ''

        def update_concept_selected(concept):
            nonlocal concept_selected
            nonlocal submit_button
            concept_selected = concept
            submit_button.setEnabled(True)
        search.set_callback(update_concept_selected)

        dialog.layout().addWidget(search)
        dialog.layout().addWidget(submit_button)

        dialog.setModal(True)
        dialog.exec_()

        return concept_selected

    def make_new_observation(self, concept):
        """
        Create a new observation of the specified concept
        :param concept: Concept to observe
        :return: Observation JSON response
        """
        kwargs = dict()
        fields = self.moment.metadata.keys()
        if 'timecode' in fields:
            kwargs['timecode'] = self.moment.metadata['timecode']
        if 'elapsed_time' in fields:
            kwargs['elapsed_time'] = self.moment.metadata['elapsed_time']
        if 'recorded_date' in fields:
            kwargs['recorded_date'] = self.moment.metadata['recorded_date']

        observation = create_observation(
            self.moment.metadata['video_reference_uuid'],
            concept,
            self.window().observer,
            **kwargs
        )

        uuid = observation['observation_uuid']
        observation_metadata = {
            'concept': observation['concept'],
            'uuid': uuid,
            'observer': observation['observer'],
            'boxes': list(extract_bounding_boxes(
                observation['associations'],
                observation['concept'],
                uuid
            )),
            'type': 'observation'
        }
        self.window().search_panel.entry_tree.add_item(observation_metadata, self.moment)  # Register in tree

        # Register in view records
        self.observation_concepts[uuid] = concept
        self.box_managers[uuid] = BoundingBoxManager()  # Construct new bounding box manager
        self.box_managers[uuid].set_box_click_callback(self.show_box_properties_dialog)
        self.box_sources[uuid] = observation_metadata['boxes']
        self.enabled_observations[uuid] = True

        return observation

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
            uuid = observation['observation_uuid']

        box.observation_uuid = uuid
        self.draw_bounding_box(box, self.box_managers[uuid])
        self.box_sources[uuid].append(box)
        self
        response_json = create_box(box.get_json(), uuid)
        box.association_uuid = response_json['uuid']

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            new_rect = self.calc_drag_rect()
            if new_rect:
                new_rect = self.calc_crop_rect(new_rect)
                box_json = {
                    'x': int(new_rect.x()),
                    'y': int(new_rect.y()),
                    'width': int(new_rect.width()),
                    'height': int(new_rect.height()),
                    'image_reference_uuid': self.moment.metadata['image_reference_uuid']
                }

                concept = self.observation_concepts[self.observation_uuid] if self.observation_uuid else ''
                observer = self.window().observer
                new_src_box = SourceBoundingBox(
                    box_json,
                    concept,
                    observer,
                    utils.get_observer_confidence(observer)
                )
                if new_src_box.width() * new_src_box.height() > 100:
                    self.handle_new_box(new_src_box)
            self.pt_1 = None
            self.pt_2 = None
            self.redraw()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            self.pt_1 = self.get_im_rel_point(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            self.pt_2 = self.get_im_rel_point(event.pos())

        self.mouse_hline.setLine(0, event.y(), self.scene().width(), event.y())
        self.mouse_vline.setLine(event.x(), 0, event.x(), self.scene().height())
        self.redraw()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            self.pt_1 = None
            self.pt_2 = None
            for uuid, enabled in self.enabled_observations.items():
                if enabled:
                    self.box_managers[uuid].check_box_click(event.pos())

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.redraw()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Up:
            self.window().search_panel.select_prev()
        elif event.key() == Qt.Key_Down:
            self.window().search_panel.select_next()
