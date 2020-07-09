import datetime

import jwt
from flask import Blueprint, request
from requests import HTTPError

import config
from lib.discord import exchange_code, fetch_user_info, handle_token_response
from lib.utils import error, jsonify, success

discord = Blueprint('discord', __name__)


@discord.route("users/<user_id>", methods=["GET"])
def get_user(user_id):
    """
    GET /discord/users/:id

    Returns:
    (UserInfo)
    """
    return jsonify(fetch_user_info(user_id).to_dict())


@discord.route("auth", methods=["POST"])
def handle_auth():
    """
    POST /discord/auth
    Content-Type: application/json

    {"code": str}

    Returns:
    {"success": bool, "data": {"jwt": str}, "error": str}
    """
    data = request.json
    if data is None:
        return error(400, "missing body")
    if 'code' not in data:
        return error(400, f"code is required")
    if not isinstance(data['code'], str):
        return error(400, f"code must be str")

    try:
        access_token_resp = exchange_code(data['code'])
        _, user = handle_token_response(access_token_resp)
    except HTTPError as e:
        if 400 <= e.response.status_code < 500:
            return error(e.response.status_code, str(e))
        return error(500, str(e))

    token = jwt.encode(
        {
            'iss': 'avrae.io',
            'aud': 'avrae.io',
            'iat': datetime.datetime.now(),
            'id': str(user.id),
            'username': user.username,
            'discriminator': user.discriminator,
            'avatar': user.avatar
        },
        config.JWT_SECRET, algorithm='HS256')

    return success({'jwt': token.decode()})  # token is str
