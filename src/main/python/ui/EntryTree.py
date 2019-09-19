# EntryTree.py (vars-localize)
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem
from util.requests import get_imaged_moment_uuids, get_imaged_moment
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


class EntryTree(QTreeWidget):

    def __init__(self, headers, parent=None):
        super(EntryTree, self).__init__(parent)

        self.setFont(QFont('Courier'))

        self.setHeaderLabels(headers)
        self.header_map = dict([tup[::-1] for tup in enumerate(headers)])  # header -> column lookup

    def add_item(self, data: dict, parent=None):
        """
        Create an entry tree item from dictionary of data, add to tree, and return item
        :param data: dict of data attributes
        :param parent: Parent object
        :return: Entry tree item
        """
        item = EntryTreeItem(parent if parent else self)
        item.metadata = data

        if data:
            for header, datum in data.items():
                if header in self.header_map.keys():
                    col = self.header_map[header]
                    item.setText(col, str(datum))
        else:
            item.setText(0, 'No results found.')

        return item


class ImagedMomentTree(EntryTree):

    def __init__(self, parent=None):
        super(ImagedMomentTree, self).__init__(
            (
                'uuid',
                'concept',
                'observer'
            ),
            parent)

        self.loaded_concept = None
        self.loaded_uuids = []

        self.currentItemChanged.connect(self.item_changed)

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
            'type': 'imaged_moment'
        } for uuid in self.loaded_uuids[offset:offset+limit]]

        self.clear()
        if not results:
            self.add_item(None, self)
        for result in results:
            item = self.add_item(result)

    def item_changed(self, current: EntryTreeItem, previous: EntryTreeItem):
        """
        Slot for item selection change
        :param current: Current item
        :param previous: Previous item
        :return: None
        """
        meta = current.metadata
        if not current or not meta:
            return
        if meta['type'] == 'imaged_moment' and not current.childCount():
            imaged_moment = get_imaged_moment(meta['uuid'])

            # Get indices
            meta['video_reference_uuid'] = imaged_moment['video_reference_uuid']
            fields = imaged_moment.keys()
            if 'timecode' in fields:
                meta['timecode'] = imaged_moment['timecode']
            if 'elapsed_time' in fields:
                meta['elapsed_time'] = imaged_moment['elapsed_time']
            if 'recorded_date' in fields:
                meta['recorded_date'] = imaged_moment['recorded_date']

            for image_reference in imaged_moment['image_references']:
                if image_reference['format'] == 'image/png':
                    meta['image_reference_uuid'] = image_reference['uuid']
                    meta['url'] = image_reference['url']
                    break

            observations = imaged_moment['observations']
            for observation in observations:
                observation_metadata = {
                    'concept': observation['concept'],
                    'uuid': observation['uuid'],
                    'observer': observation['observer'],
                    'boxes': list(extract_bounding_boxes(
                        observation['associations'],
                        observation['concept'],
                        observation['uuid']
                    )),
                    'type': 'observation'
                }
                self.add_item(observation_metadata, parent=current)
