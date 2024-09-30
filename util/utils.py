# utils.py (vars-localize)
from ui.BoundingBox import SourceBoundingBox

from functools import reduce
import json
import urllib.parse

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Utility functions for the application.

@author: __author__
@status: __status__
@license: __license__
'''

LOG_LEVELS = {0: 'INFO', 1: 'WARNING', 2: 'ERROR'}


def log(message, level=0):
    """
    Log a message to stdout
    :param message: Message to log
    :param level: Log level (see LOG_LEVELS)
    :return: None
    """
    if level not in LOG_LEVELS:
        raise ValueError('Bad log level.')
    print('[{}] {}'.format(LOG_LEVELS[level], message))


def n_split_hash(string: str, n: int, maxval: int = 255):
    """
    Hashes string into n values using simple algorithm
    :param string: String to hash
    :param n: Number of values
    :param maxval: Bound
    :return: Tuple of int values
    """
    if not string:
        return tuple([127] * n)

    part_len = len(string) // n
    parts = [string[i * part_len:(i + 1) * part_len] for i in range(n - 1)]
    parts.append(string[(n - 1) * part_len:])

    return tuple([
        reduce(lambda a, b: a * b % maxval, [ord(letter) for letter in sorted(part.replace(' ', ''))]) % maxval
        for part in parts
    ])


def encode_form(json_obj):
    """
    Encodes a JSON object to comply with the 'x-www-form-urlencoded' format
    :param json_obj: JSON object
    :return: URL encoded form string
    """
    return bytearray(urllib.parse.urlencode(json_obj).replace('%27', '%22'), 'utf-8')


def extract_bounding_boxes(associations: list, concept: str, observation_uuid: str, im_ref_filter: str = None):
    """
    Yield source bounding box objects from a JSON list of associations
    :param associations: JSON list of associations
    :param concept: Concept to attach to each source bounding box
    :param observation_uuid: Observation UUID to attach to box
    :param im_ref_filter: Optional filter for bounding boxes tied to a particular image reference
    :return: Generator object for bounding boxes
    """
    for association in associations:  # Generate source bounding boxes
        if association['link_name'] != 'bounding box':
            continue

        box_json = json.loads(association['link_value'])
        image_reference_uuid = box_json.get('image_reference_uuid', None)
        if im_ref_filter is not None and image_reference_uuid == im_ref_filter:
            yield SourceBoundingBox(  # Create source box
                box_json,
                concept,
                observer=box_json.get('observer', None),
                observation_uuid=observation_uuid,
                association_uuid=association['uuid'],
                part=association['to_concept']
            )


def split_comma_list(comma_str: str):
    """
    Split a comma-separated list of values, stripping whitespace
    """
    return [item.strip() for item in comma_str.split(',')]
