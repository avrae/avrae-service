import json
from typing import List, Optional, Union

from bson import ObjectId
from flask import Blueprint, current_app, request
from pydantic import BaseModel, HttpUrl, ValidationError, constr

from lib.auth import maybe_auth, requires_auth
from lib.utils import error, expect_json, success
from lib.validation import str1024, str255, str4096, parse_validation_error
from .helpers import user_can_edit, user_can_view, user_editable, user_is_owner

items = Blueprint('homebrew/items', __name__)


# ==== helpers ====
def _is_owner(user, obj_id):
    return user_is_owner(data_coll=current_app.mdb.packs, user=user, obj_id=obj_id)


def _can_view(user, obj_id):
    return user_can_view(
        data_coll=current_app.mdb.packs, sub_coll=current_app.mdb.pack_subscriptions, user=user,
        obj_id=obj_id
    )


def _can_edit(user, obj_id):
    return user_can_edit(
        data_coll=current_app.mdb.packs, sub_coll=current_app.mdb.pack_subscriptions, user=user,
        obj_id=obj_id
    )


def _editable(user):
    return user_editable(data_coll=current_app.mdb.packs, sub_coll=current_app.mdb.pack_subscriptions, user=user)


# ==== routes ====
@items.route('/me', methods=['GET'])
@requires_auth
def user_packs(user):
    data = list(_editable(user))
    for pack in data:
        pack['numItems'] = len(pack['items'])
        pack['owner'] = str(pack['owner'])
        del pack['items']
    return success(data)


@items.route('', methods=['POST'])
@requires_auth
def new_pack(user):
    reqdata = request.json
    if reqdata is None:
        return error(400, "No data found")
    if 'name' not in reqdata:
        return error(400, "Missing name field")
    pack = {
        'name': reqdata['name'],
        'public': bool(reqdata.get('public', False)),
        'desc': reqdata.get('desc', ''),
        'image': reqdata.get('image', ''),
        'owner': int(user.id),
        'items': []
    }
    result = current_app.mdb.packs.insert_one(pack)
    data = {"packId": str(result.inserted_id)}
    return success(data)


@items.route('/<pack>', methods=['GET'])
@maybe_auth
def get_pack(user, pack):
    data = current_app.mdb.packs.find_one({"_id": ObjectId(pack)})
    if data is None:
        return error(404, "Pack not found")
    if not _can_view(user, ObjectId(pack)):
        return error(403, "You do not have permission to view this pack")
    data['owner'] = str(data['owner'])
    return success(data)


@items.route('/<pack>', methods=['PUT'])
@requires_auth
def put_pack(user, pack):
    reqdata = request.json
    if not _can_edit(user=user, obj_id=ObjectId(pack)):
        return error(403, "You do not have permission to edit this pack")

    try:
        the_pack = Pack.parse_obj(reqdata)
    except ValidationError as e:
        e = parse_validation_error(reqdata, 'items', e)
        return error(400, str(e))

    current_app.mdb.packs.update_one({"_id": ObjectId(pack)}, {"$set": the_pack.dict(exclude_unset=True)})
    return success("Pack updated.")


@items.route('/<pack>', methods=['DELETE'])
@requires_auth
def delete_pack(user, pack):
    if not _is_owner(user, ObjectId(pack)):
        return error(403, "You do not have permission to delete this pack")
    current_app.mdb.packs.delete_one({"_id": ObjectId(pack)})
    current_app.mdb.pack_subscriptions.delete_many({"object_id": ObjectId(pack)})
    return success("Pack deleted.")


@items.route('/<pack>/sharing', methods=['PATCH'])
@expect_json(public=bool)
@requires_auth
def update_pack_sharing(user, data, pack):
    if not _can_edit(user, ObjectId(pack)):
        return error(403, "You do not have permission to edit this pack")

    current_app.mdb.packs.update_one({"_id": ObjectId(pack)}, {"$set": {"public": data['public']}})
    return success("Tome updated.")


@items.route('/<pack>/editors', methods=['GET'])
@requires_auth
def get_pack_editors(user, pack):
    if not _can_view(user, ObjectId(pack)):
        return error(403, "You do not have permission to view this pack")

    data = [str(sd['subscriber_id']) for sd in
            current_app.mdb.pack_subscriptions.find({"type": "editor", "object_id": ObjectId(pack)})]

    return success(data)


@items.route('/srd', methods=['GET'])
def srd_items():
    with open('static/template-items.json') as f:
        _items = json.load(f)
    return success(_items)


# ==== validation ====
class Item(BaseModel):
    name: str255
    meta: str1024
    desc: str4096
    image: Optional[Union[HttpUrl, constr(max_length=0)]]


class Pack(BaseModel):
    name: str255
    public: bool
    desc: str4096
    image: Optional[Union[HttpUrl, constr(max_length=0)]]
    items: List[Item]
