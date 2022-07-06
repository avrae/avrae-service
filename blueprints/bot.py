import base64
import enum
import hashlib
import hmac
import struct
from functools import wraps

from flask import Blueprint, abort, current_app, request

import config
from lib.utils import error, expect_json, jsonify, success

bot = Blueprint("bot", __name__)


def requires_secret(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app_3pp_secret = request.headers.get("authorization")
        if current_app.mdb.api_apps.find_one({"key": app_3pp_secret}) is None:
            return abort(403)
        return f(*args, **kwargs)

    return decorated_function


@bot.route("characters/<user>/active", methods=["GET"])
@requires_secret
def active_char(user):
    char = current_app.mdb.characters.find_one({"owner": user, "active": True})
    if char is None:
        return "User has no character active, or user does not exist", 404
    return jsonify(char)


@bot.route("characters/<user>/<_id>", methods=["GET"])
@requires_secret
def user_char(user, _id):
    char = current_app.mdb.characters.find_one({"owner": user, "upstream": _id})
    if char is None:
        return "Character not found", 404
    return jsonify(char)


# ==== signature verification ===
# copied from avrae/aliasing.api.functions
SIG_SECRET = config.DRACONIC_SIGNATURE_SECRET
SIG_STRUCT = struct.Struct("!QQQ12sB")  # u64, u64, u64, byte[12], u8 - https://docs.python.org/3/library/struct.html
SIG_HASH_ALG = hashlib.sha1  # SHA1 is technically compromised but the hash collision attack vector is not feasible here
DISCORD_EPOCH = 1420070400000


class ExecutionScope(enum.IntEnum):
    # note: all values must be within [0..7] to fit in signature()
    UNKNOWN = 0
    PERSONAL_ALIAS = 1
    SERVER_ALIAS = 2
    PERSONAL_SNIPPET = 3
    SERVER_SNIPPET = 4
    COMMAND_TEST = 5


@bot.route("signature/verify", methods=["POST"])
@expect_json(signature=str)
def verify_signature(body):
    data = body["signature"]
    # decode
    try:
        encoded_data, encoded_signature = data.split(".", 1)
        decoded_data = base64.b64decode(encoded_data, validate=True)
        decoded_signature = base64.b64decode(encoded_signature, validate=True)
        message_id, channel_id, author_id, object_id, tail_byte = SIG_STRUCT.unpack(decoded_data)
    except (ValueError, struct.error):
        return error(400, "Failed to unpack signature: invalid format")

    # verify
    verification = hmac.new(SIG_SECRET, decoded_data + SIG_SECRET, SIG_HASH_ALG)
    is_valid = hmac.compare_digest(decoded_signature, verification.digest())
    if not is_valid:
        return error(400, "Failed to verify signature: invalid signature")

    # resolve
    timestamp = ((message_id >> 22) + DISCORD_EPOCH) / 1000
    execution_scope = ExecutionScope(tail_byte & 0x07)
    user_data = (tail_byte & 0xF8) >> 3
    collection_id = object_id.hex() if any(object_id) else None  # bytes is an iterable of int, check if it's all 0

    return success(
        {
            "message_id": message_id,
            "channel_id": channel_id,
            "author_id": author_id,
            "timestamp": timestamp,
            "scope": execution_scope.name,
            "user_data": user_data,
            "workshop_collection_id": collection_id,
        }
    )
