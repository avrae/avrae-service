from bson.json_util import dumps
from flask import Response


def jsonify(data, status=200):
    return Response(dumps(data), status=status, mimetype="application/json")


def success(data, status=200):
    return jsonify({
        "success": True,
        "data": data
    }, status)


def error(status: int, message: str = None):
    return jsonify({
        "success": False,
        "error": message
    }, status)
