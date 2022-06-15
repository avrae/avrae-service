import json
from typing import List

import automation_common
import pydantic
from flask import Blueprint, current_app, request
from pydantic import ValidationError

from lib.auth import requires_auth
from lib.utils import error, jsonify, success
from lib.validation import parse_validation_error

characters = Blueprint("characters", __name__)


@characters.route("", methods=["GET"])
@requires_auth
def character_list(user):
    data = list(current_app.mdb.characters.find({"owner": user.id}))
    return jsonify(data)


@characters.route("/meta", methods=["GET"])
@requires_auth
def meta(user):
    data = list(
        current_app.mdb.characters.find(
            {"owner": user.id},
            ["upstream", "active", "name", "description", "image", "levels", "import_version", "overrides"],
        )
    )
    return jsonify(data)


@characters.route("/<upstream>/attacks", methods=["GET"])
@requires_auth
def attacks(user, upstream):
    """Returns a character's overriden attacks."""
    data = current_app.mdb.characters.find_one({"owner": user.id, "upstream": upstream}, ["overrides"])
    return jsonify(data["overrides"]["attacks"])


@characters.route("/<upstream>/attacks", methods=["PUT"])
@requires_auth
def put_attacks(user, upstream):
    """Sets a character's attack overrides. Must PUT a list of attacks."""
    the_attacks = request.json

    # validation/normalizae
    try:
        normalized_obj = pydantic.parse_obj_as(
            List[automation_common.validation.models.AttackModel], the_attacks, type_name="AttackList"
        )
    except ValidationError as e:
        e = parse_validation_error(the_attacks, e)
        return error(400, str(e))

    # write
    response = current_app.mdb.characters.update_one(
        {"owner": user.id, "upstream": upstream},
        {"$set": {"overrides.attacks": [a.dict(exclude_none=True, exclude_defaults=True) for a in normalized_obj]}},
    )

    # respond
    if not response.matched_count:
        return error(404, "Character not found")
    return success("Attacks updated")


@characters.route("/attacks/validate", methods=["POST"])
def validate_attacks():
    reqdata = request.json
    if not isinstance(reqdata, list):
        reqdata = [reqdata]

    try:
        pydantic.parse_obj_as(List[automation_common.validation.models.AttackModel], reqdata, type_name="AttackList")
    except ValidationError as e:
        e = parse_validation_error(reqdata, e)
        return error(400, str(e))

    return success("OK")


@characters.route("/attacks/srd", methods=["GET"])
def srd_attacks():
    with open("static/template-attacks.json") as f:
        _items = json.load(f)
    return jsonify(_items)
