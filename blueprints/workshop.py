import functools

from flask import Blueprint

from lib.auth import requires_auth
from lib.utils import error, expect_json, nullable, success
from workshop.collection import WorkshopCollection
from workshop.errors import CollectableNotFound, CollectionNotFound

workshop = Blueprint('workshop', __name__)


@workshop.errorhandler(CollectionNotFound)
@workshop.errorhandler(CollectableNotFound)
def not_found_handler(e):
    return error(404, str(e))


@workshop.route("collection", methods=["POST"])
@expect_json(name=str, description=str, image=nullable(str))
@requires_auth
def create_collection(user, body):
    new_collection = WorkshopCollection.create_new(int(user.id), body['name'], body['description'], body['image'])
    return success(new_collection.to_dict(js=True), 201)


@workshop.route("collection/<coll_id>", methods=["PATCH"])
@expect_json(name=str, description=str, image=nullable(str))
@requires_auth
def edit_collection(user, body, coll_id):
    coll = WorkshopCollection.from_id(coll_id)
    if not (coll.is_owner(int(user.id)) or coll.is_editor(int(user.id))):
        return error(403, "you do not have permission to edit this collection")

    coll.update_info(name=body['name'], description=body['description'], image=body['image'])
    return success(coll.to_dict(js=True), 200)


@workshop.route("collection/<coll_id>/editor/<int:editor_id>", methods=["PUT"])
@requires_auth
def add_editor(user, coll_id, editor_id: int):
    coll = WorkshopCollection.from_id(coll_id)
    if not coll.is_owner(int(user.id)):
        return error(403, "you do not have permission to add editors to this collection")

    coll.add_editor(editor_id)
    return success("Added editor", 200)


@workshop.route("collection/<coll_id>/editor/<int:editor_id>", methods=["DELETE"])
@requires_auth
def remove_editor(user, coll_id, editor_id: int):
    coll = WorkshopCollection.from_id(coll_id)
    if not (coll.is_owner(int(user.id)) or editor_id == int(user.id)):
        return error(403, "you do not have permission to remove editors from this collection")

    coll.remove_editor(editor_id)
    return success("Removed editor", 200)
