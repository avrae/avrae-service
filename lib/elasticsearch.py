import requests

import config


def init():
    """Various things to run on application init."""
    if not config.ELASTICSEARCH_ENDPOINT:
        return
    ensure_indices_exist()


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
