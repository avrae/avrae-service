import json
from typing import Optional

from flask import Blueprint, current_app, request
from pydantic import BaseModel, Field, ValidationError, constr

from lib.auth import requires_auth
from lib.utils import error, jsonify, success
from lib.validation import Automation, str1024, str255, parse_validation_error

characters = Blueprint('characters', __name__)


@characters.route('', methods=["GET"])
@requires_auth
def character_list(user):
    data = list(current_app.mdb.characters.find({"owner": user.id}))
    return jsonify(data)


@characters.route('/meta', methods=["GET"])
@requires_auth
def meta(user):
    data = list(
        current_app.mdb.characters.find(
            {"owner": user.id},
            ["upstream", "active", "name", "description", "image", "levels",
             "import_version", "overrides"]
        )
    )
    return jsonify(data)


@characters.route('/<upstream>/attacks', methods=["GET"])
@requires_auth
def attacks(user, upstream):
    """Returns a character's overriden attacks."""
    data = current_app.mdb.characters.find_one(
        {"owner": user.id, "upstream": upstream},
        ["overrides"]
    )
    return jsonify(data['overrides']['attacks'])


@characters.route('/<upstream>/attacks', methods=["PUT"])
@requires_auth
def put_attacks(user, upstream):
    """Sets a character's attack overrides. Must PUT a list of attacks."""
    the_attacks = request.json

    # validation
    try:
        validated_attacks = [Attack.parse_obj(a) for a in the_attacks]
    except ValidationError as e:
        e = parse_validation_error(the_attacks, 'attacks', e)
        return error(400, str(e))

    # write
    response = current_app.mdb.characters.update_one(
        {"owner": user.id, "upstream": upstream},
        {"$set": {"overrides.attacks": [a.dict(exclude_none=True, exclude_defaults=True) for a in validated_attacks]}}
    )

    # respond
    if not response.matched_count:
        return error(404, "Character not found")
    return success("Attacks updated")


@characters.route('/attacks/validate', methods=["POST"])
def validate_attacks():
    reqdata = request.json
    if not isinstance(reqdata, list):
        reqdata = [reqdata]

    try:
        [Attack.parse_obj(a) for a in reqdata]
    except ValidationError as e:
        e = parse_validation_error(the_attacks, 'attacks', json.loads(e.json()))
        return error(400, str(e))

    return success("OK")


@characters.route('/attacks/srd', methods=['GET'])
def srd_attacks():
    with open('static/template-attacks.json') as f:
        _items = json.load(f)
    return jsonify(_items)


# ==== helpers ====
class Attack(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=255)
    automation: Automation
    v: int = Field(alias="_v")
    proper: Optional[bool]
    verb: Optional[str255] = ""  # these empty strings are here for exclude_defaults
    criton: Optional[int]
    phrase: Optional[str1024] = ""
    thumb: Optional[str1024] = ""
    extra_crit_damage: Optional[str255] = ""

    def dict(self, *args, **kwargs):
        return super().dict(*args, by_alias=True, **kwargs)
