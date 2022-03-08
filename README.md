# avrae ![Build Status](https://github.com/avrae/avrae-service/workflows/Build/badge.svg)

Avrae is a bot to facilitate running Dungeons & Dragons 5e online over Discord. This project is the backend to serve
avrae.io.

You can join the Avrae Development Discord [here](https://discord.gg/pQbd4s6)!

## Requirements

- Python 3.10+
- MongoDB server
- Redis server

See the README in avrae/avrae for additional instructions and links to dependencies.

## Running

### Configuration

The development config defaults to the MongoDB/Redis servers run by [Avrae](https://github.com/avrae/avrae) Docker
Compose.

1. Copy `docker/config-development.py` to `config.py`.
2. The dev config should point to the services exposed by the Avrae docker-compose file. If necessary, set the
   environment variables `MONGO_URL` and `REDIS_URL` to override connection strings.
3. Set the `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, and `DISCORD_BOT_TOKEN` environment variables to the values for
   your application, found in the [Discord Developer Portal](https://discord.com/developers/applications).
4. Set the `JWT_SECRET` env var to any value of your choice.

**Env Var Overview**

- `MONGO_URL` - Override connection string to MongoDB, defaults to exposed instance from avrae/avrae docker compose
- `REDIS_URL` - Override connection string to Redis, defaults to exposed instance from avrae/avrae docker compose
- `DISCORD_CLIENT_ID` - Discord application Client ID (Dev Portal -> Application -> OAuth2)
- `DISCORD_CLIENT_SECRET` - Discord application Client Secret (Dev Portal -> Application -> OAuth2)
- `DISCORD_BOT_TOKEN` - Discord application Bot User Token (Dev Portal -> Application -> Bot)
- `JWT_SECRET` - Used to sign JWTs issued by the service
- `ELASTICSEARCH_ENDPOINT` (optional) - Used to specify URL of an ElasticSearch instance for Alias Workshop

### ElasticSearch

The Avrae service requires ElasticSearch for some features (e.g. searching alias workshop collections). You should
either set up a dev ElasticSearch instance on AWS, or run an openElasticSearch distro.

Whichever you choose, set the `ELASTICSEARCH_ENDPOINT` env var. The service will work without this set, but Alias
Workshop endpoints might have undefined behaviour.

### Running locally

1. Create a [virtual environment](https://docs.python.org/3/library/venv.html): `python3 -m venv venv`.
2. Activate the venv: `source venv/bin/activate` on Unix (bash/zsh), `venv\Scripts\activate.bat` on Windows.
3. Install the required Python packages: `pip install -r requirements.txt`.
4. Run the app: `python -m flask run`.

The service should now be accessible at http://localhost:5000.

Should you have authentication errors and DB not loading locally, you can update line 38 in app.py to the below.

```app.mdb = mdb = PyMongo(app, config.MONGO_URL).cx["avrae"]```

### Running locally with Docker

1. Build the Docker image: `docker build -t avrae-service:latest --build-arg ENVIRONMENT=development .`.
2. Run the Docker image: `docker run -p 58000:8000 avrae-service:latest`.

The service should now be accessible at http://localhost:58000.

### Running in production

1. Build the Docker image: `docker build -t avrae-service:latest`.
2. Deploy it in whatever fashion your production environment requires.

The service should now be accessible at http://IP.ADDRESS:8000.
 