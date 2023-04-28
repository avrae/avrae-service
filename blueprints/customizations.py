import uuid

from flask import Blueprint, current_app, request

from lib.auth import requires_auth
from lib.utils import jsonify
from workshop.constants import SNIPPET_SIZE_LIMIT, ALIAS_SIZE_LIMIT, UVAR_SIZE_LIMIT, GVAR_SIZE_LIMIT

customizations = Blueprint("customizations", __name__)


@customizations.route("", methods=["GET"])
@requires_auth
def customization_list(user):
    data = {
        "aliases": list(current_app.mdb.aliases.find({"owner": user.id})),
        "snippets": list(current_app.mdb.snippets.find({"owner": user.id})),
        "uvars": list(current_app.mdb.uvars.find({"owner": user.id})),
    }
    return jsonify(data)


@customizations.route("/aliases", methods=["GET"])
@requires_auth
def alias_list(user):
    data = list(current_app.mdb.aliases.find({"owner": user.id}))
    return jsonify(data)


@customizations.route("/aliases/<name>", methods=["POST"])
@requires_auth
def alias_update(user, name):
    data = request.json
    if data is None:
        return "No data found", 400
    if "commands" not in data:
        return "Missing commands field", 400
    if not data["commands"]:
        return "Commands cannot be blank", 400
    if " " in name:
        return "Name cannot contain whitespace", 400
    if name in current_app.rdb.jget("default_commands", []):
        return "Alias is already built-in", 409
    if len(data["commands"]) > 4000:
        return "Alias commands must be less than 4KB", 400

    current_app.mdb.aliases.update_one(
        {"owner": user.id, "name": name}, {"$set": {"commands": data["commands"]}}, upsert=True
    )
    return "Alias updated."


@customizations.route("/aliases/<name>", methods=["DELETE"])
@requires_auth
def alias_delete(user, name):
    result = current_app.mdb.aliases.delete_one({"owner": user.id, "name": name})
    if not result.deleted_count:
        return "Alias not found.", 404
    return "Alias deleted."


@customizations.route("/snippets", methods=["GET"])
@requires_auth
def snippet_list(user):
    data = list(current_app.mdb.snippets.find({"owner": user.id}))
    return jsonify(data)


@customizations.route("/snippets/<name>", methods=["POST"])
@requires_auth
def snippet_update(user, name):
    data = request.json
    if data is None:
        return "No data found", 400
    if "snippet" not in data:
        return "Missing snippet field", 400
    if not data["snippet"]:
        return "Snippet cannot be blank", 400
    if " " in name:
        return "Name cannot contain whitespace", 400
    if len(data["snippet"]) > 2000:
        return "Snippet must be less than 2KB", 400
    if len(name) < 2:
        return "Name must be at least 2 characters", 400

    current_app.mdb.snippets.update_one(
        {"owner": user.id, "name": name}, {"$set": {"snippet": data["snippet"]}}, upsert=True
    )
    return "Snippet updated."


@customizations.route("/snippets/<name>", methods=["DELETE"])
@requires_auth
def snippet_delete(user, name):
    result = current_app.mdb.snippets.delete_one({"owner": user.id, "name": name})
    if not result.deleted_count:
        return "Snippet not found.", 404
    return "Snippet deleted."


@customizations.route("/uvars", methods=["GET"])
@requires_auth
def uvar_list(user):
    data = list(current_app.mdb.uvars.find({"owner": user.id}))
    return jsonify(data)


@customizations.route("/uvars/<name>", methods=["POST"])
@requires_auth
def uvar_update(user, name):
    data = request.json
    if data is None:
        return "No data found", 400
    if "value" not in data:
        return "Missing value field", 400
    if not data["value"]:
        return "Value cannot be blank", 400
    if len(data["value"]) > 4000:
        return "Value must be less than 4KB", 400

    current_app.mdb.uvars.update_one({"owner": user.id, "name": name}, {"$set": {"value": data["value"]}}, upsert=True)
    return "Uvar updated."


@customizations.route("/uvars/<name>", methods=["DELETE"])
@requires_auth
def uvar_delete(user, name):
    result = current_app.mdb.uvars.delete_one({"owner": user.id, "name": name})
    if not result.deleted_count:
        return "Uvar not found.", 404
    return "Uvar deleted."


@customizations.route("/gvars", methods=["GET"])
@requires_auth
def gvar_list(user):
    data = {
        "owned": list(current_app.mdb.gvars.find({"owner": user.id})),
        "editable": list(current_app.mdb.gvars.find({"editors": user.id})),
    }
    return jsonify(data)


@customizations.route("/gvars/owned", methods=["GET"])
@requires_auth
def gvar_list_owned(user):
    data = list(current_app.mdb.gvars.find({"owner": user.id}))
    return jsonify(data)


@customizations.route("/gvars/editable", methods=["GET"])
@requires_auth
def gvar_list_editable(user):
    data = list(current_app.mdb.gvars.find({"editors": user.id}))
    return jsonify(data)


@customizations.route("/gvars", methods=["POST"])
@requires_auth
def gvar_new(user):
    data = request.json
    if data is None:
        return "No data found", 400
    if "value" not in data:
        return "Missing value field", 400
    if len(data["value"]) > 100000:
        return "Gvars must be less than 100KB", 400
    key = str(uuid.uuid4())
    gvar = {
        "owner": user.id,
        "key": key,
        "owner_name": f"{user.username}#{user.discriminator}",
        "value": data["value"],
        "editors": [],
    }
    current_app.mdb.gvars.insert_one(gvar)
    return f"Gvar {key} created."


@customizations.route("/gvars/<key>", methods=["GET"])
@requires_auth
def get_specific_gvar(_, key):
    gvar = current_app.mdb.gvars.find_one({"key": key})
    if gvar is None:
        return "Gvar not found", 404

    return jsonify(gvar)


@customizations.route("/gvars/<key>", methods=["POST"])
@requires_auth
def gvar_update(user, key):
    data = request.json
    gvar = current_app.mdb.gvars.find_one({"key": key}, ["owner", "editors"])
    if data is None:
        return "No data found", 400
    if "value" not in data:
        return "Missing value field", 400
    if gvar is None:
        return "Gvar not found", 404
    if gvar["owner"] != user.id and user.id not in gvar.get("editors", []):
        return "You do not have permission to edit this gvar", 403
    if len(data["value"]) > 100000:
        return "Gvars must be less than 100KB", 400
    current_app.mdb.gvars.update_one({"key": key}, {"$set": {"value": data["value"]}})
    return "Gvar updated."


@customizations.route("/gvars/<key>", methods=["DELETE"])
@requires_auth
def gvar_delete(user, key):
    gvar = current_app.mdb.gvars.find_one({"key": key}, ["owner"])
    if gvar is None:
        return "Gvar not found", 404
    if gvar["owner"] != user.id:
        return "You do not have permission to delete this gvar", 403
    current_app.mdb.gvars.delete_one({"key": key})
    return "Gvar deleted."
