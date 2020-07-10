import json

import d20
import sentry_sdk
from flask import Flask, request
from flask_cors import CORS
from flask_pymongo import PyMongo
from sentry_sdk.integrations.flask import FlaskIntegration

import config
from blueprints.bot import bot
from blueprints.characters import characters
from blueprints.cheatsheets import cheatsheets
from blueprints.customizations import customizations
from blueprints.discord import discord
from blueprints.homebrew.items import items
from blueprints.homebrew.spells import spells
from lib import errors
from lib.auth import requires_auth
from lib.discord import discord_token_for, get_user_info
from lib.redisIO import RedisIO
from lib.utils import jsonify

if config.SENTRY_DSN is not None:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment='Development' if config.TESTING else 'Production',
        integrations=[FlaskIntegration()]
    )

app = Flask(__name__)
app.rdb = rdb = RedisIO(config.REDIS_URL)
app.mdb = mdb = PyMongo(app, config.MONGO_URL).db

CORS(app)


# routes
@app.route('/', methods=["GET"])
def hello_world():
    return 'Hello World!'


@app.route('/user', methods=["GET"])
@requires_auth
def user(the_user):
    info = get_user_info(discord_token_for(the_user.id))
    data = {
        "username": info.username,
        "discriminator": info.discriminator,
        "id": info.id,
        "avatarUrl": info.get_avatar_url()
    }
    return jsonify(data)


@app.route('/userStats', methods=["GET"])
@requires_auth
def user_stats(the_user):
    data = {
        "numCharacters": app.mdb.characters.count_documents({"owner": the_user.id}),
        "numCustomizations": sum((app.mdb.aliases.count_documents({"owner": the_user.id}),
                                  app.mdb.snippets.count_documents({"owner": the_user.id})))
    }
    return jsonify(data)


@app.route('/commands', methods=["GET"])
def commands():
    with open("static/commands.json") as f:
        data = json.load(f)
    return jsonify(data)


@app.route('/roll', methods=['GET'])
def roll():
    to_roll = request.args.get('dice') or '1d20'
    adv = request.args.get('adv', 0)
    try:
        rolled = d20.roll(to_roll, advantage=adv)
    except Exception as e:
        result = {'success': False, 'error': str(e)}
    else:
        result = {
            'success': True, 'total': rolled.total, 'result': rolled.result, 'is_crit': rolled.crit,
            'repr': repr(rolled)
        }

    return jsonify(result)


app.register_blueprint(characters, url_prefix="/characters")
app.register_blueprint(customizations, url_prefix="/customizations")
app.register_blueprint(bot, url_prefix="/bot")
app.register_blueprint(cheatsheets, url_prefix="/cheatsheets")
app.register_blueprint(discord, url_prefix="/discord")
app.register_blueprint(items, url_prefix="/homebrew/items")
app.register_blueprint(spells, url_prefix="/homebrew/spells")

errors.register_error_handlers(app)

if __name__ == '__main__':
    app.run()
