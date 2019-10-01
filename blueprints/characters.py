from bson import ObjectId
from flask import Blueprint, request

from app import mdb
from lib.discord import get_user_info
from lib.utils import jsonify
from lib.validation import is_valid_automation

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
                                    ["upstream", "active", "name", "description", "image", "levels"]))
    return jsonify(data)


@characters.route('/<_id>/attacks', methods=["GET"])
def attacks(_id):
    """Returns a character's overriden attacks."""
    user = get_user_info()
    char_id = ObjectId(_id)
    data = mdb.characters.find_one({"owner": user.id, "_id": char_id},
                                   ["overrides"])
    return jsonify(data['attacks'])


@characters.route('/<_id>/attacks', methods=["POST"])
def put_attacks(_id):
    """Sets a character's attack overrides. Must POST a list of attacks."""
    user = get_user_info()
    char_id = ObjectId(_id)

    the_attacks = request.json

    # validation
    if not isinstance(the_attacks, list):
        return "Attacks must be a list", 400

    for attack in the_attacks:
        if not all((isinstance(attack, dict),
                    set(attack.keys()) == {"name", "automation"},
                    is_valid_automation(attack['automation']))):
            return "Invalid attack", 400

    # write
    response = mdb.characters.update_one(
        {"owner": user.id, "_id": char_id},
        {"$set": {"overrides.attacks": the_attacks}}
    )

    # respond
    if not response.modified_count:
        return "Character not found", 404
    return "Attacks updated."
