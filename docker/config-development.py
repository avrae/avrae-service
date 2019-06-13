import os

os.environ['TESTING'] = 'yup'

# Default to `avrae` docker-compose hosts, allow override via environment variables
test_mongo_url = os.getenv('AVRAE_MONGO_URL', 'mongodb://root:topsecret@localhost:58017/avrae')
test_redis_url = os.getenv('AVRAE_REDIS_URL', 'redis://redis:58379/0')
