import datetime

import pymongo
from flask import current_app

from lib import discord
from lib.discord import UserInfo
from workshop.collection import PublicationState
from workshop.errors import NeedsServerAliaser

ALIASER_ROLE_NAMES = ("server aliaser", "dragonspeaker")
ALIASER_PERMISSION = 8  # administrator


def guild_permissions_check(user: UserInfo, guild_id: int):
    """Checks whether the given user has permissions to edit server aliases on the given guild."""

    # 1: is the user *in* the guild?
    user_guilds = discord.get_current_user_guilds(discord.discord_token_for(user.id))
    the_guild = next((g for g in user_guilds if g['id'] == str(guild_id)), None)
    if the_guild is None:
        raise NeedsServerAliaser("You are not in this server")

    # 2: does the user have Administrator in the guild?
    if the_guild['owner'] or (the_guild['permissions'] & ALIASER_PERMISSION):
        return True

    # 3: does the user have a role in the aliaser role names in the guild?
    guild_roles = discord.get_guild_roles(guild_id)
    role_map = {r['id']: r for r in guild_roles}
    guild_member = discord.get_guild_member(guild_id, user.id)

    for role_id in guild_member['roles']:
        if role_map[role_id]['name'].lower() in ALIASER_ROLE_NAMES:
            return True

    raise NeedsServerAliaser("You do not have permissions to edit server collections - either Administrator Discord"
                             "permissions or a role named \"Server Aliaser\" is required")


def explore_collections(order: str = 'popular-1w', tags: list = None, q: str = None, page: int = 1):
    """Returns a list of ids (str) of collections that match the given search parameters."""
    if page < 1:
        raise ValueError("page must be at least 1")
    if not isinstance(tags, list):
        raise ValueError("tags must be comma-separated list of tags")

    # todo check tag validity

    if order in ("newest", "edittime"):
        return _time_based_explore(order, tags, q, page)
    elif order == "popular-1w":
        return _popularity_based_explore(datetime.datetime.now() - datetime.timedelta(days=7), tags, q, page)
    elif order == "popular-1m":
        return _popularity_based_explore(datetime.datetime.now() - datetime.timedelta(days=30), tags, q, page)
    elif order == "popular-6m":
        return _popularity_based_explore(datetime.datetime.now() - datetime.timedelta(days=180), tags, q, page)
    elif order == "popular-all":
        return _popularity_based_explore(datetime.datetime.fromtimestamp(0), tags, q, page)
    else:
        raise ValueError(f"unknown order: {order}")


def _time_based_explore(order: str, tags: list, q: str, page: int):
    """Returns a list of ids for a time-based explore query."""

    if tags is None:
        cursor = current_app.mdb.workshop_collections.find({"publish_state": PublicationState.PUBLISHED.value})
    else:
        cursor = current_app.mdb.workshop_collections.find(
            {"publish_state": PublicationState.PUBLISHED.value,
             "tags": {"$all": tags}}
        )

    if order == "newest":
        cursor.sort("created_at", pymongo.DESCENDING)
    else:
        cursor.sort("last_edited", pymongo.DESCENDING)

    cursor.limit(50)  # 50 results/page
    cursor.skip(50 * (page - 1))  # seek to page

    return [str(coll['_id']) for coll in cursor]


def _popularity_based_explore(since: datetime.datetime, tags: list, q: str, page: int):
    """Returns a list of ids for a popularity-based explore query."""

    # pipeline on analytics events: turn analytics stream into {_id: coll_id, score: num_subs}
    pipeline = [
        # get all sub/unsub docs since time
        {"$match": {"timestamp": {"$gt": since},
                    "type": {"$in": ["subscribe", "unsubscribe", "server_subscribe", "server_unsubscribe"]}}},

        # give all subscribe and server_subscribe docs score: 1
        # and all unsubscribe and server_unsubscribe docs score: -1
        {"$addFields": {"score": {"$cond": {
            "if": {"type": {"$in": ["subscribe", "server_subscribe"]}},
            "then": 1,
            "else": -1}}}},

        # group all these docs by collection id (object_id)
        # -> {_id: coll_id, score: num_subs}
        {"$group": {"_id": "$object_id", "score": {"$sum": "$score"}}}
    ]

    # todo get actual collections from id, score pairs
    # probably using $in a lot
    cursor = current_app.mdb.analytics_alias_events.aggregate(pipeline)
    return cursor
