# EntryTree.py (vars-localize)
from PyQt5 import QtCore
from PyQt5.QtGui import QFont, QBrush, QColor, QKeyEvent
from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem, QAbstractItemView, QDialog, QMessageBox, QHeaderView, \
    QAbstractScrollArea, QMenu, QAction, QApplication

from util.requests import get_imaged_moment_uuids, get_imaged_moment, get_other_videos, get_windowed_moments, \
    delete_observation
from util.utils import extract_bounding_boxes

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Alternative view to entry list.

@author: __author__
@status: __status__
@license: __license__
'''


class EntryTreeItem(QTreeWidgetItem):

    __slots__ = ['metadata']

    def __init__(self, parent):
        super(EntryTreeItem, self).__init__(parent)

    def set_background(self, header: str, background: QColor):
        """
        Set the background color of one or all columns
        :param header: Title of the column, or 'all' for all
        :param background: Background QColor
        :return: None
        """
        if header == 'all':
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

    def __init__(self, headers, parent=None):
        super(EntryTree, self).__init__(parent)

        self.setFont(QFont('Courier'))

        self.setHeaderLabels(headers)
        self.header_map = dict([tup[::-1] for tup in enumerate(headers)])  # header -> column lookup

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
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
            item.setText(0, 'No results found.')

        return item

    def menu(self, point):
        item = self.itemAt(point)
        if item is None:
            return

        menu = QMenu("Context menu", self)
        copy_action = QAction("Copy UUID")

        def do_copy():
            clipboard = QApplication.clipboard()
            clipboard.setText(item.metadata['uuid'])

        copy_action.triggered.connect(do_copy)
        menu.addAction(copy_action)

        menu.exec(self.viewport().mapToGlobal(point))


def update_imaged_moment_entry(entry: EntryTreeItem):
    localized = 0
    for obs_item in [entry.child(idx) for idx in range(entry.childCount())]:
        if obs_item.metadata['boxes']:  # This observation has been localized
            localized += 1
        obs_item.metadata['status'] = len(obs_item.metadata['boxes'])
        if not obs_item.metadata['status']:
            obs_item.set_background('status', QColor('#ff9696'))
        else:
            obs_item.set_background('status', QColor('#ffffff'))
        obs_item.update()

    percent_localized = localized / len(entry.metadata['observations'])
    if percent_localized < 0.25:
        entry.set_background('status', QColor('#ff9696'))
    elif percent_localized < 1:
        entry.set_background('status', QColor('#ffc996'))
    else:
        entry.set_background('status', QColor('#b9ff96'))
    entry.metadata['status'] = '{}/{}'.format(localized, len(entry.metadata['observations']))
    entry.update()


class ImagedMomentTree(EntryTree):

    def __init__(self, parent=None):
        super(ImagedMomentTree, self).__init__(
            (
                'uuid',
                'concept',
                'observer',
                'status'
            ),
            parent)

        self.loaded_concept = None
        self.loaded_uuids = []
        self.time_window = None
        self.editable_uuids = set()

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

        header = self.header()
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        header.setCascadingSectionResizes(True)

        self.currentItemChanged.connect(self.item_changed)

    def set_time_window(self, value: int):
        """
        Update the time window value
        :param value: Value to set
        :return: None
        """
        self.time_window = value

    def fetch_uuids(self, concept: str):
        """
        Fetch and load imaged moment uuids to object
        :param concept: Concept to fetch
        :return: None
        """
        self.loaded_uuids = get_imaged_moment_uuids(concept)
        self.loaded_concept = concept

    def query(self, concept: str, offset: int, limit: int):
        """
        Query and fill tree with imaged moments
        :param concept: Concept to query
        :param offset: Offset of imaged moments
        :param limit: Limit of imaged moments
        :return: None
        """
        if self.loaded_concept != concept:
            self.fetch_uuids(concept)

        results = [{
            'uuid': uuid,
            'type': 'imaged_moment',
            'status': 'unknown'
        } for uuid in self.loaded_uuids[offset:offset+limit]]

        self.clear()
        if not results:
            self.add_item(None, self)
        for result in results:
            item = self.add_item(result)
            self.load_imaged_moment_entry(item)  # Fetch imaged moment observation/metadata

    def query_imaged_moment(self, imaged_moment_uuid: str):
        """
        Query for a particular imaged moment and add it to the tree
        :param imaged_moment_uuid: Imaged moment UUID
        :return: None
        """
        self.loaded_uuids = [imaged_moment_uuid]
        self.loaded_concept = None

        result = {
            'uuid': imaged_moment_uuid,
            'type': 'imaged_moment',
            'status': 'unknown'
        }

        self.clear()
        item = self.add_item(result)
        self.load_imaged_moment_entry(item)

    def load_imaged_moment_entry(self, entry: EntryTreeItem):
        """
        Load imaged moment entry data into tree.
        :param entry: Imaged moment entry item
        :return: None
        """
        while entry.childCount():  # Remove children
            entry.removeChild(entry.child(0))

        entry.metadata = get_imaged_moment(entry.metadata['uuid'])  # Fetch original imaged moment data
        meta = entry.metadata
        meta['type'] = 'imaged_moment'

        all_moments = get_windowed_moments(  # Fetch all moments in window
            [meta['video_reference_uuid']], meta['uuid'],
            self.time_window
        )
        for moment in all_moments:  # Add other observations to the imaged moment observations list
            known_observation_uuids = [obs['uuid'] for obs in meta['observations']]
            for obs in moment['observations']:
                if obs['uuid'] not in known_observation_uuids:
                    meta['observations'].append(obs)

        for image_reference in meta['image_references']:  # Pick the image reference & URL to use
            if image_reference['format'] == 'image/png':
                meta['image_reference_uuid'] = image_reference['uuid']
                meta['url'] = image_reference['url']
                break

        for observation in meta['observations']:
            obs_item = self.add_item(observation, parent=entry)
            obs_item.metadata['type'] = 'observation'
            obs_item.metadata['boxes'] = list(extract_bounding_boxes(
                observation['associations'],
                observation['concept'],
                observation['uuid'],
                im_ref_filter=meta['image_reference_uuid']
            ))
            if observation['uuid'] in self.editable_uuids:
                obs_item.set_background('uuid', QColor('#b9ff96'))

        update_imaged_moment_entry(entry)

    def item_changed(self, current: EntryTreeItem, previous: EntryTreeItem):
        """
        Slot for item selection change
        :param current: Current item
        :param previous: Previous item
        :return: None
        """
        if not current or not current.metadata:
            self.parent().parent().association_text.setText('')
            return
        if current.metadata['type'] == 'imaged_moment':
            if not current.childCount():
                self.load_imaged_moment(current)
            self.parent().parent().association_text.setText('')
        elif current.metadata['type'] == 'observation':
            associations = current.metadata['associations']
            assoc_lines = ['{} | {} | {}'.format(assoc['link_name'], assoc['to_concept'], assoc['link_value']) for assoc in associations if assoc['link_name'] != 'bounding box']
            self.parent().parent().association_text.setText('\n'.join(assoc_lines))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.parent().parent().parent().admin_mode and event.key() == QtCore.Qt.Key_Delete:
            observations_to_delete = [el for el in self.selectedItems() if el.metadata['type'] == 'observation']
            if not observations_to_delete:  # Ensure at least one observation selected
                return

            observation_uuids = [obs.metadata['uuid'] for obs in observations_to_delete]

            # Show confirmation dialog
            res = QMessageBox.warning(self, 'Confirm Observation Bulk Delete',
                                      'Are you sure you want to delete the following observation(s)?\n\t' + '\n\t'.join(observation_uuids),
                                      buttons=QMessageBox.Yes | QMessageBox.Cancel)
            if res == QMessageBox.Yes:  # Do deletion and reload imaged moment
                for observation_uuid in observation_uuids:
                    delete_observation(observation_uuid)
                self.parent().parent().parent().display_panel.image_view.reload_moment()
