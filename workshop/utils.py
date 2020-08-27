import datetime

import pymongo
import requests
from flask import current_app

from lib import discord
from lib.discord import UserInfo
from lib.utils import now
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
        return _popularity_based_explore('7d', tags, q, page)
    elif order == "popular-1m":
        return _popularity_based_explore('30d', tags, q, page)
    elif order == "popular-6m":
        return _popularity_based_explore('180d', tags, q, page)
    elif order == "popular-all":
        return _metric_based_explore("num_guild_subscribers", tags, q, page)
    else:
        raise ValueError(f"unknown order: {order}")


def _relevance_based_explore(tags: list, q: str, page: int):
    """Returns a list of ids for a relevance-based explore query."""
    if not q:
        return _popularity_based_explore('7d', tags, q, page)

    query = {"publish_state": PublicationState.PUBLISHED.value,
             "$text": {"$search": q}}

    if tags:
        query["tags"] = {"$all": tags}

    cursor = current_app.mdb.workshop_collections.find(query, {'score': {'$meta': 'textScore'}})

    cursor.sort([('score', {'$meta': 'textScore'})])
    cursor.limit(RESULTS_PER_PAGE)  # 50 results/page
    cursor.skip(RESULTS_PER_PAGE * (page - 1))  # seek to page

    return [str(coll['_id']) for coll in cursor]


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


def _popularity_based_explore(since: str, tags: list, q: str, page: int):
    """Returns a list of ids for a popularity-based explore query."""
    if since not in ('7d', '30d', '180d'):
        raise ValueError("since must be 7d, 30d, or 180d")

    if since == '7d':
        since_ts = now() - datetime.timedelta(days=7)
        cache_coll = "workshop_explore_scores_7d"
    elif since == '30d':
        since_ts = now() - datetime.timedelta(days=30)
        cache_coll = "workshop_explore_scores_30d"
    else:  # 180d
        since_ts = now() - datetime.timedelta(days=180)
        cache_coll = "workshop_explore_scores_180d"

    # do we have cached scores already?
    if (cached := current_app.mdb[cache_coll].find_one()) is None or cached['expire_at'] < now():
        # if not, refresh the cache
        pipeline = [
            # get all sub/unsub docs since time
            {"$match": {"timestamp": {"$gt": since_ts},
                        "type": {"$in": ["subscribe", "unsubscribe", "server_subscribe", "server_unsubscribe"]}}},

            # give all subscribe and server_subscribe docs score: 1
            # and all unsubscribe and server_unsubscribe docs score: -1
            {"$addFields": {"score": {"$cond": {
                "if": {"$in": ["$type", ["subscribe", "server_subscribe"]]},
                "then": 1,
                "else": -1}}}},

            # group all these docs by collection id (object_id)
            # -> {_id: coll_id, score: num_subs}
            {"$group": {"_id": "$object_id", "score": {"$sum": "$score"}}},

            # put the actual collection in the doc
            {"$lookup": {"from": "workshop_collections", "localField": "_id", "foreignField": "_id",
                         "as": "collection"}},

            # filter out deleted and non-published collections
            {"$match": {"collection": {"$size": 1},
                        "collection.0.publish_state": PublicationState.PUBLISHED.value}},

            # add a timestamp for the expiring index (TTL 6h)
            {"$addFields": {"expire_at": now() + datetime.timedelta(hours=6)}},

            # pipe the scores to an expiring collection for further queries
            {"$out": cache_coll}
        ]

        current_app.mdb.analytics_alias_events.aggregate(pipeline)

    # now that the cache is up-to-date, we can query it
    query = {}

    if tags:
        query["collection.0.tags"] = {"$all": tags}

    if q:
        query["$text"] = {"$search": q}

    cursor = current_app.mdb[cache_coll].find(query)

    cursor.sort('score', pymongo.DESCENDING)
    cursor.limit(RESULTS_PER_PAGE)  # 50 results/page
    cursor.skip(RESULTS_PER_PAGE * (page - 1))  # seek to page

    return [str(coll['_id']) for coll in cursor]
