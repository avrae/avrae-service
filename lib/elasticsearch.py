import logging

import requests

import config

log = logging.getLogger(__name__)


def init():
    """Various things to run on application init."""
    if not config.ELASTICSEARCH_ENDPOINT:
        return
    try:
        ensure_indices_exist()
    except requests.ConnectionError as ce:
        log.error(f"Got an error connecting to ElasticSearch: {ce}\n"
                  f"This is fine on dev, but /workshop endpoints may be unhappy")


def ensure_indices_exist():
    # alias workshop indices
    requests.put(
        f"{config.ELASTICSEARCH_ENDPOINT}/workshop_collections",
        json={
            "mappings": {
                "properties": {
                    "name": {"type": "text"},
                    "description": {"type": "text"},
                    "tags": {"type": "keyword"},
                    "publish_state": {"type": "keyword"},
                    "num_subscribers": {"type": "integer"},
                    "num_guild_subscribers": {"type": "integer"},
                    "last_edited": {"type": "date"},
                    "created_at": {"type": "date"}
                }
            }
        }
    )

    requests.put(
        f"{config.ELASTICSEARCH_ENDPOINT}/workshop_events",
        json={
            "mappings": {
                "properties": {
                    "type": {"type": "keyword"},
                    "object_id": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "user_id": {"type": "keyword"},
                    "sub_score": {"type": "integer"}
                }
            }
        }
    )
