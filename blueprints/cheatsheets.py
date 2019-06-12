import json
import string

from flask import Blueprint

from lib.utils import jsonify

cheatsheets = Blueprint('cheatsheets', __name__)


@cheatsheets.route('', methods=['GET'])
def list_cheatsheets():
    with open("static/cheatsheets.json") as f:
        data = json.load(f)
    return jsonify(data)


@cheatsheets.route('<title>', methods=['GET'])
def get_cheatsheet(title):
    if not set(title).issubset(string.ascii_letters):  # oi, bad
        return "Invalid cheatsheet name", 400
    try:
        with open(f"static/cheatsheets/{title}.md") as f:
            return f.read(), 200
    except FileNotFoundError:
        return "Cheatsheet not found", 404
