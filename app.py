import json
import os

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
from lib import dice
from lib.discord import get_user_info
from lib.redisIO import RedisIO
from lib.utils import jsonify

SENTRY_DSN = os.getenv('SENTRY_DSN') or None
TESTING = True if os.environ.get("TESTING") else False

if SENTRY_DSN is not None:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment='Development' if TESTING else 'Production',
        integrations=[FlaskIntegration()]
    )

app = Flask(__name__)
app.rdb = rdb = RedisIO(config.redis_url if not TESTING else config.test_redis_url)
app.mdb = mdb = PyMongo(app, config.mongo_url if not TESTING else config.test_mongo_url).db

CORS(app)


# routes
@app.route('/', methods=["GET"])
def hello_world():
    return 'Hello World!'


@app.route('/user', methods=["GET"])
def user():
    info = get_user_info()
    data = {
        "username": info.username,
        "discriminator": info.discriminator,
        "id": info.id,
        "avatarUrl": info.get_avatar_url()
    }
    return jsonify(data)


@app.route('/userStats', methods=["GET"])
def user_stats():
    info = get_user_info()
    data = {
        "numCharacters": app.mdb.characters.count_documents({"owner": info.id}),
        "numCustomizations": sum((app.mdb.aliases.count_documents({"owner": info.id}),
                                  app.mdb.snippets.count_documents({"owner": info.id})))
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
    rolled = dice.roll(to_roll, adv)

    result = {'total': rolled.total, 'result': rolled.result,
              'is_crit': rolled.crit,
              'dice': [part.to_dict() for part in rolled.raw_dice.parts]}

    return jsonify(result)


app.register_blueprint(characters, url_prefix="/characters")
app.register_blueprint(customizations, url_prefix="/customizations")
app.register_blueprint(bot, url_prefix="/bot")
app.register_blueprint(cheatsheets, url_prefix="/cheatsheets")
app.register_blueprint(discord, url_prefix="/discord")
app.register_blueprint(items, url_prefix="/homebrew/items")
app.register_blueprint(spells, url_prefix="/homebrew/spells")

if __name__ == '__main__':
    app.run()
