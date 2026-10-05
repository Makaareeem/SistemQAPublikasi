"""Bounded in-process cache. Never used for evaluation requests."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic


class TTLCache:
    def __init__(self, maxsize=128, ttl=600):
        self.maxsize, self.ttl = maxsize, ttl
        self.items = OrderedDict()
        self.lock = RLock()

    def get(self, key):
        with self.lock:
            item = self.items.get(key)
            if item is None:
                return None
            created, value = item
            if monotonic() - created > self.ttl:
                del self.items[key]
                return None
            self.items.move_to_end(key)
            return deepcopy(value)

    def put(self, key, value):
        if self.maxsize <= 0 or self.ttl <= 0:
            return
        with self.lock:
            self.items[key] = (monotonic(), deepcopy(value))
            self.items.move_to_end(key)
            while len(self.items) > self.maxsize:
                self.items.popitem(last=False)

    def clear(self):
        with self.lock:
            self.items.clear()
