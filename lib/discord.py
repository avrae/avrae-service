import datetime

import requests
from flask import abort, current_app

import config
from lib.utils import now

DISCORD_API = "https://discord.com/api/v6"
DISCORD_CDN = "https://cdn.discordapp.com"
HEADERS = {
    "User-Agent": "DiscordBot (https://github.com/avrae/avrae.io, 1)"
}


# oauth
def exchange_code(code):
    data = {
        'client_id': config.DISCORD_CLIENT_ID,
        'client_secret': config.DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': config.OAUTH_REDIRECT_URI,
        'scope': config.OAUTH_SCOPE
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    r = requests.post(f'{DISCORD_API}/oauth2/token', data=data, headers=headers)
    r.raise_for_status()
    return r.json()


def refresh_token(ref_token):
    data = {
        'client_id': config.DISCORD_CLIENT_ID,
        'client_secret': config.DISCORD_CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': ref_token,
        'redirect_uri': config.OAUTH_REDIRECT_URI,
        'scope': config.OAUTH_SCOPE
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    r = requests.post(f'{DISCORD_API}/oauth2/token', data=data, headers=headers)
    r.raise_for_status()
    return r.json()


def handle_token_response(access_token_resp):
    access_token = access_token_resp['access_token']
    ref_token = access_token_resp['refresh_token']
    expiry = now() + datetime.timedelta(seconds=access_token_resp['expires_in'])

    r = get("/users/@me", access_token)
    r.raise_for_status()

    user = r.json()
    user['discord_auth'] = {"access_token": access_token, "expiry": expiry, "refresh_token": ref_token}

    # store user access token
    current_app.mdb.users.update_one(
        {"id": str(user['id'])},
        {"$set": user},
        upsert=True
    )

    # return current access token and user info
    return access_token, UserInfo(user)


def discord_token_for(user_id: str):
    """Gets the current discord access token for the given user id, refreshing if necessary."""
    user = current_app.mdb.users.find_one({"id": user_id})
    if user is None:
        return None
    if 'discord_auth' not in user:
        return None

    expiry = user['discord_auth']['expiry']
    if expiry < now():
        resp = refresh_token(user['discord_auth']['refresh_token'])
        token, _ = handle_token_response(resp)
        return token
    else:
        return user['discord_auth']['access_token']


# user
class UserInfo:
    def __init__(self, user):
        self.username = user['username']  # type: str
        self.id = user['id']  # type: str
        self.discriminator = user['discriminator']  # type: str
        self.avatar = user['avatar']  # type: str or None

    def get_avatar_url(self):
        if self.avatar:
            return f"{DISCORD_CDN}/avatars/{self.id}/{self.avatar}.png?size=512"
        else:
            return f"{DISCORD_CDN}/embed/avatars/{int(self.discriminator) % 5}.png?size=512"

    def to_dict(self):
        return {'id': self.id, 'username': f"{self.username}#{self.discriminator}", 'avatarUrl': self.get_avatar_url()}


def get(endpoint, token):
    headers = HEADERS.copy()
    headers['Authorization'] = f"Bearer {token}"
    return requests.get(f"{DISCORD_API}{endpoint}", headers=headers)


def bot_get(endpoint):
    headers = HEADERS.copy()
    headers['Authorization'] = f"Bot {config.DISCORD_BOT_TOKEN}"
    return requests.get(f"{DISCORD_API}{endpoint}", headers=headers)


def get_user_info(discord_access_token):
    r = get("/users/@me", discord_access_token)
    try:
        data = r.json()
        # cache us
        current_app.mdb.users.update_one(
            {"id": str(data['id'])},
            {"$set": data},
            upsert=True
        )
        return UserInfo(data)
    except KeyError:
        abort(403)


def fetch_user_info(user_id):
    # is user in our list of known users?
    user = current_app.mdb.users.find_one({"id": str(user_id)})
    if user is not None:
        del user['_id']  # mongo ID
        return UserInfo(user)
    else:
        return UserInfo({"username": str(user_id), "id": str(user_id), "discriminator": "0000", "avatar": None})


def search_by_username(username, discriminator):
    user = current_app.mdb.users.find_one({"username": username, "discriminator": discriminator})
    if user is not None:
        del user['_id']  # mongo ID
        return UserInfo(user)
    return None


# guilds
def get_current_user_guilds(discord_access_token):
    """
    Returns a list of partial guild objects the user is a member of.
    https://discord.com/developers/docs/resources/user#get-current-user-guilds
    """
    r = get("/users/@me/guilds", discord_access_token)
    r.raise_for_status()
    return r.json()


def get_guild_roles(guild_id):
    """
    Gets a list of role objects for the guild.
    https://discord.com/developers/docs/resources/guild#get-guild-roles

    :type guild_id: str or int
    """
    r = bot_get(f"/guilds/{guild_id}/roles")
    r.raise_for_status()
    return r.json()


def get_guild_member(guild_id, user_id):
    """
    Gets a guild member object for the given user.
    https://discord.com/developers/docs/resources/guild#get-guild-member

    :type guild_id: str or int
    :type user_id: str or int
    """
    r = bot_get(f"/guilds/{guild_id}/members/{user_id}")
    r.raise_for_status()
    return r.json()
