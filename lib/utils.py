import datetime
import functools
import json

from bson import ObjectId
from bson.json_util import dumps
from flask import Response, request


def jsonify(data, status=200):
    return Response(dumps(data), status=status, mimetype="application/json")


class HelperEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime.datetime):
            dt = o.isoformat()
            if o.utcoffset() is None:  # BSON returns utc timestamps, without tzinfo
                dt += 'Z'
            return dt
        return super().default(o)


def new_jsonify(data, status=200):
    """
    Like jsonify, but handles BSON objects (ObjectId, datetime) better.

    ObjectId -> str
    datetime -> ISO8601 str
    """
    return Response(json.dumps(data, cls=HelperEncoder), status=status, mimetype="application/json")


def success(data, status=200):
    return new_jsonify({
        "success": True,
        "data": data
    }, status)


def error(status: int, message: str = None):
    return new_jsonify({
        "success": False,
        "error": message
    }, status)


def expect_json(*, strict=False, **fields):
    """
    Returns a wrapper that enforces the presence of a JSON body, and the presence of certain fields in that body.
    Passes the JSON body as the first argument to the inner.

    If a field is missing or has the wrong type, returns 400.

    :param bool strict: Whether *only* the fields defined in *fields* are allowed.
    :param fields: A mapping of field->type of expected fields.
    :type fields: type
    """

    def wrapper(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            # ensure correct mimetype
            if not request.is_json:
                return error(400, "expected json body")

            # ensure body exists
            body = request.get_json(silent=True)  # return None on error
            if body is None:
                return error(400, "missing or invalid body")

            # ensure fields are present
            if strict:
                if set(fields) != set(body):
                    return error(400, f"invalid body fields: expected {list(fields)}, got {list(body)}")
            else:
                if not set(fields).issubset(body):
                    return error(400, f"missing body fields: {list(set(fields).difference(body))}")

            # check field types
            for field, e_type in fields.items():
                if not isinstance(body[field], e_type):
                    return error(400, f"expected {field} to be {e_type.__name__}")

            # everything is good!
            return func(body, *args, **kwargs)

        return inner

    return wrapper


def maybe_json(**jkwargs):
    """
    Returns a wrapper that enforces the presence of certain fields in a JSON body, if a body is present.
    Passes the JSON body as the first argument to the inner, or None if there is no body.

    If a field is missing or has the wrong type, returns 400.
    """

    def wrapper(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            if request.content_length == 0:
                return func(None, *args, **kwargs)
            return expect_json(**jkwargs)(func)(*args, **kwargs)

        return inner

    return wrapper


def nullable(t: type):
    """A helper function for type checking - type *t* or None."""
    return t, type(None)
