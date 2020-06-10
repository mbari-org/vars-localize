# requests.py (vars-localize)
import json

import util.utils

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

HTTP request functions for interacting with M3 endpoints.

@author: __author__
@status: __status__
@license: __license__
'''
import requests
from PyQt5.QtGui import QPixmap

concepts = None


def auth_retry(fail_msg):
    """
    Decorator for REST calls with auth retry
    :param fail_msg: Message to show on fail
    :return: Wrapped function
    """
    def wrap_func(func):
        def retry_func(*args, retry=True, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if retry:
                    auth()
                    return retry_func(*args, retry=False, **kwargs)
                else:
                    util.utils.log(fail_msg, level=2)
                    util.utils.log(e, level=2)
        return retry_func
    return wrap_func


def check_connection():
    """
    Check the connection by sending a GET request to the prod_site endpoint
    :return: Connection OK
    """
    r = requests.get(
        util.utils.get_property('endpoints', 'prod_site')
    )
    return r.status_code == 200


def get_imaged_moment_uuids(concept: str):
    """
    Get all imaged moment uuids with valid .png images for a specific concept
    :param concept: Concept to query
    :return: List of imaged moment uuids
    """
    response = requests.get(
        util.utils.get_property('endpoints', 'imaged_moments_by_concept') + '/{}'.format(concept)
    )
    return response.json()


def get_imaged_moment(imaged_moment_uuid: str):
    """
    Get data associated with an imaged moment uuid
    :param imaged_moment_uuid: UUID of imaged moment
    :return: JSON object of imaged moment
    """
    response = requests.get(
        util.utils.get_property('endpoints', 'imaged_moment') + '/{}'.format(imaged_moment_uuid)
    )
    response_json = response.json()
    return response_json


def get_all_concepts():
    """
    Return a list of all concepts used
    :return: List of concept strings
    """
    global concepts
    if not concepts:
        all_concepts_endpoint = util.utils.get_property('endpoints', 'all_concepts')
        response = requests.get(all_concepts_endpoint)
        concepts = response.json()  # List of concept strings
    return concepts


def concept_count(concept: str):
    """
    Use the fast servlet to get a count of observations with valid image references
    :param concept: Concept to use
    :return: int number of observations with valid image references
    """
    try:
        response = requests.get(
            util.utils.get_property('endpoints', 'image_count') + '/{}'.format(concept)
        )
        response_json = response.json()
        return int(response_json['count'])
    except Exception as e:
        util.utils.log('Concept count failed.', level=2)
        util.utils.log(e, level=2)
        return 0


def auth():
    """
    Authenticate, generate new JWT access token and cache it
    :return: JWT access token
    """
    try:
        response = requests.post(
            util.utils.get_property('endpoints', 'auth'),
            headers={
                'Authorization': 'APIKEY {}'.format(util.utils.get_api_key())
            }
        )
        util.utils.cache_token(response.content.decode())
        return response.json()['access_token']
    except Exception as e:
        util.utils.log('Authentication failed.', level=2)
        util.utils.log(e, level=2)
        return None


def check_auth():
    """
    Check cached authentication token is valid, fetch new if not
    :return: Token str
    """
    token = util.utils.get_token()
    if not token:
        token = auth()
    if not token:
        raise ValueError('Bad API key! Check it in src/main/resources/base/config/api_key.txt')
    else:
        return token


def create_observation(video_reference_uuid, concept, observer, timecode=None, elapsed_time_millis=None, recorded_timestamp=None,
                       retry=True):
    """
    Create an observation. One of timecode, elapsed_time, or recorded_date is required as an index
    :param video_reference_uuid: Video reference UUID
    :param concept: Concept observed
    :param observer: Observer tag
    :param timecode: Optional timecode of observation
    :param elapsed_time_millis: Optional elapsed time of observation
    :param recorded_timestamp: Optional recorded timestamp of observation
    :param retry: Retry after authentication failure
    :return: HTTP response JSON if success, else None
    """
    request_data = {
        'video_reference_uuid': video_reference_uuid,
        'concept': concept,
        'observer': observer,
    }

    if not (timecode or elapsed_time_millis or recorded_timestamp):
        util.utils.log('No observation index provided. Observation creation failed.', level=2)
        return

    if timecode:
        request_data['timecode'] = timecode
    if elapsed_time_millis:
        request_data['elapsed_time_millis'] = int(elapsed_time_millis)
    if recorded_timestamp:
        request_data['recorded_timestamp'] = recorded_timestamp

    token = check_auth()

    try:
        response = requests.post(
            util.utils.get_property('endpoints', 'observation'),
            data=request_data,
            headers={
                'Authorization': 'BEARER {}'.format(token)
            }
        )
        return response.json()
    except Exception as e:
        if retry:
            auth()
            return create_observation(video_reference_uuid, concept, observer, timecode, elapsed_time_millis, recorded_timestamp,
                                      retry=False)
        else:
            print('Observation creation failed.')
            print(e)


def delete_observation(observation_uuid: str, retry=True):
    """
    Delete an observation in VARS
    :param observation_uuid: Observation UUID
    :param retry: Retry after authentication failure
    :return: HTTP response JSON if success, else None
    """
    token = check_auth()

    try:
        response = requests.delete(
            util.utils.get_property('endpoints', 'delete_observation') + '/{}'.format(observation_uuid),
            headers={
                'Authorization': 'BEARER {}'.format(token)
            }
        )
        return response
    except Exception as e:
        if retry:
            auth()
            return delete_observation(observation_uuid, retry=False)
        else:
            util.utils.log('Observation deletion failed.', level=2)
            util.utils.log(e, level=2)


def create_box(box_json, observation_uuid: str, retry=True):
    """
    Creates an association for a box in VARS
    :param box_json: JSON of bounding box data
    :param observation_uuid: Observation UUID
    :param retry: Retry after authentication failure
    :return: HTTP response JSON if success, else None
    """
    request_data = {
        'observation_uuid': observation_uuid,
        'link_name': 'bounding box',
        'link_value': json.dumps(box_json),
        'mime_type': 'application/json'
    }

    token = check_auth()

    try:
        response = requests.post(
            util.utils.get_property('endpoints', 'assoc'),
            data=request_data,
            headers={
                'Authorization': 'BEARER {}'.format(token)
            }
        )
        return response.json()
    except Exception as e:
        if retry:
            auth()
            return create_box(box_json, observation_uuid, retry=False)
        else:
            util.utils.log('Box creation failed.', level=2)
            util.utils.log(e, level=2)


def modify_box(box_json, observation_uuid: str, association_uuid: str, retry=True):
    """
    Modifies a box with a given association_uuid
    :param box_json: JSON of bounding box data
    :param observation_uuid: Observation UUID
    :param association_uuid: UUID in associations table to modify
    :param retry: Retry after authentication failure
    :return: HTTP response JSON if success, else None
    """
    token = check_auth()

    request_data = {
        'observation_uuid': observation_uuid,
        'link_name': 'bounding box',
        'link_value': json.dumps(box_json),
        'mime_type': 'application/json'
    }

    try:
        response = requests.put(
            util.utils.get_property('endpoints', 'assoc') + '/{}'.format(association_uuid),
            data=request_data,
            headers={
                'Authorization': 'BEARER {}'.format(token)
            }
        )
        return response.json()
    except Exception as e:
        if retry:
            auth()
            return modify_box(box_json, observation_uuid, association_uuid, retry=False)
        else:
            util.utils.log('Box modification failed.', level=2)
            util.utils.log(e, level=2)


def delete_box(association_uuid: str, retry=True):
    """
    Deletes a box with a given association_uuid
    :param association_uuid: UUID in associations table to delete
    :param retry: Retry after authentication failure
    :return: HTTP response if success, else None
    """
    token = check_auth()

    try:
        response = requests.delete(
            util.utils.get_property('endpoints', 'assoc') + '/{}'.format(association_uuid),
            headers={
                'Authorization': 'BEARER {}'.format(token)
            }
        )
        return response
    except Exception as e:
        if retry:
            auth()
            return delete_box(association_uuid, retry=False)
        else:
            util.utils.log('Box deletion failed.', level=2)
            util.utils.log(e, level=2)


def fetch_image(url: str) -> QPixmap:
    """
    Fetch an image from a URL and represent it as a pixmap
    :param url: URL of image
    :return: Pixmap item representing image if valid url, else None
    """
    pixmap = QPixmap()
    try:
        image_contents = requests.get(url).content
        pixmap.loadFromData(image_contents)
    except Exception as e:
        util.utils.log('Could not fetch image at {}'.format(url), level=1)
        pixmap = None
    return pixmap


def get_all_users() -> list:
    """
    Get a list of all available VARS users
    :return: list of all VARS usernames
    """
    response = requests.get(
        util.utils.get_property('endpoints', 'users')
    )
    response_json = response.json()
    usernames = []
    for user_struct in response_json:
        usernames.append(user_struct['username'])
    return usernames


def get_other_videos(video_reference_uuid: str) -> list:
    """
    Get a list of all video references concurrent to the provided video reference UUID
    :param video_reference_uuid: Base video reference UUID
    :return: List of all concurrent video reference UUIDs
    """
    response = requests.get(
        util.utils.get_property('endpoints', 'concurrent_videos') + '/{}'.format(video_reference_uuid)
    )
    response_json = response.json()
    return [ref['video_reference_uuid'] for ref in response_json]


def get_windowed_moments(video_reference_uuids: list, imaged_moment_uuid: str, time_window: int):
    """
    Get a list of imaged moment data within specified time window in the given videos corresponding to a particular imaged moment.
    :param video_reference_uuids: List of video reference UUIDs to fetch from
    :param imaged_moment_uuid: Reference imaged moment UUID
    :param time_window: Time window, in milliseconds
    :return: List of imaged moment data
    """
    request_data = {
        'video_reference_uuids': video_reference_uuids,
        'imaged_moment_uuid': imaged_moment_uuid,
        'window': time_window
    }

    response = requests.post(
        util.utils.get_property('endpoints', 'window_request'),
        data=json.dumps(request_data),
        headers={
            'Content-Type': 'application/json'
        }
    )
    response_json = response.json()
    return response_json


def modify_concept(observation_uuid: str, new_concept: str, observer: str, retry=True):
    """
    Rename an observation
    :param observation_uuid: Observation UUID to rename
    :param new_concept: New concept
    :param observer: Observer to update
    :param retry: Retry after authentication failure
    :return: HTTP response if success, else None
    """
    token = check_auth()

    request_data = {
        'concept': new_concept,
        'observer': observer
    }

    try:
        response = requests.put(
            util.utils.get_property('endpoints', 'observation') + '/{}'.format(observation_uuid),
            data=request_data,
            headers={
                'Authorization': 'BEARER {}'.format(token)
            }
        )
        return response.json()
    except Exception as e:
        if retry:
            auth()
            return modify_concept(observation_uuid, new_concept, observer, retry=False)
        else:
            util.utils.log('Observation renaming failed.', level=2)
            util.utils.log(e, level=2)
