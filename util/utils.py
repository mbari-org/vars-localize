# utils.py (vars-localize)
from ui.BoundingBox import SourceBoundingBox

import configparser
from functools import reduce
import json
import os
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

GLOBAL_CONFIG = None
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
    part_len = len(string) // n
    parts = [string[i * part_len:(i + 1) * part_len] for i in range(n - 1)]
    parts.append(string[(n - 1) * part_len:])

    return tuple([
        reduce(lambda a, b: a * b % maxval, [ord(letter) for letter in sorted(part.replace(' ', ''))]) % maxval
        for part in parts
    ])


def get_property(category, prop):
    """
    Gets a property from a given category from the config file, if it exists
    :param category: Category to pull from
    :param prop: Property to fetch
    :return: Requested property value if exists, else None
    """
    global GLOBAL_CONFIG
    if not GLOBAL_CONFIG:
        GLOBAL_CONFIG = configparser.ConfigParser()
        GLOBAL_CONFIG.read('config/config.ini')
    if category in GLOBAL_CONFIG:
        if prop in GLOBAL_CONFIG[category]:
            return GLOBAL_CONFIG[category][prop]
    return None


def get_api_key():
    """
    Returns the API key for authorization from 'config/api_key.txt'
    :return: API key string
    """
    api_key_file = open('config/api_key.txt', 'r')
    key = api_key_file.readlines()[0].strip()
    api_key_file.close()
    return key


def cache_token(token: str):
    """
    Caches a token to the 'cache/token.json'
    :param token: JWT access token JSON string
    :return: None
    """
    if not os.path.exists('cache'):
        os.makedirs('cache')
    with open('cache/token.json', 'w') as f:
        f.write(token)


def get_token():
    """
    Gets the JWT access token, if it exists
    :return: JWT access token string if exists, else None
    """
    if not os.path.exists('cache/token.json'):
        return None
    with open('cache/token.json', 'r') as f:
        access_token = json.loads(f.read())['access_token']
        return access_token


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
        if im_ref_filter and box_json['image_reference_uuid'] == im_ref_filter:
            yield SourceBoundingBox(  # Create source box
                box_json,
                concept,
                box_json['observer'],
                box_json['strength'],
                observation_uuid=observation_uuid,
                association_uuid=association['uuid'],
                part=association['to_concept']
            )


def get_observer_confidence(observer: str):
    """
    Get the confidence value given a particular observer.
    :param observer: Observer to lookup
    :return: Confidence value (any)
    """
    with open('config/strength_map.json', 'r') as f:
        json_obj = json.load(f)
        for conf_rank in json_obj.keys():
            if conf_rank != 'default' and observer in json_obj[conf_rank]:
                return conf_rank
        return json_obj['default']


def split_comma_list(comma_str: str):
    """
    Split a comma-separated list of values, stripping whitespace
    """
    return [item.strip() for item in comma_str.split(',')]
