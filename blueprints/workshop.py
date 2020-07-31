from bson import ObjectId
from flask import Blueprint, current_app, request

from lib.auth import requires_auth
from lib.discord import fetch_user_info
from lib.errors import NotAllowed
from lib.utils import error, expect_json, maybe_json, nullable, success
from workshop.collection import WorkshopAlias, WorkshopCollection, WorkshopSnippet
from workshop.constants import ALIAS_SIZE_LIMIT, SNIPPET_SIZE_LIMIT
from workshop.errors import CollectableNotFound, CollectionNotFound, NeedsServerAliaser
from workshop.utils import explore_collections, guild_permissions_check

workshop = Blueprint('workshop', __name__)


# ==== error handlers ====
@workshop.errorhandler(CollectionNotFound)
@workshop.errorhandler(CollectableNotFound)
def not_found_handler(e):
    return error(404, str(e))


@workshop.errorhandler(NeedsServerAliaser)
def needs_server_aliaser_handler(e):
    return error(403, str(e))


# ==== routes ====
# ---- collection operations ----
@workshop.route("collection", methods=["POST"])
@expect_json(name=str, description=str, image=nullable(str))
@requires_auth
def create_collection(user, body):
    new_collection = WorkshopCollection.create_new(int(user.id), body['name'], body['description'], body['image'])
    return success(new_collection.to_dict(js=True), 201)


@workshop.route("collection/<coll_id>", methods=["GET"])
def get_collection(coll_id):
    return success(WorkshopCollection.from_id(coll_id).to_dict(js=True), 200)


@workshop.route("collection/<coll_id>", methods=["PATCH"])
@expect_json(name=str, description=str, image=nullable(str))
@requires_auth
def edit_collection(user, body, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")

    coll.update_info(name=body['name'], description=body['description'], image=body['image'])
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
        coll.set_state(body['state'])
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
        return error(403, "you do not have permission to add editors to this collection")

    coll.add_editor(editor_id)
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
def get_editors(_, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    return success(get_editors(coll), 200)


# todo tags
@workshop.route("collection/<coll_id>/tag", methods=["POST"])
@expect_json(tag=str)
@requires_auth
def add_tag(user, body, coll_id):
    return error(404, "not yet implemented")


@workshop.route("collection/<coll_id>/tag", methods=["DELETE"])
@expect_json(tag=str)
@requires_auth
def remove_tag(user, body, coll_id):
    return error(404, "not yet implemented")


# ---- alias/snippet operations ----
@workshop.route("collection/<coll_id>/alias", methods=["POST"])
@expect_json(name=str, docs=str)
@requires_auth
def create_alias(user, body, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")

    if ' ' in body['name']:
        return error(400, "Alias names cannot contain spaces")
    if body['name'] in current_app.rdb.jget("default_commands", []):
        return error(409, f"{body['name']} is already a built-in command")

    alias = coll.create_alias(body['name'], body['docs'])
    return success(alias.to_dict(js=True), 201)


@workshop.route("alias/<alias_id>/alias", methods=["POST"])
@expect_json(name=str, docs=str)
@requires_auth
def create_subalias(user, body, alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    coll = alias.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")
    if ' ' in body['name']:
        return error(400, "Alias names cannot contain spaces")

    subalias = alias.create_subalias(body['name'], body['docs'])
    return success(subalias.to_dict(js=True), 201)


@workshop.route("alias/<alias_id>", methods=["PATCH"])
@expect_json(name=str, docs=str)
@requires_auth
def edit_alias(user, body, alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    coll = alias.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")
    if ' ' in body['name']:
        return error(400, "Alias names cannot contain spaces")
    if body['name'] in current_app.rdb.jget("default_commands", []):
        return error(409, f"{body['name']} is already a built-in command")

    alias.update_info(body['name'], body['docs'])
    return success(alias.to_dict(js=True), 200)


@workshop.route("alias/<alias_id>", methods=["GET"])
def get_alias(alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    return success(alias.to_dict(js=True), 200)


@workshop.route("alias/<alias_id>", methods=["DELETE"])
@requires_auth
def delete_alias(user, alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    coll = alias.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")

    alias.delete()
    return success(f"Deleted {alias.name}", 200)


@workshop.route("alias/<alias_id>/code", methods=["POST"])
@expect_json(content=str)
@requires_auth
def create_alias_code_version(user, body, alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    coll = alias.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")
    if len(body['content']) > ALIAS_SIZE_LIMIT:
        return error(400, f"max alias size is {ALIAS_SIZE_LIMIT}")

    cv = alias.create_code_version(body['content'])
    return success(cv.to_dict(), 201)


@workshop.route("alias/<alias_id>/active-code", methods=["PUT"])
@expect_json(version=int)
@requires_auth
def set_active_alias_code_version(user, body, alias_id):
    alias = WorkshopAlias.from_id(alias_id)
    coll = alias.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")

    alias.set_active_code_version(body['version'])
    return success(alias.to_dict(js=True), 200)


# todo entitlements
@workshop.route("alias/<alias_id>/entitlement", methods=["POST"])
@expect_json()
@requires_auth
def add_alias_entitlement(user, body, alias_id):
    return error(404, "not yet implemented")


@workshop.route("alias/<alias_id>/entitlement", methods=["DELETE"])
@expect_json()
@requires_auth
def delete_alias_entitlement(user, body, alias_id):
    return error(404, "not yet implemented")


# ---- snippet operations ----
@workshop.route("collection/<coll_id>/snippet", methods=["POST"])
@expect_json(name=str, docs=str)
@requires_auth
def create_snippet(user, body, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")

    if ' ' in body['name']:
        return error(400, "snippet names cannot contain spaces")
    if len(body['name']) < 2:
        return error(400, "snippet names must be at least 2 characters")

    snippet = coll.create_snippet(body['name'], body['docs'])
    return success(snippet.to_dict(js=True), 201)


@workshop.route("snippet/<snippet_id>", methods=["PATCH"])
@expect_json(name=str, docs=str)
@requires_auth
def edit_snippet(user, body, snippet_id):
    snippet = WorkshopSnippet.from_id(snippet_id)
    coll = snippet.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")
    if ' ' in body['name']:
        return error(400, "snippet names cannot contain spaces")
    if len(body['name']) < 2:
        return error(400, "snippet names must be at least 2 characters")

    snippet.update_info(body['name'], body['docs'])
    return success(snippet.to_dict(js=True), 200)


@workshop.route("snippet/<snippet_id>", methods=["GET"])
def get_snippet(snippet_id):
    snippet = WorkshopSnippet.from_id(snippet_id)
    return success(snippet.to_dict(js=True), 200)


@workshop.route("snippet/<snippet_id>", methods=["DELETE"])
@requires_auth
def delete_snippet(user, snippet_id):
    snippet = WorkshopSnippet.from_id(snippet_id)
    coll = snippet.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")

    snippet.delete()
    return success(f"Deleted {snippet.name}", 200)


@workshop.route("snippet/<snippet_id>/code", methods=["POST"])
@expect_json(content=str)
@requires_auth
def create_snippet_code_version(user, body, snippet_id):
    snippet = WorkshopSnippet.from_id(snippet_id)
    coll = snippet.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")
    if len(body['content']) > SNIPPET_SIZE_LIMIT:
        return error(400, f"max snippet size is {SNIPPET_SIZE_LIMIT}")

    cv = snippet.create_code_version(body['content'])
    return success(cv.to_dict(), 201)


@workshop.route("snippet/<snippet_id>/active-code", methods=["PUT"])
@expect_json(version=int)
@requires_auth
def set_active_snippet_code_version(user, body, snippet_id):
    snippet = WorkshopSnippet.from_id(snippet_id)
    coll = snippet.collection

    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")

    snippet.set_active_code_version(body['version'])
    return success(snippet.to_dict(js=True), 200)


# todo entitlements
@workshop.route("snippet/<snippet_id>/entitlement", methods=["POST"])
@expect_json()
@requires_auth
def add_snippet_entitlement(user, body, snippet_id):
    return error(404, "not yet implemented")


@workshop.route("snippet/<snippet_id>/entitlement", methods=["DELETE"])
@expect_json()
@requires_auth
def delete_snippet_entitlement(user, body, snippet_id):
    return error(404, "not yet implemented")


# ---- subscription operations ----
def _bindings_check(coll, bindings):
    if bindings is None:
        return

    for binding in bindings:
        if not isinstance(binding, dict):
            raise NotAllowed("bindings must be list of {name, id}")

        if set(binding) != {"name", "id"}:
            raise NotAllowed("bindings must be list of {name, id}")

        if not isinstance(binding['name'], str):
            raise NotAllowed("binding name must be str")

        if isinstance(binding['id'], dict):
            if '$oid' not in binding['id']:
                raise NotAllowed("binding id must be ObjectId")
            oid = ObjectId(binding['id']['$oid'])
        elif isinstance(binding['id'], str):
            oid = ObjectId(binding['id'])
        else:
            raise NotAllowed("binding id must be ObjectId")

        if not (oid in coll.alias_ids or oid in coll.snippet_ids):
            raise NotAllowed("binding must be to object in collection")

        binding['id'] = oid


@workshop.route("collection/<coll_id>/subscription/me", methods=["PUT"])
@maybe_json(alias_bindings=nullable(list), snippet_bindings=nullable(list))
@requires_auth
def personal_subscribe(user, body, coll_id):
    coll = WorkshopCollection.from_id(coll_id)

    if body is None:
        alias_bindings = snippet_bindings = None
    else:
        alias_bindings = body['alias_bindings']
        _bindings_check(coll, alias_bindings)
        snippet_bindings = body['snippet_bindings']
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
    return success(coll.my_sub(int(user.id)), 200)


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
        alias_bindings = body['alias_bindings']
        _bindings_check(coll, alias_bindings)
        snippet_bindings = body['snippet_bindings']
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
    return success(coll.guild_sub(guild_id), 200)


@workshop.route("subscribed/<int:guild_id>", methods=["GET"])
def get_guild_subscriptions(guild_id):
    """Returns a list of str representing the IDs of subscribed collections."""
    return success([str(oid) for oid in WorkshopCollection.guild_active_ids(guild_id)], 200)


# ---- other ----
# todo
@workshop.route("entitlements", methods=["GET"])
def get_entitlements():
    pass


@workshop.route("tags", methods=["GET"])
def get_tags():
    pass


@workshop.route("explore", methods=["GET"])
def get_explore_collections():
    """
    Returns a paginated list of collection IDs (50/page), based on given filters.

    :q str order: The method to explore by: popular-1w, popular-1m, popular-6m, popular-all, newest, edittime
    :q str tags: A comma-separated list of tags that returned collections must have all of.
    :q str q: A search query. todo how
    :q int page: The page of results to return.
    """
    order = request.args.get('order', 'popular-1w')
    tags = request.args.get('tags')
    if tags:
        tags = tags.split(',')
    else:
        tags = []
    q = request.args.get('q')
    page = request.args.get('page')
    if page:
        try:
            page = int(page)
        except ValueError:
            return error(400, 'page must be int')
    coll_ids = explore_collections(order, tags, q, page)
    return success(coll_ids, 200)


@workshop.route("owned", methods=["GET"])
@requires_auth
def get_owned_collections(user):
    pass


@workshop.route("editable", methods=["GET"])
@requires_auth
def get_editable_collections(user):
    pass
