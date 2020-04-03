from bson.errors import InvalidId

from lib.utils import jsonify


def register_error_handlers(app):

    @app.errorhandler(InvalidId)
    def invalid_id(e):
        return jsonify({"error": "invalid ID"}), 400
