from flask import Blueprint, current_app

from lib.auth import requires_auth
from lib.discord import fetch_user_info
from lib.utils import error, expect_json, nullable, success
from workshop.collection import WorkshopAlias, WorkshopCollection
from workshop.constants import ALIAS_SIZE_LIMIT
from workshop.errors import CollectableNotFound, CollectionNotFound

workshop = Blueprint('workshop', __name__)


# ==== error handlers ====
@workshop.errorhandler(CollectionNotFound)
@workshop.errorhandler(CollectableNotFound)
def not_found_handler(e):
    return error(404, str(e))


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


# ---- alias operations ----
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
    pass


@workshop.route("alias/<alias_id>/entitlement", methods=["DELETE"])
@expect_json()
@requires_auth
def delete_alias_entitlement(user, body, alias_id):
    pass


# ---- snippet operations ----
@workshop.route("collection/<coll_id>/snippet", methods=["POST"])
@expect_json()
@requires_auth
def create_snippet(user, body, coll_id):
    pass


@workshop.route("snippet/<snippet_id>", methods=["PATCH"])
@expect_json()
@requires_auth
def edit_snippet(user, body, snippet_id):
    pass


@workshop.route("snippet/<snippet_id>", methods=["GET"])
@expect_json()
@requires_auth
def get_snippet(user, body, snippet_id):
    pass


@workshop.route("snippet/<snippet_id>", methods=["DELETE"])
@expect_json()
@requires_auth
def delete_snippet(user, body, snippet_id):
    pass


@workshop.route("snippet/<snippet_id>/code", methods=["POST"])
@expect_json()
@requires_auth
def create_snippet_code_version(user, body, snippet_id):
    pass


@workshop.route("snippet/<snippet_id>/active-code", methods=["PUT"])
@expect_json()
@requires_auth
def set_active_snippet_code_version(user, body, snippet_id):
    pass


# todo entitlements
@workshop.route("snippet/<snippet_id>/entitlement", methods=["POST"])
@expect_json()
@requires_auth
def add_snippet_entitlement(user, body, snippet_id):
    pass


@workshop.route("snippet/<snippet_id>/entitlement", methods=["DELETE"])
@expect_json()
@requires_auth
def delete_snippet_entitlement(user, body, snippet_id):
    pass

# ---- subscription operations ----

# ---- other ----
