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


@characters.route("<upstream>/consumables", methods=["GET"])
@requires_auth
def counters(user, upstream):
    """Returns a characters consumables"""
    data = current_app.mdb.characters.find_one({"owner": user.id, "upstream": upstream}, ["consumables"])
    return jsonify(data["consumables"])


@characters.route("<upstream>/consumables", methods=["POST"])
@requires_auth
def add_consumable(user, upstream):
    """Adds a consumable to a character's consumables list"""
    new_item = request.json

    if new_item is None:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    error = validate_consumable(new_item)
    if error:
        return jsonify({"error": error}), 400

    result = current_app.mdb.characters.update_one(
        {"owner": user.id, "upstream": upstream},
        {"$push": {"consumables": new_item}},
    )

    if result.matched_count == 0:
        return jsonify({"error": "Character not found"}), 404

    return success("Consumables updated!")


STR_FIELDS = {
    "name",
    "minv",
    "maxv",
    "display_type",
    "reset",
    "reset_to",
    "reset_by",
    "title",
    "desc",
}
NUMERIC_FIELDS = {"value"}
ALWAYS_NONE_FIELDS = {"ddb_source_feature_id", "ddb_source_feature_type", "live_id"}

ALL_FIELDS = STR_FIELDS | ALWAYS_NONE_FIELDS | NUMERIC_FIELDS


def validate_consumable(item):
    """Returns an error string if invalid, otherwise None"""
    if not isinstance(item, dict):
        return "Item must be a JSON object"

    missing = ALL_FIELDS - item.keys()
    if missing:
        return f"Missing required fields: {', '.join(missing)}"

    unknown = item.keys() - ALL_FIELDS
    if unknown:
        return f"Unknown fields: {', '.join(unknown)}"

    for field in STR_FIELDS:
        if item[field] is not None and not isinstance(item[field], str):
            return f"Field '{field}' must be a string or null"

    for field in NUMERIC_FIELDS:
        value = item[field]
        if not isinstance(value, int) or isinstance(value, bool):
            return f"Field '{field}' must be a number (not null)"

    for field in ALWAYS_NONE_FIELDS:
        if item[field] is not None:
            return f"Field '{field}' must always be null"

    return None
