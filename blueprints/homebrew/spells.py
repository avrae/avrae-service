import json

from bson import ObjectId
from flask import Blueprint, current_app, request, app

from lib.discord import get_user_info
from lib.utils import jsonify
from lib.validation import ValidationError, check_automation, ensure_spell_keys
from .helpers import user_can_edit, user_can_view, user_editable, user_is_owner

spells = Blueprint('homebrew/spells', __name__)

TOME_FIELDS = {"name", "public", "desc", "image", "spells"}
SPELL_FIELDS = ("name", "level", "school", "classes", "subclasses", "casttime", "range", "components", "duration",
                "ritual", "description", "higherlevels", "concentration", "automation", "image")
IGNORED_FIELDS = {"_id", "active", "server_active", "subscribers", "editors", "owner", "numSpells"}


def _is_owner(user, obj_id):
    return user_is_owner(data_coll=current_app.mdb.tomes, user=user, obj_id=obj_id)


def _can_view(user, obj_id):
    return user_can_view(data_coll=current_app.mdb.tomes, sub_coll=current_app.mdb.tome_subscriptions, user=user,
                         obj_id=obj_id)


def _can_edit(user, obj_id):
    return user_can_edit(data_coll=current_app.mdb.tomes, sub_coll=current_app.mdb.tome_subscriptions, user=user,
                         obj_id=obj_id)


def _editable(user):
    return user_editable(data_coll=current_app.mdb.tomes, sub_coll=current_app.mdb.tome_subscriptions, user=user)


@spells.route('/me', methods=['GET'])
def user_tomes():
    user = get_user_info()
    data = list(_editable(user))
    for tome in data:
        tome['numSpells'] = len(tome['spells'])
        tome['owner'] = str(tome['owner'])
        del tome['spells']
    return jsonify(data)


@spells.route('', methods=['POST'])
def new_tome():
    user = get_user_info()
    reqdata = request.json
    if reqdata is None:
        return "No data found", 400
    if 'name' not in reqdata:
        return "Missing name field", 400
    tome = {
        'name': reqdata['name'],
        'public': bool(reqdata.get('public', False)),
        'desc': reqdata.get('desc', ''),
        'image': reqdata.get('image', ''),
        'owner': int(user.id),
        'spells': []
    }
    result = current_app.mdb.tomes.insert_one(tome)
    data = {"success": True, "tomeId": str(result.inserted_id)}
    return jsonify(data)


@spells.route('/<tome>', methods=['GET'])
def get_tome(tome):
    user = None
    if 'Authorization' in request.headers:
        user = get_user_info()
    data = current_app.mdb.tomes.find_one({"_id": ObjectId(tome)})
    if data is None:
        return "Tome not found", 404
    if not _can_view(user, ObjectId(tome)):
        return "You do not have permission to view this tome", 403
    data['owner'] = str(data['owner'])
    return jsonify(data)


@spells.route('/<tome>', methods=['PUT'])
def put_tome(tome):
    user = get_user_info()
    reqdata = request.json
    if not _can_edit(user, ObjectId(tome)):
        return "You do not have permission to edit this tome", 403

    for field in IGNORED_FIELDS:
        if field in reqdata:
            reqdata.pop(field)

    if not all(k in TOME_FIELDS for k in reqdata):
        return f"Invalid fields: {set(reqdata).difference(TOME_FIELDS)}", 400
    if "spells" in reqdata:
        for spell in reqdata['spells']:
            if not all(k in SPELL_FIELDS for k in spell):
                return f"Invalid spell field in {spell}", 400
            try:
                validate(spell)
            except ValidationError as e:
                return str(e), 400

    current_app.mdb.tomes.update_one({"_id": ObjectId(tome)}, {"$set": reqdata})
    return "Tome updated."


@spells.route('/<tome>', methods=['DELETE'])
def delete_tome(tome):
    user = get_user_info()
    if not _is_owner(user, ObjectId(tome)):
        return "You do not have permission to delete this tome", 403
    current_app.mdb.tomes.delete_one({"_id": ObjectId(tome)})
    return "Tome deleted."


@spells.route('/<tome>/editors', methods=['GET'])
def get_tome_editors(tome):
    user = get_user_info()
    if not _can_view(user, ObjectId(tome)):
        return "You do not have permission to view this tome", 403

    data = [str(sd['subscriber_id']) for sd in
            current_app.mdb.tome_subscriptions.find({"type": "editor", "object_id": ObjectId(tome)})]

    return jsonify(data)


@spells.route('/srd', methods=['GET'])
def srd_spells():
    with open('static/template-spells.json') as f:
        _spells = json.load(f)
    return jsonify(_spells)


@spells.route('/validate', methods=['POST'])
def validate_import():
    reqdata = request.json
    if not isinstance(reqdata, list):
        reqdata = [reqdata]
    for spell in reqdata:
        try:
            validate(spell)
        except ValidationError as e:
            return str(e), 400
    return jsonify({'success': True, 'result': "OK"})


def validate(spell):
    try:
        ensure_spell_keys(spell)
        if spell['automation'] is not None:
            check_automation(spell['automation'])
    except AssertionError as e:
        raise ValidationError(str(e))
