import json

from flask import Blueprint, current_app, request

from lib.auth import requires_auth
from lib.utils import error, jsonify, success
from lib.validation import is_valid_automation

characters = Blueprint('characters', __name__)


@characters.route('', methods=["GET"])
@requires_auth
def character_list(user):
    data = list(current_app.mdb.characters.find({"owner": user.id}))
    return jsonify(data)


@characters.route('/meta', methods=["GET"])
@requires_auth
def meta(user):
    data = list(current_app.mdb.characters.find({"owner": user.id},
                                                ["upstream", "active", "name", "description", "image", "levels",
                                                 "import_version", "overrides"]))
    return jsonify(data)


@characters.route('/<upstream>/attacks', methods=["GET"])
@requires_auth
def attacks(user, upstream):
    """Returns a character's overriden attacks."""
    data = current_app.mdb.characters.find_one({"owner": user.id, "upstream": upstream},
                                               ["overrides"])
    return jsonify(data['overrides']['attacks'])


@characters.route('/<upstream>/attacks', methods=["PUT"])
@requires_auth
def put_attacks(user, upstream):
    """Sets a character's attack overrides. Must PUT a list of attacks."""
    the_attacks = request.json

    # validation
    try:
        _validate_attacks(the_attacks)
    except ValidationError as e:
        return error(400, str(e))

    # write
    response = current_app.mdb.characters.update_one(
        {"owner": user.id, "upstream": upstream},
        {"$set": {"overrides.attacks": the_attacks}}
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
        _validate_attacks(reqdata)
    except ValidationError as e:
        return error(400, str(e))

    return success("OK")


@characters.route('/attacks/srd', methods=['GET'])
def srd_attacks():
    with open('static/template-attacks.json') as f:
        _items = json.load(f)
    return jsonify(_items)


# ==== helpers ====
class ValidationError(Exception):
    pass


REQUIRED_ATTACK_KEYS = {"name", "automation", "_v"}
OPTIONAL_ATTACK_KEYS = {"proper", "verb", "criton", "phrase", "thumb", "extra_crit_damage"}


def _validate_attacks(the_attacks):
    if not isinstance(the_attacks, list):
        raise ValidationError("Attacks must be a list")

    template = "Invalid attack ({0}): {1}"

    for i, attack in enumerate(the_attacks):
        if not isinstance(attack, dict):
            raise ValidationError(template.format(i, "attack is not an object"))

        keys = set(attack.keys())
        if not (keys.issuperset(REQUIRED_ATTACK_KEYS) and keys.issubset(REQUIRED_ATTACK_KEYS | OPTIONAL_ATTACK_KEYS)):
            raise ValidationError(template.format(i, "attack object missing keys"))

        valid, why = is_valid_automation(attack['automation'])
        if not valid:
            raise ValidationError(template.format(i, f"invalid automation: {why}"))
