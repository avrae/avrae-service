from flask import Blueprint

from lib.discord import UserInfo, fetch_user_info, get_user_info
from lib.utils import jsonify

discord = Blueprint('discord', __name__)


@discord.route("users/<user_id>", methods=["GET"])
def get_user(user_id):
    return jsonify(fetch_user_info(user_id).to_dict())
