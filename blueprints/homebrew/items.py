import json

from bson import ObjectId
from flask import Blueprint, current_app, request

from lib.discord import get_user_info
from lib.utils import jsonify
from .helpers import user_can_edit, user_can_view, user_editable, user_is_owner

items = Blueprint('homebrew/items', __name__)

PACK_FIELDS = {"name", "owner", "public", "desc", "image", "items", "numItems"}
ITEM_FIELDS = ("name", "meta", "desc", "image")
IGNORED_FIELDS = {"_id", "active", "server_active", "subscribers"}


def _is_owner(user, obj_id):
    return user_is_owner(data_coll=current_app.mdb.packs, user=user, obj_id=obj_id)


def _can_view(user, obj_id):
    return user_can_view(data_coll=current_app.mdb.packs, sub_coll=current_app.mdb.pack_subscriptions, user=user,
                         obj_id=obj_id)


def _can_edit(user, obj_id):
    return user_can_edit(data_coll=current_app.mdb.packs, sub_coll=current_app.mdb.pack_subscriptions, user=user,
                         obj_id=obj_id)


def _editable(user):
    return user_editable(data_coll=current_app.mdb.packs, sub_coll=current_app.mdb.pack_subscriptions, user=user)


@items.route('/me', methods=['GET'])
def user_packs():
    user = get_user_info()
    data = list(_editable(user))
    for pack in data:
        pack['numItems'] = len(pack['items'])
        del pack['items']
    return jsonify(data)


@items.route('', methods=['POST'])
def new_pack():
    user = get_user_info()
    reqdata = request.json
    if reqdata is None:
        return "No data found", 400
    if 'name' not in reqdata:
        return "Missing name field", 400
    pack = {
        'name': reqdata['name'],
        'public': bool(reqdata.get('public', False)),
        'desc': reqdata.get('desc', ''),
        'image': reqdata.get('image', ''),
        'owner': int(user.id),
        'items': []
    }
    result = current_app.mdb.packs.insert_one(pack)
    data = {"success": True, "packId": str(result.inserted_id)}
    return jsonify(data)


@items.route('/<pack>', methods=['GET'])
def get_pack(pack):
    user = None
    if 'Authorization' in request.headers:
        user = get_user_info()
    data = current_app.mdb.packs.find_one({"_id": ObjectId(pack)})
    if data is None:
        return "Pack not found", 404
    if not _can_view(user, ObjectId(pack)):
        return "You do not have permission to view this pack", 403
    return jsonify(data)


@items.route('/<pack>', methods=['PUT'])
def put_pack(pack):
    user = get_user_info()
    reqdata = request.json
    if not _can_edit(user=user, obj_id=ObjectId(pack)):
        return "You do not have permission to edit this pack", 403

    for field in IGNORED_FIELDS:
        if field in reqdata:
            reqdata.pop(field)

    if not all(k in PACK_FIELDS for k in reqdata):
        return "Invalid field", 400
    if "items" in reqdata:
        for item in reqdata['items']:
            if not all(k in ITEM_FIELDS for k in item):
                return f"Invalid item field in {item}", 400

    current_app.mdb.packs.update_one({"_id": ObjectId(pack)}, {"$set": reqdata})
    return "Pack updated."


@items.route('/<pack>', methods=['DELETE'])
def delete_pack(pack):
    user = get_user_info()
    if not _is_owner(user, ObjectId(pack)):
        return "You do not have permission to delete this pack", 403
    current_app.mdb.packs.delete_one({"_id": ObjectId(pack)})
    return "Pack deleted."


@items.route('/srd', methods=['GET'])
def srd_items():
    with open('static/template-items.json') as f:
        _items = json.load(f)
    return jsonify(_items)
