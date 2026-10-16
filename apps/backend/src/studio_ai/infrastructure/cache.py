"""Small fail-open JSON cache for read-mostly HTTP data."""
import json
import os

from redis import Redis
from redis.exceptions import RedisError


class JsonCache:
    def __init__(self, client=None, namespace='studio:v1'):
        self.client = client
        self.namespace = namespace

    @classmethod
    def from_environment(cls):
        url = os.environ.get('REDIS_URL', '').strip()
        if not url:
            return cls()
        client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=.25,
            socket_timeout=.25,
            health_check_interval=30,
            max_connections=12,
        )
        return cls(client)

    def _key(self, key):
        return f'{self.namespace}:{key}'

    def get_or_set(self, key, ttl_seconds, producer):
        if self.client is None:
            return producer()
        namespaced = self._key(key)
        try:
            cached = self.client.get(namespaced)
            if cached is not None:
                return json.loads(cached)
        except (RedisError, json.JSONDecodeError, TypeError):
            pass
        value = producer()
        try:
            self.client.set(namespaced, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
        except (RedisError, TypeError, ValueError):
            pass
        return value

    def delete(self, key):
        if self.client is None:
            return
        try:
            self.client.delete(self._key(key))
        except RedisError:
            pass

    def close(self):
        if self.client is not None:
            self.client.close()
