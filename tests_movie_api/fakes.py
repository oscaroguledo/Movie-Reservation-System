"""A minimal in-memory stand-in for redis.asyncio.Redis, covering just
the operations this codebase's repository classes actually use. Real
repository code runs against this in tests instead of mocking every
individual redis_client call, so both the repository and the service
orchestrating it get genuine coverage."""

import fnmatch


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                count += 1
            if key in self.sets:
                del self.sets[key]
                count += 1
            if key in self.hashes:
                del self.hashes[key]
                count += 1
        return count

    async def exists(self, key):
        return int(key in self.store or key in self.sets or key in self.hashes)

    async def persist(self, key):
        return True

    async def sadd(self, key, *values):
        members = self.sets.setdefault(key, set())
        before = len(members)
        members.update(str(v) for v in values)
        return len(members) - before

    async def srem(self, key, *values):
        members = self.sets.get(key)
        if not members:
            return 0
        before = len(members)
        for value in values:
            members.discard(str(value))
        return before - len(members)

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def mget(self, keys):
        return [self.store.get(key) for key in keys]

    async def hset(self, key, field, value):
        fields = self.hashes.setdefault(key, {})
        is_new = field not in fields
        fields[field] = value
        return 1 if is_new else 0

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hdel(self, key, field):
        fields = self.hashes.get(key, {})
        if field in fields:
            del fields[field]
            return 1
        return 0

    async def scan_iter(self, match=None, count=None):
        pattern = match or "*"
        for key in list(self.store.keys()):
            if fnmatch.fnmatch(key, pattern):
                yield key
