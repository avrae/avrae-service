from bson import ObjectId
from flask import Blueprint

from app import mdb
from lib.discord import get_user_info
from lib.utils import jsonify

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


@characters.route('/<_id>/options', methods=["GET"])
def options(_id):
    user = get_user_info()
    char_id = ObjectId(_id)
    data = list(mdb.characters.find({"owner": user.id, "_id": char_id},
                                    ["options", "overrides"]))
    return jsonify(data)
