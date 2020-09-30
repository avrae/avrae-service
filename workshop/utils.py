import datetime

import requests
from flask import current_app

import config
from lib import discord
from lib.discord import UserInfo
from workshop.collection import PublicationState
from workshop.errors import NeedsServerAliaser

ALIASER_ROLE_NAMES = ("server aliaser", "dragonspeaker")
ALIASER_PERMISSION = 8  # administrator
RESULTS_PER_PAGE = 48


def guild_permissions_check(user: UserInfo, guild_id: int):
    """Checks whether the given user has permissions to edit server aliases on the given guild."""

    # 1: is the user *in* the guild?
    user_guilds = discord.get_current_user_guilds(discord.discord_token_for(user.id))
    the_guild = next((g for g in user_guilds if g['id'] == str(guild_id)), None)
    if the_guild is None:
        raise NeedsServerAliaser("You are not in this server.")

    # 2: does the user have Administrator in the guild?
    if the_guild['owner'] or (the_guild['permissions'] & ALIASER_PERMISSION):
        return True

    # 3: does the user have a role in the aliaser role names in the guild?
    try:
        guild_roles = discord.get_guild_roles(guild_id)
    except requests.HTTPError:
        raise NeedsServerAliaser(
            "You do not have permissions to edit server collections - make sure Avrae is in the server you want to "
            "add collections to.")
    role_map = {r['id']: r for r in guild_roles}
    guild_member = discord.get_guild_member(guild_id, user.id)

    for role_id in guild_member['roles']:
        if role_map[role_id]['name'].lower() in ALIASER_ROLE_NAMES:
            return True

    raise NeedsServerAliaser("You do not have permissions to edit server collections - either Administrator Discord "
                             "permissions or a role named \"Server Aliaser\" is required.")


def explore_collections(order: str = 'popular-1w', tags: list = None, q: str = None, page: int = 1):
    """Returns a list of ids (str) of collections that match the given search parameters."""
    if page < 1:
        raise ValueError("page must be at least 1")
    if tags is not None:
        if not isinstance(tags, list):
            raise ValueError("tags must be comma-separated list of tags")
        # check tag validity
        for tag in tags:
            if current_app.mdb.workshop_tags.find_one({"slug": tag}) is None:
                raise ValueError(f"{tag} is an invalid tag")

    if order == "relevance":
        return _relevance_based_explore(tags, q, page)
    elif order == "newest":
        return _metric_based_explore("created_at", tags, q, page)
    elif order == "edittime":
        return _metric_based_explore("last_edited", tags, q, page)
    elif order == "popular-1w":
        return _popularity_based_explore(7, tags, q, page)
    elif order == "popular-1m":
        return _popularity_based_explore(30, tags, q, page)
    elif order == "popular-6m":
        return _popularity_based_explore(180, tags, q, page)
    elif order == "popular-all":
        return _metric_based_explore("num_guild_subscribers", tags, q, page)
    else:
        raise ValueError(f"unknown order: {order}")


def _build_query(tags: list, q: str):
    """Builds a default ES query."""
    query = [{"term": {"publish_state": {"value": PublicationState.PUBLISHED.value}}}]

    if tags:
        query.append({"terms": {"tags": tags}})

    if q:
        query.append({
            "multi_match": {
                "query": q,
                "fields": ["name^3", "description"]  # search for the query in name, desc - name 3x more important
            }
        })
    return query


def _relevance_based_explore(tags: list, q: str, page: int):
    """Returns a list of ids for a relevance-based explore query."""
    if not q:
        return _popularity_based_explore(7, tags, q, page)

    es_query = {
        "query": {
            "bool": {
                "must": _build_query(tags, q)
            }
        },
        "sort": ["_score"],
        "from": RESULTS_PER_PAGE * (page - 1),
        "size": RESULTS_PER_PAGE,
        "_source": False
    }

    resp = requests.get(
        f"{config.ELASTICSEARCH_ENDPOINT}/workshop_collections/_search",
        json=es_query
    )
    resp.raise_for_status()
    result = resp.json()

    return [str(sr['_id']) for sr in result['hits']['hits']]


def _metric_based_explore(metric: str, tags: list, q: str, page: int):
    """Returns a list of ids for a time-based explore query."""

    es_query = {
        "query": {
            "bool": {
                "must": _build_query(tags, q)
            }
        },
        "sort": [{metric: "desc"}],
        "from": RESULTS_PER_PAGE * (page - 1),
        "size": RESULTS_PER_PAGE,
        "_source": False
    }

    resp = requests.get(
        f"{config.ELASTICSEARCH_ENDPOINT}/workshop_collections/_search",
        json=es_query
    )
    resp.raise_for_status()
    result = resp.json()

    return [str(sr['_id']) for sr in result['hits']['hits']]


def _popularity_based_explore(days: int, tags: list, q: str, page: int):
    """Returns a list of ids for a popularity-based explore query."""
    since_ts = datetime.date.today() - datetime.timedelta(days=days)

    es_query = {
        # get docs that are relevant
        "query": {
            "bool": {
                "must": {"terms": {"type": ["subscribe", "server_subscribe", "unsubscribe", "server_unsubscribe"]}},
                "filter": {"range": {"timestamp": {"gte": since_ts.isoformat()}}}
            }
        },
        # bucket by collection id and compute sub score per bucket
        "aggs": {
            "collections": {
                "terms": {
                    "field": "object_id",
                    "size": 512,  # only 512 most popular collections will be shown
                    "order": {"the_score": "desc"}  # sort by sub score
                },
                "aggs": {
                    "the_score": {
                        "sum": {"field": "sub_score", "missing": 0}
                    }
                }
            }
        },
        "size": 0  # only return aggregation results
    }

    # query most popular ids
    resp = requests.get(
        f"{config.ELASTICSEARCH_ENDPOINT}/workshop_events/_search?request_cache=true",
        json=es_query
    )
    resp.raise_for_status()
    result = resp.json()

    sorted_popular_ids = [b['key'] for b in result['aggregations']['collections']['buckets']]

    # filter most popular ids by search/publish state
    es_query = {
        "query": {
            "bool": {
                "filter": _build_query(tags, q),  # filter results by search, tags, publish state
                "must": {"ids": {"values": sorted_popular_ids}}
            }
        },
        "_source": False,
        "size": len(sorted_popular_ids)
    }

    resp = requests.get(
        f"{config.ELASTICSEARCH_ENDPOINT}/workshop_collections/_search",
        json=es_query
    )
    resp.raise_for_status()
    result = resp.json()
    matching_ids = {str(sr['_id']) for sr in result['hits']['hits']}

    # compute final results by discarding nonmatching from popular ids
    final_results = [i for i in sorted_popular_ids if i in matching_ids]
    # skip to page
    from_idx = RESULTS_PER_PAGE * (page - 1)
    to_idx = from_idx + RESULTS_PER_PAGE
    return final_results[from_idx:to_idx]
