"""
HTTP request functions for interacting with M3 endpoints.
"""

import json
from typing import Optional

import requests
import requests.auth
from PyQt6.QtGui import QPixmap

from vars_localize.util import endpoints, utils

KB_CONCEPTS = None
KB_PARTS = None

DEFAULT_SESSION = requests.Session()
ANNO_SESSION = requests.Session()


class BasicJWTAuth(requests.auth.AuthBase):
    """
    Basic JWT authentication for requests.
    """

    def __init__(self, token: str):
        self.token = token

    def __call__(self, r):
        r.headers["Authorization"] = "BEARER " + self.token
        return r


def configure_anno_session():
    jwt_auth(ANNO_SESSION, endpoints.Annosaurus)


def requires_auth(session: requests.Session):
    """
    Decorator for REST calls to require authentication
    :return: Wrapped function
    """

    def wrapper(f):
        def f_proxy(*args, **kwargs):
            if session.auth is None:
                raise Exception("Session must be authenticated")
            return f(*args, **kwargs)

        return f_proxy

    return wrapper


def check_connection(m3_url: str) -> bool:
    """
    Check the connection by sending a GET request to the prod_site endpoint
    :return: Connection OK
    """
    try:
        r = DEFAULT_SESSION.get(m3_url, timeout=3)
        return r.status_code == 200
    except requests.HTTPError as e:
        utils.log(f"Connection check failed: {e}", level=2)
        return False


def get_imaged_moment_uuids(concept: str):
    """
    Get all imaged moment uuids with valid .png images for a specific concept
    :param concept: Concept to query
    :return: List of imaged moment uuids
    """
    response = ANNO_SESSION.get(
        endpoints.Annosaurus.IMAGED_MOMENTS_BY_CONCEPT + "/" + concept
    )
    return response.json()


def get_imaged_moment(imaged_moment_uuid: str):
    """
    Get data associated with an imaged moment uuid
    :param imaged_moment_uuid: UUID of imaged moment
    :return: JSON object of imaged moment
    """
    response = ANNO_SESSION.get(
        endpoints.Annosaurus.IMAGED_MOMENT + "/" + imaged_moment_uuid
    )
    response_json = response.json()
    return response_json


def get_all_concepts():
    """
    Return a list of all concepts in the knowledge base
    :return: List of concept strings
    """
    global KB_CONCEPTS
    if not KB_CONCEPTS:
        response = DEFAULT_SESSION.get(endpoints.VARSKBServer.ALL_CONCEPTS)

        KB_CONCEPTS = response.json()

    return KB_CONCEPTS


def get_all_parts():
    """
    Return a list of all concept parts
    :return: List of part strings
    """
    global KB_PARTS
    if not KB_PARTS:
        response = DEFAULT_SESSION.get(endpoints.VARSKBServer.ALL_PARTS)

        KB_PARTS = [el["name"] for el in response.json()]

    return KB_PARTS


def concept_count(concept: str):
    """
    Use the fast servlet to get a count of observations with valid image references
    :param concept: Concept to use
    :return: int number of observations with valid image references
    """
    try:
        response = ANNO_SESSION.get(endpoints.Annosaurus.IMAGE_COUNT + "/" + concept)
        response.raise_for_status()

        response_json = response.json()
        return int(response_json["count"])
    except Exception as e:
        utils.log("Concept count failed.", level=2)
        utils.log(e, level=2)
        return 0


def jwt_auth(session: requests.Session, endpoint: endpoints.ConfigEndpoint) -> bool:
    """
    Authenticate a session with basic JWT
    :return: Success or failure
    """
    try:
        response = session.post(
            endpoint.AUTH,
            headers={"Authorization": "APIKEY {}".format(endpoint.SECRET)},
        )
        response.raise_for_status()

        token = response.json()["access_token"]
        session.auth = BasicJWTAuth(token)

        return True
    except Exception as e:
        utils.log("Authentication failed.", level=2)
        utils.log(e, level=2)
        return False


@requires_auth(ANNO_SESSION)
def create_observation(
    video_reference_uuid,
    concept,
    observer,
    timecode=None,
    elapsed_time_millis=None,
    recorded_timestamp=None,
) -> Optional[dict]:
    """
    Create an observation. One of timecode, elapsed_time, or recorded_timestamp is required as an index
    :param video_reference_uuid: Video reference UUID
    :param concept: Concept observed
    :param observer: Observer tag
    :param timecode: Optional timecode of observation
    :param elapsed_time_millis: Optional elapsed time of observation
    :param recorded_timestamp: Optional recorded timestamp of observation
    :return: HTTP response JSON if success, else None
    """
    request_data = {
        "video_reference_uuid": video_reference_uuid,
        "concept": concept,
        "observer": observer,
        "activity": "localize",
        "group": "ROV:training-set",
    }

    if not (timecode or elapsed_time_millis or recorded_timestamp):
        utils.log(
            "No observation index provided. Observation creation failed.", level=2
        )
        return

    if timecode:
        request_data["timecode"] = timecode
    if elapsed_time_millis:
        request_data["elapsed_time_millis"] = int(elapsed_time_millis)
    if recorded_timestamp:
        request_data["recorded_timestamp"] = recorded_timestamp

    try:
        response = ANNO_SESSION.post(
            endpoints.Annosaurus.OBSERVATION, data=request_data
        )
        response.raise_for_status()

        return response.json()
    except Exception as e:
        utils.log("Observation creation failed.", level=2)
        utils.log(e, level=2)


@requires_auth(ANNO_SESSION)
def delete_observation(observation_uuid: str) -> Optional[dict]:
    """
    Delete an observation in VARS
    :param observation_uuid: Observation UUID
    :return: HTTP response if success, else None
    """
    try:
        response = ANNO_SESSION.delete(
            endpoints.Annosaurus.DELETE_OBSERVATION + "/" + observation_uuid
        )
        response.raise_for_status()

        return response
    except Exception as e:
        utils.log("Observation deletion failed.", level=2)
        utils.log(e, level=2)


@requires_auth(ANNO_SESSION)
def create_box(
    box_json, observation_uuid: str, to_concept: Optional[str] = None
) -> Optional[dict]:
    """
    Creates an association for a box in VARS
    :param box_json: JSON of bounding box data
    :param observation_uuid: Observation UUID
    :param to_concept: Optional concept part
    :return: HTTP response JSON if success, else None
    """
    request_data = {
        "observation_uuid": observation_uuid,
        "link_name": "bounding box",
        "link_value": json.dumps(box_json),
        "mime_type": "application/json",
    }

    if to_concept is not None:
        request_data["to_concept"] = to_concept

    try:
        response = ANNO_SESSION.post(
            endpoints.Annosaurus.ASSOCIATION,
            data=request_data,
        )
        response.raise_for_status()

        return response.json()
    except Exception as e:
        utils.log("Box creation failed.", level=2)
        utils.log(e, level=2)


@requires_auth(ANNO_SESSION)
def modify_box(
    box_json, observation_uuid: str, association_uuid: str
) -> Optional[dict]:
    """
    Modifies a box with a given association_uuid
    :param box_json: JSON of bounding box data
    :param observation_uuid: Observation UUID
    :param association_uuid: UUID in associations table to modify
    :param retry: Retry after authentication failure
    :return: HTTP response JSON if success, else None
    """
    request_data = {
        "observation_uuid": observation_uuid,
        "link_name": "bounding box",
        "link_value": json.dumps(box_json),
        "mime_type": "application/json",
    }

    try:
        response = ANNO_SESSION.put(
            endpoints.Annosaurus.ASSOCIATION + "/" + association_uuid, data=request_data
        )
        response.raise_for_status()

        return response.json()
    except Exception as e:
        utils.log("Box modification failed.", level=2)
        utils.log(e, level=2)


@requires_auth(ANNO_SESSION)
def delete_box(association_uuid: str):
    """
    Deletes a box with a given association_uuid
    :param association_uuid: UUID in associations table to delete
    :param retry: Retry after authentication failure
    :return: HTTP response if success, else None
    """
    try:
        response = ANNO_SESSION.delete(
            endpoints.Annosaurus.ASSOCIATION + "/" + association_uuid
        )
        response.raise_for_status()

        return response
    except Exception as e:
        utils.log("Box deletion failed.", level=2)
        utils.log(e, level=2)


def fetch_image(url: str) -> Optional[QPixmap]:
    """
    Fetch an image from a URL and represent it as a pixmap
    :param url: URL of image
    :return: Pixmap item representing image if valid url, else None
    """
    try:
        response = DEFAULT_SESSION.get(url)
        response.raise_for_status()

        pixmap = QPixmap()
        pixmap.loadFromData(response.content)
        return pixmap
    except Exception:
        utils.log("Could not fetch image at {}".format(url), level=1)


def get_all_users() -> list:
    """
    Get a list of all available VARS users
    :return: list of all VARS users
    """
    response = DEFAULT_SESSION.get(endpoints.VARSUserServer.ALL_USERS)
    response_json = response.json()
    return response_json


def get_other_videos(video_reference_uuid: str) -> list:
    """
    Get a list of all video references concurrent to the provided video reference UUID
    :param video_reference_uuid: Base video reference UUID
    :return: List of all concurrent video reference UUIDs
    """
    response = DEFAULT_SESSION.get(
        endpoints.VampireSquid.CONCURRENT_VIDEOS + "/" + video_reference_uuid
    )
    response_json = response.json()
    return [ref["video_reference_uuid"] for ref in response_json]


@requires_auth(ANNO_SESSION)
def rename_observation(observation_uuid: str, new_concept: str, observer: str):
    """
    Rename an observation
    :param observation_uuid: Observation UUID to rename
    :param new_concept: New concept
    :param observer: Observer to update
    :param retry: Retry after authentication failure
    :return: HTTP response if success, else None
    """
    request_data = {"concept": new_concept, "observer": observer}

    try:
        response = ANNO_SESSION.put(
            endpoints.Annosaurus.OBSERVATION + "/" + observation_uuid, data=request_data
        )
        response.raise_for_status()

        return response.json()
    except Exception as e:
        utils.log("Concept rename failed.", level=2)
        utils.log(e, level=2)


def get_video_data(video_reference_uuid: str):
    """
    Get data for a particular video reference UUID
    :param video_reference_uuid: Video reference UUID to lookup
    :return: JSON data if valid UUID, else None
    """
    try:
        response = DEFAULT_SESSION.get(
            endpoints.VampireSquid.VIDEO_DATA + "/" + video_reference_uuid
        )
        response.raise_for_status()

        return response.json()
    except Exception as e:
        utils.log(
            "Could not fetch video data for {}".format(video_reference_uuid), level=1
        )
        utils.log(e, level=1)


def get_imaged_moments_by_image_reference(image_reference_uuid: str):
    """
    Get imaged moments using a particular image reference UUID
    :param image_reference_uuid: Image reference UUID
    :return : JSON data if valid UUID, else None
    """
    try:
        response = DEFAULT_SESSION.get(
            endpoints.Annosaurus.IMAGED_MOMENTS_BY_IMAGE_REFERENCE
            + "/"
            + image_reference_uuid
        )
        response.raise_for_status()

        return response.json()
    except Exception as e:
        utils.log(
            "Could not fetch imaged moment data for image reference {}".format(
                image_reference_uuid
            ),
            level=1,
        )
        utils.log(e, level=1)


def get_annotations_by_video_refernce(video_reference_uuid: str):
    """
    Get annotations for a particular video reference UUID
    :param video_reference_uuid: Video reference UUID
    :return: JSON data if valid UUID, else None
    """
    try:
        response = DEFAULT_SESSION.get(
            endpoints.Annosaurus.ANNOTATIONS_BY_VIDEO_REFERENCE
            + "/"
            + video_reference_uuid,
            params={"data": True},
        )
        response.raise_for_status()

        return response.json()
    except Exception as e:
        utils.log(
            "Could not fetch annotation data for video reference {}".format(
                video_reference_uuid
            ),
            level=1,
        )
        utils.log(e, level=1)


def get_video_by_video_reference_uuid(video_reference_uuid: str):
    """
    Get data for a video by a given video reference UUID
    :param video_reference_uuid: Video reference UUID
    :type video_reference_uuid: str
    :return: JSON data if valid UUID, else None
    """
    try:
        response = DEFAULT_SESSION.get(
            endpoints.VampireSquid.VIDEO_BY_VIDEO_REFERENCE_UUID
            + "/"
            + video_reference_uuid
        )
        response.raise_for_status()

        response_parsed = response.json()

        # Workaround for https://github.com/mbari-org/vampire-squid/issues/10
        if isinstance(response_parsed, list):
            return response_parsed[0]

        return response_parsed
    except Exception as e:
        utils.log(
            "Could not fetch video data for video reference {}".format(
                video_reference_uuid
            ),
            level=1,
        )
        utils.log(e, level=1)
