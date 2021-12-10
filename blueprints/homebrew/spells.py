import json
from typing import List, Optional, Union

from bson import ObjectId
from flask import Blueprint, current_app, request
from pydantic import BaseModel, HttpUrl, ValidationError, conint, constr

from lib.auth import maybe_auth, requires_auth
from lib.utils import error, expect_json, success
from lib.validation import Automation, str1024, str255, str4096, parse_validation_error
from .helpers import user_can_edit, user_can_view, user_editable, user_is_owner

spells = Blueprint('homebrew/spells', __name__)


# ==== helpers ====
def _is_owner(user, obj_id):
    return user_is_owner(data_coll=current_app.mdb.tomes, user=user, obj_id=obj_id)


def _can_view(user, obj_id):
    return user_can_view(
        data_coll=current_app.mdb.tomes, sub_coll=current_app.mdb.tome_subscriptions, user=user,
        obj_id=obj_id
    )


def _can_edit(user, obj_id):
    return user_can_edit(
        data_coll=current_app.mdb.tomes, sub_coll=current_app.mdb.tome_subscriptions, user=user,
        obj_id=obj_id
    )


def _editable(user):
    return user_editable(data_coll=current_app.mdb.tomes, sub_coll=current_app.mdb.tome_subscriptions, user=user)


# ==== routes ====
@spells.route('/me', methods=['GET'])
@requires_auth
def user_tomes(user):
    data = list(_editable(user))
    for tome in data:
        tome['numSpells'] = len(tome['spells'])
        tome['owner'] = str(tome['owner'])
        del tome['spells']
    return success(data)


@spells.route('', methods=['POST'])
@requires_auth
def new_tome(user):
    reqdata = request.json
    if reqdata is None:
        return error(400, "No data found")
    if 'name' not in reqdata:
        return error(400, "missing name field")
    tome = {
        'name': reqdata['name'],
        'public': bool(reqdata.get('public', False)),
        'desc': reqdata.get('desc', ''),
        'image': reqdata.get('image', ''),
        'owner': int(user.id),
        'spells': []
    }
    result = current_app.mdb.tomes.insert_one(tome)
    data = {"tomeId": str(result.inserted_id)}
    return success(data)


@spells.route('/<tome>', methods=['GET'])
@maybe_auth
def get_tome(user, tome):
    data = current_app.mdb.tomes.find_one({"_id": ObjectId(tome)})
    if data is None:
        return error(404, "Tome not found")
    if not _can_view(user, ObjectId(tome)):
        return error(403, "You do not have permission to view this tome")
    data['owner'] = str(data['owner'])
    return success(data)


@spells.route('/<tome>', methods=['PUT'])
@requires_auth
def put_tome(user, tome):
    reqdata = request.json
    if not _can_edit(user, ObjectId(tome)):
        return error(403, "You do not have permission to edit this tome")

    try:
        the_tome = Tome.parse_obj(reqdata)
    except ValidationError as e:
        e = parse_validation_error(reqdata, 'spells', json.loads(e.json()))
        return error(400, str(e))

    current_app.mdb.tomes.update_one({"_id": ObjectId(tome)}, {"$set": the_tome.dict(exclude_unset=True)})
    return success("Tome updated.")


@spells.route('/<tome>', methods=['DELETE'])
@requires_auth
def delete_tome(user, tome):
    if not _is_owner(user, ObjectId(tome)):
        return error(403, "You do not have permission to edit this tome")
    current_app.mdb.tomes.delete_one({"_id": ObjectId(tome)})
    current_app.mdb.tome_subscriptions.delete_many({"object_id": ObjectId(tome)})
    return success("Tome updated.")


@spells.route('/<tome>/sharing', methods=['PATCH'])
@expect_json(public=bool)
@requires_auth
def update_tome_sharing(user, data, tome):
    if not _can_edit(user, ObjectId(tome)):
        return error(403, "You do not have permission to edit this tome")

    current_app.mdb.tomes.update_one({"_id": ObjectId(tome)}, {"$set": {"public": data['public']}})
    return success("Tome updated.")


@spells.route('/<tome>/editors', methods=['GET'])
@requires_auth
def get_tome_editors(user, tome):
    if not _can_view(user, ObjectId(tome)):
        return error(403, "You do not have permission to view this tome")

    data = [str(sd['subscriber_id']) for sd in
            current_app.mdb.tome_subscriptions.find({"type": "editor", "object_id": ObjectId(tome)})]

    return success(data)


@spells.route('/srd', methods=['GET'])
def srd_spells():
    with open('static/template-spells.json') as f:
        _spells = json.load(f)
    return success(_spells)


@spells.route('/validate', methods=['POST'])
def validate_import():
    reqdata = request.json
    if not isinstance(reqdata, list):
        reqdata = [reqdata]
    for spell in reqdata:
        try:
            Spell.parse_obj(spell)
        except ValidationError as e:
            return error(400, str(e))
    return success({'result': "OK"})


# ==== Validation ====
class SpellComponents(BaseModel):
    verbal: bool
    somatic: bool
    material: Optional[str255]


class Spell(BaseModel):
    name: str255
    level: conint(ge=0, le=9)
    school: str255
    automation: Optional[Automation]
    classes: Optional[str255]
    subclasses: Optional[str255]
    casttime: Optional[str255]
    range: Optional[str255]
    components: Optional[SpellComponents]
    duration: Optional[str255]
    ritual: Optional[bool]
    description: Optional[str4096]
    higherlevels: Optional[str1024]
    concentration: Optional[bool]
    image: Optional[Union[HttpUrl, constr(max_length=0)]]  # image might be an empty string


class Tome(BaseModel):
    name: str255
    public: bool
    desc: str4096
    image: Optional[Union[HttpUrl, constr(max_length=0)]]
    spells: List[Spell]
