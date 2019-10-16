# EntryTree.py (vars-localize)
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem
from util.requests import get_imaged_moment_uuids, get_imaged_moment, get_other_videos, get_windowed_moments
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

    def update(self):
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
            'type': 'imaged_moment',
            'status': 'unknown'
        } for uuid in self.loaded_uuids[offset:offset+limit]]

        self.clear()
        if not results:
            self.add_item(None, self)
        for result in results:
            item = self.add_item(result)
            self.load_imaged_moment_entry(item)  # Fetch imaged moment observation/metadata

    def load_imaged_moment_entry(self, entry: EntryTreeItem):
        """
        Load imaged moment entry data into tree.
        :param entry: Imaged moment entry item
        :return: None
        """
        meta = entry.metadata
        imaged_moment = get_imaged_moment(meta['uuid'])

        meta['video_reference_uuid'] = imaged_moment['video_reference_uuid']
        # other_videos = get_other_videos(meta['video_reference_uuid'])
        all_moments = get_windowed_moments(
            [meta['video_reference_uuid']], meta['uuid'],
            self.window().search_panel.time_window.value()
        )

        # Get indices
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

        # observations = imaged_moment['observations']
        observations = []
        for moment in all_moments:
            for obs in moment['observations']:
                observations.append(obs)
        localized = 0
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
            if observation_metadata['boxes']:  # This observation has been localized
                localized += 1
            observation_metadata['status'] = len(observation_metadata['boxes'])
            self.add_item(observation_metadata, parent=entry)

        entry.metadata['status'] = '{}/{}'.format(localized, len(observations))
        entry.update()

    def item_changed(self, current: EntryTreeItem, previous: EntryTreeItem):
        """
        Slot for item selection change
        :param current: Current item
        :param previous: Previous item
        :return: None
        """
        if not current or not current.metadata:
            return
        if current.metadata['type'] == 'imaged_moment' and not current.childCount():
            self.load_imaged_moment(current)
