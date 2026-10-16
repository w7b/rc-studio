import json

from redis.exceptions import ConnectionError

from studio_ai.infrastructure.cache import JsonCache


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.writes = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex):
        self.values[key] = value
        self.writes.append((key, ex))

    def delete(self, key):
        self.values.pop(key, None)

    def close(self):
        pass


def test_json_cache_reuses_value_until_invalidated():
    client = FakeRedis()
    cache = JsonCache(client)
    calls = []

    assert cache.get_or_set('formats', 60, lambda: calls.append(1) or {'items': [1]}) == {
        'items': [1]
    }
    assert cache.get_or_set('formats', 60, lambda: calls.append(2) or {}) == {'items': [1]}
    assert calls == [1]
    assert client.writes == [('studio:v1:formats', 60)]

    cache.delete('formats')
    assert cache.get_or_set('formats', 60, lambda: calls.append(3) or {'items': [2]}) == {
        'items': [2]
    }


def test_json_cache_fails_open_when_redis_is_unavailable():
    class OfflineRedis(FakeRedis):
        def get(self, key):
            raise ConnectionError('offline')

        def set(self, key, value, ex):
            raise ConnectionError('offline')

    assert JsonCache(OfflineRedis()).get_or_set('config', 60, lambda: {'ok': True}) == {
        'ok': True
    }


def test_json_cache_ignores_invalid_cached_json():
    client = FakeRedis()
    client.values['studio:v1:config'] = 'invalid'
    value = JsonCache(client).get_or_set('config', 60, lambda: {'fresh': True})
    assert value == {'fresh': True}
    assert json.loads(client.values['studio:v1:config']) == value
