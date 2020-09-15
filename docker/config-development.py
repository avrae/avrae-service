import os

os.environ['TESTING'] = 'yup'
TESTING = True

# Default to `avrae` docker-compose hosts, allow override via environment variables
MONGO_URL = os.getenv('MONGO_URL', 'mongodb://root:topsecret@localhost:58017/avrae')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:58379/0')
SENTRY_DSN = os.getenv('SENTRY_DSN')

# discord oauth
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
OAUTH_REDIRECT_URI = "http://127.0.0.1:4200/login"
OAUTH_SCOPE = "identify guilds"

# other discord
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# site auth
JWT_SECRET = os.getenv('JWT_SECRET')

# AWS stuff
ELASTICSEARCH_ENDPOINT = os.getenv('ELASTICSEARCH_ENDPOINT')
