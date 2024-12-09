"""
Utility functions for the application.
"""

from vars_localize.ui.BoundingBox import SourceBoundingBox

from functools import reduce
import json
import urllib.parse


LOG_LEVELS = {0: "INFO", 1: "WARNING", 2: "ERROR"}


def log(message, level=0):
    """
    Log a message to stdout
    :param message: Message to log
    :param level: Log level (see LOG_LEVELS)
    :return: None
    """
    if level not in LOG_LEVELS:
        raise ValueError("Bad log level.")
    print("[{}] {}".format(LOG_LEVELS[level], message))


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
    parts = [string[i * part_len : (i + 1) * part_len] for i in range(n - 1)]
    parts.append(string[(n - 1) * part_len :])

    return tuple(
        [
            reduce(
                lambda a, b: a * b % maxval,
                [ord(letter) for letter in sorted(part.replace(" ", ""))],
            )
            % maxval
            for part in parts
        ]
    )


def encode_form(json_obj):
    """
    Encodes a JSON object to comply with the 'x-www-form-urlencoded' format
    :param json_obj: JSON object
    :return: URL encoded form string
    """
    return bytearray(urllib.parse.urlencode(json_obj).replace("%27", "%22"), "utf-8")


def extract_bounding_boxes(associations: list, concept: str, observation_uuid: str):
    """
    Yield source bounding box objects from a JSON list of associations
    :param associations: JSON list of associations
    :param concept: Concept to attach to each source bounding box
    :param observation_uuid: Observation UUID to attach to box
    :return: Generator object for bounding boxes
    """
    for association in associations:  # Generate source bounding boxes
        if association["link_name"] != "bounding box":
            continue

        box_json = json.loads(association["link_value"])
        yield SourceBoundingBox(  # Create source box
            box_json,
            concept,
            observer=box_json.get("observer", None),
            observation_uuid=observation_uuid,
            association_uuid=association["uuid"],
            part=association["to_concept"],
        )


def split_comma_list(comma_str: str):
    """
    Split a comma-separated list of values, stripping whitespace
    """
    return [item.strip() for item in comma_str.split(",")]
