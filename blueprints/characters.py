from flask import Blueprint, current_app, request

from lib.discord import get_user_info
from lib.utils import jsonify
from lib.validation import is_valid_automation

characters = Blueprint('characters', __name__)


@characters.route('', methods=["GET"])
def character_list():
    user = get_user_info()
    data = list(current_app.mdb.characters.find({"owner": user.id}))
    return jsonify(data)


@characters.route('/meta', methods=["GET"])
def meta():
    user = get_user_info()
    data = list(current_app.mdb.characters.find({"owner": user.id},
                                    ["upstream", "active", "name", "description", "image", "levels", "import_version"]))
    return jsonify(data)


@characters.route('/<upstream>/attacks', methods=["GET"])
def attacks(upstream):
    """Returns a character's overriden attacks."""
    user = get_user_info()
    data = current_app.mdb.characters.find_one({"owner": user.id, "upstream": upstream},
                                   ["overrides"])
    return jsonify(data['overrides']['attacks'])


@characters.route('/<upstream>/attacks', methods=["PUT"])
def put_attacks(upstream):
    """Sets a character's attack overrides. Must PUT a list of attacks."""
    user = get_user_info()
    the_attacks = request.json

    # validation
    try:
        _validate_attacks(the_attacks)
    except ValidationError as e:
        return str(e), 400

    # write
    response = current_app.mdb.characters.update_one(
        {"owner": user.id, "upstream": upstream},
        {"$set": {"overrides.attacks": the_attacks}}
    )

    # respond
    if not response.matched_count:
        return "Character not found", 404
    return "Attacks updated."


@characters.route('/attacks/validate', methods=["POST"])
def validate_attacks():
    reqdata = request.json
    if not isinstance(reqdata, list):
        reqdata = [reqdata]

    try:
        _validate_attacks(reqdata)
    except ValidationError as e:
        return str(e), 400

    return jsonify({'success': True, 'result': "OK"})


class ValidationError(Exception):
    pass


REQUIRED_ATTACK_KEYS = {"name", "automation", "_v"}
OPTIONAL_ATTACK_KEYS = {"proper", "verb"}


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
