"""
Created on Dec 28, 2016

@author: andrew
"""

import json

import redis


class RedisIO:
    """
    A simple class to interface with the redis database.
    """

    def __init__(self, url):
        self._db = redis.from_url(url)
        self.pubsub = self._db.pubsub(ignore_subscribe_messages=True)

    def get(self, key, default=None):
        encoded_data = self._db.get(key)
        return encoded_data.decode() if encoded_data is not None else default

    def set(self, key, value):
        return self._db.set(key, value)

    def incr(self, key):
        return self._db.incr(key)

    def exists(self, key):
        return self._db.exists(key)

    def delete(self, key):
        return self._db.delete(key)

    def setex(self, key, value, expiration):
        return self._db.setex(key, value, expiration)

    def set_dict(self, key, dictionary):
        if len(dictionary) == 0:
            return self._db.delete(key)
        return self._db.hmset(key, dictionary)

    def get_dict(self, key, dict_key):
        return self._db.hget(key, dict_key).decode()

    def get_whole_dict(self, key, default={}):
        encoded_dict = self._db.hgetall(key)
        if encoded_dict is None: return default
        out = {}
        for k in encoded_dict.keys():
            out[k.decode()] = encoded_dict[k].decode()
        return out

    def jset(self, key, data, **kwargs):
        return self.not_json_set(key, data, **kwargs)

    def jsetex(self, key, data, exp, **kwargs):
        data = json.dumps(data, **kwargs)
        return self.setex(key, data, exp)

    def jget(self, key, default=None):
        return self.not_json_get(key, default)

    def not_json_set(self, key, data, **kwargs):
        data = json.dumps(data, **kwargs)
        return self.set(key, data)

    def not_json_get(self, key, default=None):
        data = self.get(key)
        return json.loads(data) if data is not None else default

    def publish(self, channel, data):
        return self._db.publish(channel, data)

    def hget(self, key, field, default=None):
        encoded_data = self._db.hget(key, field)
        return encoded_data.decode() if encoded_data is not None else default

    def hset(self, key, field, value):
        return self._db.hset(key, field, value)

    def hdel(self, key, *fields):
        return self._db.hdel(key, *fields)

    def jhget(self, key, field, default=None):
        data = self.hget(key, field)
        return json.loads(data) if data is not None else default

    def jhset(self, key, field, value, **kwargs):
        data = json.dumps(value, **kwargs)
        return self.hset(key, field, data)
