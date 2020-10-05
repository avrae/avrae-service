import datetime

import jwt
from flask import Blueprint, request
from requests import HTTPError

import config
from lib.auth import requires_auth
from lib.discord import discord_token_for, exchange_code, fetch_user_info, get_current_user_guilds, \
    handle_token_response, search_by_username
from lib.utils import error, expect_json, jsonify, success

discord = Blueprint('discord', __name__)


@discord.route("users/<user_id>", methods=["GET"])
def get_user(user_id):
    """
    GET /discord/users/:id

    Returns:
    (UserInfo)
    """
    return jsonify(fetch_user_info(user_id).to_dict())


@discord.route("users", methods=["GET"])
@requires_auth
def search_user(_):
    """
    GET /discord/users?username=foo#0000
    """
    if 'username' not in request.args:
        return error(400, "username param is required")
    un = request.args['username']
    if '#' not in un:
        return error(400, "username must be username#discrim")
    username, discriminator = un.rsplit('#', 1)
    user = search_by_username(username, discriminator)
    if user is not None:
        return success(user.to_dict(), 200)
    return error(404, "user not found")


@discord.route("guilds", methods=["GET"])
@requires_auth
def get_user_guilds(user):
    guilds = get_current_user_guilds(user.id)
    return success(guilds)


@discord.route("auth", methods=["POST"])
@expect_json(code=str)
def handle_auth(data):
    """
    POST /discord/auth
    Content-Type: application/json

    {"code": str}

    Returns:
    {"success": bool, "data": {"jwt": str}, "error": str}
    """
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
