from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, request

from gamedata.compendium import compendium
from lib.auth import maybe_auth, requires_auth, requires_user_permissions
from lib.discord import fetch_user_info
from lib.errors import Error, NotAllowed
from lib.utils import error, expect_json, maybe_json, nullable, success
from workshop.collection import PublicationState, WorkshopAlias, WorkshopCollection, WorkshopSnippet
from workshop.constants import ALIAS_SIZE_LIMIT, SNIPPET_SIZE_LIMIT
from workshop.errors import CollectableNotFound, CollectionNotFound, NeedsServerAliaser
from workshop.utils import explore_collections, guild_permissions_check

workshop = Blueprint("workshop", __name__)


# ==== error handlers ====
@workshop.errorhandler(CollectionNotFound)
@workshop.errorhandler(CollectableNotFound)
def not_found_handler(e):
    return error(404, str(e))


@workshop.errorhandler(NeedsServerAliaser)
def needs_server_aliaser_handler(e):
    return error(403, str(e))


# ==== auth helpers ====
def get_collection_with_editor_check(coll_id, user):
    coll = WorkshopCollection.from_id(coll_id)
    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        raise Error(403, "you do not have permission to edit this collection")
    return coll


def get_collectable_with_editor_check(cls, collectable_id, user):
    collectable = cls.from_id(collectable_id)
    coll = collectable.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        raise Error(403, "you do not have permission to edit this collection")
    return collectable


def get_collection_with_private_check(coll_id, user):
    coll = WorkshopCollection.from_id(coll_id)
    if coll.publish_state == PublicationState.PRIVATE and (
        user is None or not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id)))
    ):
        raise Error(403, "This collection is private.")
    return coll


# ==== routes ====
# ---- collection operations ----
@workshop.route("collection", methods=["POST"])
@expect_json(name=str, description=str, image=nullable(str))
@requires_auth
def create_collection(user, body):
    new_collection = WorkshopCollection.create_new(int(user.id), body["name"], body["description"], body["image"])
    return success(new_collection.to_dict(js=True), 201)


@workshop.route("collection/<coll_id>", methods=["GET"])
@maybe_auth
def get_collection(user, coll_id):
    coll = get_collection_with_private_check(coll_id, user)
    return success(coll.to_dict(js=True), 200)


@workshop.route("collection/<coll_id>/full", methods=["GET"])
@maybe_auth
def get_collection_full(user, coll_id):
    coll = get_collection_with_private_check(coll_id, user)
    out = coll.to_dict(js=True)

    def dictify(alias):
        ad = alias.to_dict(js=True, include_code_versions=False)
        ad["subcommands"] = [dictify(subcommand) for subcommand in alias.subcommands]
        return ad

    out.update(
        {
            "aliases": [dictify(alias) for alias in coll.aliases],
            "snippets": [snippet.to_dict(js=True, include_code_versions=False) for snippet in coll.snippets],
        }
    )
    return success(out, 200)


@workshop.route("collection/batch", methods=["GET"])
@requires_auth
def get_collection_batch(user):
    """
    Gets many collections in a single request.

    GET /workshop/collection/batch?c=1,2,3,4,...
    """
    if "c" not in request.args:
        return error(400, "c is a required query param")
    collections = []
    try:
        for coll_id in map(ObjectId, request.args.get("c").split(",")):
            try:
                coll = get_collection_with_private_check(coll_id, user)
            except Error as e:
                if e.code != 403:  # don't return private collections
                    raise
            else:
                collections.append(coll.to_dict(js=True))
    except InvalidId:
        return error(400, "invalid collection ID")
    return success(collections, 200)


@workshop.route("collection/<coll_id>", methods=["PATCH"])
@expect_json(name=str, description=str, image=nullable(str))
@requires_auth
def edit_collection(user, body, coll_id):
    coll = get_collection_with_editor_check(coll_id, user)
    coll.update_info(name=body["name"], description=body["description"], image=body["image"])
    return success(coll.to_dict(js=True), 200)


@workshop.route("collection/<coll_id>", methods=["DELETE"])
@requires_auth
def delete_collection(user, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    if not coll.is_owner(int(user.id)):
        return error(403, "you do not have permission to delete this collection")

    coll.delete()
    return success(f"Deleted {coll.name}", 200)


@workshop.route("collection/<coll_id>/state", methods=["PATCH"])
@expect_json(state=str)  # PRIVATE, UNLISTED, PUBLISHED
@requires_auth
def set_state(user, body, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    if not coll.is_owner(int(user.id)):
        return error(403, "you do not have permission to change the state of this collection")

    try:
        coll.set_state(body["state"])
    except ValueError as e:  # invalid publication state
        return error(400, str(e))

    return success(coll.to_dict(js=True), 200)


def get_editors(coll):
    editors = []
    for editor_id in coll.get_editor_ids():
        editors.append(fetch_user_info(editor_id).to_dict())
    return editors


@workshop.route("collection/<coll_id>/editor/<int:editor_id>", methods=["PUT"])
@requires_auth
def add_editor(user, coll_id, editor_id: int):
    coll = WorkshopCollection.from_id(coll_id)
    if not coll.is_owner(int(user.id)):
        return error(403, "You do not have permission to add editors to this collection.")
    if coll.is_owner(editor_id):
        return error(409, "You are already the owner of this collection.")

    try:
        coll.add_editor(editor_id)
    except NotAllowed as e:
        return error(409, str(e))
    return success(get_editors(coll), 200)


@workshop.route("collection/<coll_id>/editor/<int:editor_id>", methods=["DELETE"])
@requires_auth
def remove_editor(user, coll_id, editor_id: int):
    coll = WorkshopCollection.from_id(coll_id)
    if not (coll.is_owner(int(user.id)) or editor_id == int(user.id)):
        return error(403, "you do not have permission to remove editors from this collection")

    coll.remove_editor(editor_id)
    return success(get_editors(coll), 200)


@workshop.route("collection/<coll_id>/editors", methods=["GET"])
@requires_auth
def route_get_editors(_, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    return success(get_editors(coll), 200)


@workshop.route("collection/<coll_id>/tag", methods=["POST"])
@expect_json(tag=str)
@requires_auth
def add_tag(user, body, coll_id):
    coll = get_collection_with_editor_check(coll_id, user)
    coll.add_tag(body["tag"])
    return success(coll.tags, 200)


@workshop.route("collection/<coll_id>/tag", methods=["DELETE"])
@expect_json(tag=str)
@requires_auth
def remove_tag(user, body, coll_id):
    coll = get_collection_with_editor_check(coll_id, user)
    coll.remove_tag(body["tag"])
    return success(coll.tags, 200)


# ---- alias/snippet operations ----
@workshop.route("collection/<coll_id>/alias", methods=["POST"])
@expect_json(name=str, docs=str)
@requires_auth
def create_alias(user, body, coll_id):
    coll = get_collection_with_editor_check(coll_id, user)

    if not body["name"]:
        return error(400, "Alias must have a name")
    if not 0 < len(body["name"]) < 1024:
        return error(400, "Alias names must be between 1 and 1024 characters long")
    if " " in body["name"]:
        return error(400, "Alias names cannot contain spaces")
    if body["name"] in current_app.rdb.jget("default_commands", []):
        return error(409, f"{body['name']} is already a built-in command")

    alias = coll.create_alias(body["name"], body["docs"])
    result = alias.to_dict(js=True)
    result["subcommands"] = []  # return WorkshopAliasFull interface
    return success(result, 201)


@workshop.route("alias/<alias_id>/alias", methods=["POST"])
@expect_json(name=str, docs=str)
@requires_auth
def create_subalias(user, body, alias_id):
    alias = get_collectable_with_editor_check(WorkshopAlias, alias_id, user)

    if not body["name"]:
        return error(400, "Alias must have a name")
    if not 0 < len(body["name"]) < 1024:
        return error(400, "Alias names must be between 1 and 1024 characters long")
    if " " in body["name"]:
        return error(400, "Alias names cannot contain spaces")

    subalias = alias.create_subalias(body["name"], body["docs"])
    result = subalias.to_dict(js=True)
    result["subcommands"] = []  # return WorkshopAliasFull interface
    return success(result, 201)


@workshop.route("alias/<alias_id>", methods=["PATCH"])
@expect_json(name=str, docs=str)
@requires_auth
def edit_alias(user, body, alias_id):
    alias = get_collectable_with_editor_check(WorkshopAlias, alias_id, user)

    if not body["name"]:
        return error(400, "Alias must have a name")
    if not 0 < len(body["name"]) < 1024:
        return error(400, "Alias names must be between 1 and 1024 characters long")
    if " " in body["name"]:
        return error(400, "Alias names cannot contain spaces")
    if not alias.has_parent and body["name"] in current_app.rdb.jget("default_commands", []):
        return error(409, f"{body['name']} is already a built-in command")

    alias.update_info(body["name"], body["docs"])
    return success(alias.to_dict(js=True), 200)


@workshop.route("alias/<alias_id>", methods=["GET"])
def get_alias(alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    return success(alias.to_dict(js=True), 200)


@workshop.route("alias/<alias_id>", methods=["DELETE"])
@requires_auth
def delete_alias(user, alias_id):
    alias = get_collectable_with_editor_check(WorkshopAlias, alias_id, user)
    alias.delete()
    return success(f"Deleted {alias.name}", 200)


@workshop.route("alias/<alias_id>/code", methods=["GET"])
@requires_auth
def get_alias_code_versions(user, alias_id):
    alias = get_collectable_with_editor_check(WorkshopAlias, alias_id, user)
    return _get_paginated_collectable_code_versions(alias)


@workshop.route("alias/<alias_id>/code", methods=["POST"])
@expect_json(content=str)
@requires_auth
def create_alias_code_version(user, body, alias_id):
    alias = get_collectable_with_editor_check(WorkshopAlias, alias_id, user)

    if len(body["content"]) > ALIAS_SIZE_LIMIT:
        return error(400, f"max alias size is {ALIAS_SIZE_LIMIT}")

    cv = alias.create_code_version(body["content"])
    return success(cv.to_dict(), 201)


@workshop.route("alias/<alias_id>/active-code", methods=["PUT"])
@expect_json(version=int)
@requires_auth
def set_active_alias_code_version(user, body, alias_id):
    alias = get_collectable_with_editor_check(WorkshopAlias, alias_id, user)
    alias.set_active_code_version(body["version"])
    return success(alias.to_dict(js=True), 200)


def _add_entitlement_to_collectable(collectable, entity_type: str, entity_id: int, required: bool = False):
    sourced = compendium.lookup_entity(entity_type, entity_id)
    if sourced is None:
        return error(404, "Entitlement entity not found")
    return collectable.add_entitlement(sourced, required)


def _remove_entitlement_from_collectable(collectable, entity_type: str, entity_id: int, ignore_required: bool = False):
    sourced = compendium.lookup_entity(entity_type, entity_id)
    if sourced is None:
        return error(404, "Entitlement entity not found")
    return collectable.remove_entitlement(sourced, ignore_required)


def _get_paginated_collectable_code_versions(collectable):
    """Returns the *limit* most recent code versions"""
    try:
        limit = request.args.get("limit", 50, type=int)
        skip = request.args.get("skip", 0, type=int)
    except ValueError:
        return error(400, "invalid query")
    if limit < 1 or skip < 0:
        return error(400, "invalid query")

    start_idx = -skip - 1
    end_idx = -skip - 1 - limit
    code_versions = [v.to_dict() for v in collectable.versions[start_idx:end_idx:-1]]
    return success(code_versions, 200)


@workshop.route("alias/<alias_id>/entitlement", methods=["POST"])
@expect_json(entity_type=str, entity_id=(str, int), required=bool, optional=["required"])
@requires_auth
def add_alias_entitlement(user, body, alias_id):
    alias = get_collectable_with_editor_check(WorkshopAlias, alias_id, user)
    return success(_add_entitlement_to_collectable(alias, body["entity_type"], int(body["entity_id"])))


@workshop.route("alias/<alias_id>/entitlement", methods=["DELETE"])
@expect_json(entity_type=str, entity_id=(str, int))
@requires_auth
def delete_alias_entitlement(user, body, alias_id):
    alias = get_collectable_with_editor_check(WorkshopAlias, alias_id, user)
    return success(_remove_entitlement_from_collectable(alias, body["entity_type"], int(body["entity_id"])))


# ---- snippet operations ----
@workshop.route("collection/<coll_id>/snippet", methods=["POST"])
@expect_json(name=str, docs=str)
@requires_auth
def create_snippet(user, body, coll_id):
    coll = get_collection_with_editor_check(coll_id, user)

    if " " in body["name"]:
        return error(400, "Snippet names cannot contain spaces")
    if not 1 < len(body["name"]) < 1024:
        return error(400, "Snippet names must be between 2 and 1024 characters long")

    snippet = coll.create_snippet(body["name"], body["docs"])
    return success(snippet.to_dict(js=True), 201)


@workshop.route("snippet/<snippet_id>", methods=["PATCH"])
@expect_json(name=str, docs=str)
@requires_auth
def edit_snippet(user, body, snippet_id):
    snippet = get_collectable_with_editor_check(WorkshopSnippet, snippet_id, user)

    if " " in body["name"]:
        return error(400, "snippet names cannot contain spaces")
    if not 1 < len(body["name"]) < 1024:
        return error(400, "Snippet names must be between 2 and 1024 characters long")

    snippet.update_info(body["name"], body["docs"])
    return success(snippet.to_dict(js=True), 200)


@workshop.route("snippet/<snippet_id>", methods=["GET"])
def get_snippet(snippet_id):
    snippet = WorkshopSnippet.from_id(snippet_id)
    return success(snippet.to_dict(js=True), 200)


@workshop.route("snippet/<snippet_id>", methods=["DELETE"])
@requires_auth
def delete_snippet(user, snippet_id):
    snippet = get_collectable_with_editor_check(WorkshopSnippet, snippet_id, user)

    snippet.delete()
    return success(f"Deleted {snippet.name}", 200)


@workshop.route("snippet/<snippet_id>/code", methods=["GET"])
@requires_auth
def get_snippet_code_versions(user, snippet_id):
    snippet = get_collectable_with_editor_check(WorkshopSnippet, snippet_id, user)
    return _get_paginated_collectable_code_versions(snippet)


@workshop.route("snippet/<snippet_id>/code", methods=["POST"])
@expect_json(content=str)
@requires_auth
def create_snippet_code_version(user, body, snippet_id):
    snippet = get_collectable_with_editor_check(WorkshopSnippet, snippet_id, user)

    if len(body["content"]) > SNIPPET_SIZE_LIMIT:
        return error(400, f"max snippet size is {SNIPPET_SIZE_LIMIT}")

    cv = snippet.create_code_version(body["content"])
    return success(cv.to_dict(), 201)


@workshop.route("snippet/<snippet_id>/active-code", methods=["PUT"])
@expect_json(version=int)
@requires_auth
def set_active_snippet_code_version(user, body, snippet_id):
    snippet = get_collectable_with_editor_check(WorkshopSnippet, snippet_id, user)
    snippet.set_active_code_version(body["version"])
    return success(snippet.to_dict(js=True), 200)


@workshop.route("snippet/<snippet_id>/entitlement", methods=["POST"])
@expect_json(entity_type=str, entity_id=(str, int), required=bool, optional=["required"])
@requires_auth
def add_snippet_entitlement(user, body, snippet_id):
    snippet = get_collectable_with_editor_check(WorkshopSnippet, snippet_id, user)
    return success(_add_entitlement_to_collectable(snippet, body["entity_type"], int(body["entity_id"])))


@workshop.route("snippet/<snippet_id>/entitlement", methods=["DELETE"])
@expect_json(entity_type=str, entity_id=(str, int))
@requires_auth
def delete_snippet_entitlement(user, body, snippet_id):
    snippet = get_collectable_with_editor_check(WorkshopSnippet, snippet_id, user)
    return success(_remove_entitlement_from_collectable(snippet, body["entity_type"], int(body["entity_id"])))


# ---- subscription operations ----
def _bindings_check(coll, bindings):
    if bindings is None:
        return

    for binding in bindings:
        if not isinstance(binding, dict):
            raise NotAllowed("bindings must be list of {name, id}")

        if set(binding) != {"name", "id"}:
            raise NotAllowed("bindings must be list of {name, id}")

        if not isinstance(binding["name"], str):
            raise NotAllowed("binding name must be str")

        if isinstance(binding["id"], dict):
            if "$oid" not in binding["id"]:
                raise NotAllowed("binding id must be ObjectId")
            oid = ObjectId(binding["id"]["$oid"])
        elif isinstance(binding["id"], str):
            oid = ObjectId(binding["id"])
        else:
            raise NotAllowed("binding id must be ObjectId")

        if not (oid in coll.alias_ids or oid in coll.snippet_ids):
            raise NotAllowed("binding must be to object in collection")

        binding["id"] = oid


@workshop.route("collection/<coll_id>/subscription/me", methods=["PUT"])
@maybe_json(alias_bindings=nullable(list), snippet_bindings=nullable(list))
@requires_auth
def personal_subscribe(user, body, coll_id):
    coll = WorkshopCollection.from_id(coll_id)

    if body is None:
        alias_bindings = snippet_bindings = None
    else:
        alias_bindings = body["alias_bindings"]
        _bindings_check(coll, alias_bindings)
        snippet_bindings = body["snippet_bindings"]
        _bindings_check(coll, snippet_bindings)

    bindings = coll.subscribe(int(user.id), alias_bindings, snippet_bindings)
    return success(bindings, 200)


@workshop.route("collection/<coll_id>/subscription/me", methods=["DELETE"])
@requires_auth
def personal_unsubscribe(user, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    coll.unsubscribe(int(user.id))
    return success(f"Unsubscribed from {coll.name}", 200)


@workshop.route("collection/<coll_id>/subscription/me", methods=["GET"])
@requires_auth
def get_personal_subscription(user, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    sub = coll.my_sub(int(user.id))
    if sub is None:
        return error(404, "You are not subscribed to this collection")
    return success(sub, 200)


@workshop.route("subscribed/me", methods=["GET"])
@requires_auth
def get_personal_subscriptions(user):
    """Returns a list of str representing the IDs of subscribed collections."""
    return success([str(oid) for oid in WorkshopCollection.my_sub_ids(int(user.id))], 200)


@workshop.route("collection/<coll_id>/subscription/<int:guild_id>", methods=["PUT"])
@maybe_json(alias_bindings=nullable(list), snippet_bindings=nullable(list))
@requires_auth
def guild_subscribe(user, body, coll_id, guild_id):
    guild_permissions_check(user, guild_id)

    coll = WorkshopCollection.from_id(coll_id)
    if body is None:
        alias_bindings = snippet_bindings = None
    else:
        alias_bindings = body["alias_bindings"]
        _bindings_check(coll, alias_bindings)
        snippet_bindings = body["snippet_bindings"]
        _bindings_check(coll, snippet_bindings)

    bindings = coll.set_server_active(guild_id, alias_bindings, snippet_bindings, invoker_id=int(user.id))
    return success(bindings, 200)


@workshop.route("collection/<coll_id>/subscription/<int:guild_id>", methods=["DELETE"])
@requires_auth
def guild_unsubscribe(user, coll_id, guild_id):
    guild_permissions_check(user, guild_id)

    coll = WorkshopCollection.from_id(coll_id)
    coll.unset_server_active(guild_id, int(user.id))
    return success(f"Unsubscribed from {coll.name}", 200)


@workshop.route("collection/<coll_id>/subscription/<int:guild_id>", methods=["GET"])
def get_guild_subscription(coll_id, guild_id):
    coll = WorkshopCollection.from_id(coll_id)
    sub = coll.guild_sub(guild_id)
    if sub is None:
        return error(404, "You are not subscribed to this collection")
    return success(sub, 200)


@workshop.route("subscribed/<int:guild_id>", methods=["GET"])
def get_guild_subscriptions(guild_id):
    """Returns a list of str representing the IDs of subscribed collections."""
    return success([str(oid) for oid in WorkshopCollection.guild_active_ids(guild_id)], 200)


# ---- other ----
@workshop.route("tags", methods=["GET"])
def get_tags():
    tags = current_app.mdb.workshop_tags.find()
    return success(list(tags), 200)


@workshop.route("explore", methods=["GET"])
def get_explore_collections():
    """
    Returns a paginated list of collection IDs (50/page), based on given filters.

    :q str order: The method to explore by: popular-1w, popular-1m, popular-6m, popular-all, newest, edittime, relevance
    :q str tags: A comma-separated list of tags that returned collections must have all of.
    :q str q: A search query.
    :q int page: The page of results to return.
    """
    order = request.args.get("order", "popular-1w")
    tags = request.args.get("tags")
    if tags:
        tags = tags.split(",")
    else:
        tags = []
    q = request.args.get("q")
    page = request.args.get("page", 1)
    if page:
        try:
            page = int(page)
        except ValueError:
            return error(400, "page must be int")

    try:
        coll_ids = explore_collections(order, tags, q, page)
    except ValueError as e:
        return error(400, str(e))

    return success(coll_ids, 200)


@workshop.route("owned", methods=["GET"])
@requires_auth
def get_owned_collections(user):
    """Returns a list of collection IDs the user owns in an unsorted order."""
    owned = WorkshopCollection.user_owned_ids(int(user.id))
    return success([str(o) for o in owned], 200)


@workshop.route("editable", methods=["GET"])
@requires_auth
def get_editable_collections(user):
    """Returns a list of collection IDs the user has edit permission on in an unsorted order."""
    editable = WorkshopCollection.my_editable_ids(int(user.id))
    return success(list([str(o) for o in editable]), 200)


@workshop.route("guild-check", methods=["GET"])
@requires_auth
def do_guild_permissions_check(user):
    if "g" not in request.args:
        return error(400, "g is a required query param")
    guild_id = request.args.get("g")
    try:
        guild_id = int(guild_id)
    except ValueError:
        return error(400, f"{guild_id} is not a valid guild id")

    try:
        result = guild_permissions_check(user, guild_id)
    except NeedsServerAliaser as e:
        return success({"can_edit": False, "message": str(e)})
    return success({"can_edit": result, "message": None})


# ---- moderator endpoints ----
@workshop.route("moderator/collection/<coll_id>/state", methods=["PATCH"])
@expect_json(state=str)  # PRIVATE, UNLISTED, PUBLISHED
@requires_user_permissions("moderator")
def moderator_set_collection_state(_, body, coll_id):
    coll = WorkshopCollection.from_id(coll_id)

    try:
        coll.set_state(body["state"], run_checks=False)
    except ValueError as e:  # invalid publication state
        return error(400, str(e))

    return success(coll.to_dict(js=True), 200)


@workshop.route("moderator/collection/<coll_id>", methods=["DELETE"])
@requires_user_permissions("moderator")
def moderator_delete_collection(_, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    coll.delete(run_checks=False)
    return success(f"Deleted {coll.name}", 200)


@workshop.route("moderator/alias/<alias_id>/entitlement", methods=["POST"])
@expect_json(entity_type=str, entity_id=(str, int), required=bool, optional=["required"])
@requires_user_permissions("moderator")
def moderator_add_alias_entitlement(_, body, alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    return success(_add_entitlement_to_collectable(alias, body["entity_type"], int(body["entity_id"]), required=True))


@workshop.route("moderator/alias/<alias_id>/entitlement", methods=["DELETE"])
@expect_json(entity_type=str, entity_id=(str, int))
@requires_user_permissions("moderator")
def moderator_delete_alias_entitlement(_, body, alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    result = _remove_entitlement_from_collectable(
        alias, body["entity_type"], int(body["entity_id"]), ignore_required=True
    )
    return success(result)


@workshop.route("moderator/snippet/<snippet_id>/entitlement", methods=["POST"])
@expect_json(entity_type=str, entity_id=(str, int), required=bool, optional=["required"])
@requires_user_permissions("moderator")
def moderator_add_snippet_entitlement(_, body, snippet_id):
    snippet = WorkshopSnippet.from_id(snippet_id)
    return success(_add_entitlement_to_collectable(snippet, body["entity_type"], int(body["entity_id"]), required=True))


@workshop.route("moderator/snippet/<snippet_id>/entitlement", methods=["DELETE"])
@expect_json(entity_type=str, entity_id=(str, int))
@requires_user_permissions("moderator")
def moderator_delete_snippet_entitlement(_, body, snippet_id):
    snippet = WorkshopSnippet.from_id(snippet_id)
    result = _remove_entitlement_from_collectable(
        snippet, body["entity_type"], int(body["entity_id"]), ignore_required=True
    )
    return success(result)
