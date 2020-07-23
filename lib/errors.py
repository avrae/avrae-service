from bson.errors import InvalidId
from werkzeug.exceptions import HTTPException

from lib.utils import error


def register_error_handlers(app):
    @app.errorhandler(InvalidId)
    def invalid_id(e):
        return error(400, "invalid ID")

    @app.errorhandler(AvraeException)
    def avrae_exception(e):
        return error(400, str(e))

    # base error handler
    @app.errorhandler(HTTPException)
    def http_exception(e):
        return error(e.code, f"{e.name}: {e.description}")


class AvraeException(Exception):
    pass


class NotAllowed(AvraeException):
    pass
