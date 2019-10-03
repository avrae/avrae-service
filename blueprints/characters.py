from bson import ObjectId
from flask import Blueprint, request

from app import mdb
from lib.discord import get_user_info
from lib.utils import jsonify
from lib.validation import is_valid_automation, check_automation

characters = Blueprint('characters', __name__)


@characters.route('', methods=["GET"])
def character_list():
    user = get_user_info()
    data = list(mdb.characters.find({"owner": user.id}))
    return jsonify(data)


@characters.route('/meta', methods=["GET"])
def meta():
    user = get_user_info()
    data = list(mdb.characters.find({"owner": user.id},
                                    ["upstream", "active", "name", "description", "image", "levels", "import_version"]))
    return jsonify(data)


@characters.route('/<upstream>/attacks', methods=["GET"])
def attacks(upstream):
    """Returns a character's overriden attacks."""
    user = get_user_info()
    data = mdb.characters.find_one({"owner": user.id, "upstream": upstream},
                                   ["overrides"])
    return jsonify(data['overrides']['attacks'])


@characters.route('/<upstream>/attacks', methods=["PUT"])
def put_attacks(upstream):
    """Sets a character's attack overrides. Must PUT a list of attacks."""
    user = get_user_info()
    the_attacks = request.json

    # validation
    if not isinstance(the_attacks, list):
        return "Attacks must be a list", 400

    for attack in the_attacks:
        if not all((isinstance(attack, dict),
                    set(attack.keys()) == {"name", "automation", "_v"},
                    is_valid_automation(attack['automation']))):
            return "Invalid attack", 400

    # write
    response = mdb.characters.update_one(
        {"owner": user.id, "upstream": upstream},
        {"$set": {"overrides.attacks": the_attacks}}
    )

    # respond
    if not response.matched_count:
        return "Character not found", 404
    return "Attacks updated."
