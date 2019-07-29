# avrae [![Build Status](https://travis-ci.org/avrae/avrae-service.svg?branch=master)](https://travis-ci.org/avrae/avrae-service)

Avrae is a bot to facilitate running Dungeons & Dragons 5e online over Discord. This project is the web api... thing FIXME

You can join the Avrae Development Discord [here](https://discord.gg/pQbd4s6)!

## Requirements

- Python 3.6+
- MongoDB server
- Redis server

## Running

### Configuration

The development config defaults to the MongoDB/Redis servers run by [Avrae](https://github.com/avrae/avrae) Docker Compose.

1. Copy `docker/config-development.py` to `config.py`.
2. Set the environment variables `AVRAE_MONGO_URL` and `AVRAE_REDIS_URL`, or change `test_mongo_url` and `test_redis_url` in `config.py`. 

### Running locally

1. Create a [virtual environment](https://docs.python.org/3/library/venv.html): `python3 -m venv venv`.
2. Activate the venv: `source venv/bin/activate` on Unix (bash/zsh), `venv\Scripts\activate.bat` on Windows.
3. Install the required Python packages: `pip install -r requirements.txt`.
4. Run the app: `python -m flask run`.

The service should now be accessible at http://localhost:5000.

### Running locally with Docker

1. Build the Docker image: `docker build -t avrae-service:latest --build-arg ENVIRONMENT=development .`.
2. Run the Docker image: `docker run -p 58000:8000 avrae-service:latest`.

The service should now be accessible at http://localhost:58000.

### Running in production

1. Build the Docker image: `docker build -t avrae-service:latest`.
2. Deploy it in whatever fashion your production environment requires.

The service should now be accessible at http://IP.ADDRESS:8000.
 