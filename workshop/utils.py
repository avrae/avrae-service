import datetime

import pymongo
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


def _relevance_based_explore(tags: list, q: str, page: int):
    """Returns a list of ids for a relevance-based explore query."""
    if not q:
        return _popularity_based_explore(7, tags, q, page)

    query = [
        {"multi_match": {
            "query": q,
            "fields": ["name^3", "description"]  # search for the query in name, desc - name 3x more important
        }}
    ]

    if tags:
        query.append({"terms": {"tags": tags}})

    resp = requests.get(
        f"{config.ELASTICSEARCH_ENDPOINT}/workshop_collections/_search",
        json={
            "query": {"bool": {
                "filter": {"term": {"publish_state": PublicationState.PUBLISHED.value}},
                "must": query
            }},
            "sort": ["_score"],
            "from": RESULTS_PER_PAGE * (page - 1),
            "size": RESULTS_PER_PAGE,
            "_source": False
        }
    )
    resp.raise_for_status()
    result = resp.json()

    return [str(sr['_id']) for sr in result['hits']['hits']]


def _metric_based_explore(metric: str, tags: list, q: str, page: int):
    """Returns a list of ids for a time-based explore query."""

    query = {"publish_state": PublicationState.PUBLISHED.value}

    if tags:
        query["tags"] = {"$all": tags}

    if q:
        # https://docs.mongodb.com/manual/text-search/
        query["$text"] = {"$search": q}

    cursor = current_app.mdb.workshop_collections.find(query)

    cursor.sort(metric, pymongo.DESCENDING)
    cursor.limit(RESULTS_PER_PAGE)  # 50 results/page
    cursor.skip(RESULTS_PER_PAGE * (page - 1))  # seek to page

    return [str(coll['_id']) for coll in cursor]


def _popularity_based_explore(days: int, tags: list, q: str, page: int):
    """Returns a list of ids for a popularity-based explore query."""
    pass
