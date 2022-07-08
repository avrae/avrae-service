import os

TESTING = True if os.environ.get("TESTING") else False
ENVIRONMENT = "Staging"

MONGO_URL = os.environ["MONGO_URL"]
REDIS_URL = os.environ["REDIS_URL"]
SENTRY_DSN = os.getenv("SENTRY_DSN")

# discord oauth
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
OAUTH_REDIRECT_URI = "https://avrae.io/login"
OAUTH_SCOPE = "identify guilds"

# other discord
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# site auth
JWT_SECRET = os.getenv("JWT_SECRET")
DRACONIC_SIGNATURE_SECRET = os.getenv("DRACONIC_SIGNATURE_SECRET", "secret").encode()

# AWS stuff
ELASTICSEARCH_ENDPOINT = os.getenv("ELASTICSEARCH_ENDPOINT")
