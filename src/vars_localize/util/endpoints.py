"""
M3 endpoints configured by Raziel.

You must be in the MBARI network before configuring this module with configure().
"""

import requests
from base64 import b64encode

DEFAULT_M3_URL = "https://m3.shore.mbari.org"  # The URL of the M3 microservices server

ENDPOINTS = None


def configure(m3_url: str, username: str, password: str):
    """
    Authenticate with Raziel and configure the M3 endpoints.
    """
    # Encode the username and password
    user_pass_base64 = "Basic " + b64encode(
        "{}:{}".format(username, password).encode("utf-8")
    ).decode("utf-8")

    config_url = m3_url.rstrip("/") + "/config"

    # Attempt to authenticate with Raziel
    res = requests.post(
        config_url + "/auth", headers={"Authorization": user_pass_base64}
    )
    if res.status_code != 200:
        raise Exception(
            "Failed to authenticate with Raziel (code {}): {}".format(
                res.status_code, res.json()["message"]
            )
        )

    # Get the token from the response
    token = res.json()["accessToken"]

    # Get the endpoints from Raziel
    global ENDPOINTS
    ENDPOINTS = {
        endpoint["name"]: endpoint
        for endpoint in requests.get(
            config_url + "/endpoints", headers={"Authorization": "Bearer " + token}
        ).json()
    }


class ConfigEndpoint(type):
    """
    Metaclass to namespace endpoint constants with a given Raziel configuration name.
    """

    NAME = ""
    AUTH = "/auth"

    def __getattribute__(cls, key):
        name = super().__getattribute__("NAME")
        if key == "NAME":
            return name

        if ENDPOINTS is None:
            raise Exception("You must call configure() before accessing endpoints.")
        elif name not in ENDPOINTS:
            raise Exception("No endpoint named {}".format(name))

        if key == "URL":
            return ENDPOINTS[name]["url"]
        elif key == "SECRET":
            return ENDPOINTS[name]["secret"]
        elif key == "TIMEOUT_MILLIS":
            return ENDPOINTS[name]["timeoutMillis"]
        elif key == "PROXY_PATH":
            return ENDPOINTS[name]["proxyPath"]

        attr = super().__getattribute__(key)
        return ENDPOINTS[name]["url"] + attr


class Annosaurus(metaclass=ConfigEndpoint):
    NAME = "annosaurus"

    OBSERVATION = "/annotations"
    ASSOCIATION = "/associations"
    FAST_SEARCH = "/fast/concept/images"
    IMAGE_COUNT = "/observations/concept/images/count"
    IMAGED_MOMENT = "/imagedmoments"
    WINDOW_REQUEST = "/imagedmoments/windowrequest"
    ALL_CONCEPTS_USED = "/observations/concepts"
    DELETE_OBSERVATION = "/observations"
    IMAGED_MOMENTS_BY_CONCEPT = "/fast/imagedmoments/concept/images"
    IMAGED_MOMENTS_BY_IMAGE_REFERENCE = "/annotations/imagereference"
    ANNOTATIONS_BY_VIDEO_REFERENCE = "/fast/videoreference"


class VARSKBServer(metaclass=ConfigEndpoint):
    NAME = "vars-kb-server"

    ALL_CONCEPTS = "/concept"
    ALL_PARTS = "/phylogeny/taxa/organism part"


class VARSUserServer(metaclass=ConfigEndpoint):
    NAME = "vars-user-server"

    ALL_USERS = "/users"


class VampireSquid(metaclass=ConfigEndpoint):
    NAME = "vampire-squid"

    CONCURRENT_VIDEOS = "/media/concurrent"
    VIDEO_DATA = "/videoreferences"
    VIDEO_BY_VIDEO_REFERENCE_UUID = "/videos/videoreference"
