"""Test seam only. A production executor is deliberately not provided."""

import threading
import uuid
from dataclasses import dataclass
from typing import Protocol
from .portfolio import _conflicts


@dataclass(frozen=True)
class Lease:
    order_id: str
    owner: str
    token: str
    expires: float


class WorkQueue(Protocol):
    def submit(self, order): ...
    def claim(self, owner, request_id, now, ttl): ...
    def heartbeat(self, lease, now, ttl): ...
    def complete(self, lease, now, receipt_hash): ...


class InMemoryWorkQueue:
    def __init__(self, graph, verification_capacity):
        if (
            type(verification_capacity) is not int
            or not 1 <= verification_capacity <= 64
        ):
            raise ValueError("verification capacity must be 1..64")
        self.graph, self.capacity = graph, verification_capacity
        self.orders = {}
        self.leases = {}
        self.requests = {}
        self.completed = {}
        self.lock = threading.RLock()

    def submit(self, order):
        with self.lock:
            previous = self.orders.get(order.order_id)
            if previous and previous.content_sha256 != order.content_sha256:
                raise ValueError("idempotency conflict")
            self.orders[order.order_id] = order

    def claim(self, owner, request_id, now, ttl):
        if not owner or not request_id or not 0 < ttl <= 3600:
            raise ValueError("invalid lease")
        with self.lock:
            key = (owner, request_id)
            if key in self.requests:
                lease = self.requests[key]
                if self.leases.get(lease.order_id) != lease or lease.expires <= now:
                    raise ValueError("claim expired; fresh request required")
                return lease
            active = {k: l for k, l in self.leases.items() if l.expires > now}
            if len(active) >= self.capacity:
                return None
            for key in sorted(self.orders):
                if key in active or key in self.completed:
                    continue
                selected = {k: self.orders[k] for k in [key, *active]}
                if any(key in c["orders"] for c in _conflicts(selected, self.graph, 2)):
                    continue
                lease = Lease(key, owner, uuid.uuid4().hex, now + ttl)
                self.leases[key] = lease
                self.requests[(owner, request_id)] = lease
                return lease
            return None

    def _check(self, lease, now):
        if (
            self.leases.get(lease.order_id) != lease
            or lease.expires <= now
            or lease.order_id in self.completed
        ):
            raise ValueError("stale lease fencing token")

    def heartbeat(self, lease, now, ttl):
        if not 0 < ttl <= 3600:
            raise ValueError("invalid lease duration")
        with self.lock:
            self._check(lease, now)
            renewed = Lease(lease.order_id, lease.owner, lease.token, now + ttl)
            self.leases[lease.order_id] = renewed
            for k, v in self.requests.items():
                if v == lease:
                    self.requests[k] = renewed
            return renewed

    def complete(self, lease, now, receipt_hash):
        if len(receipt_hash) != 64 or any(
            c not in "0123456789abcdef" for c in receipt_hash
        ):
            raise ValueError("receipt hash required")
        with self.lock:
            if self.completed.get(lease.order_id) == (lease.token, receipt_hash):
                return
            self._check(lease, now)
            self.completed[lease.order_id] = (lease.token, receipt_hash)
            del self.leases[lease.order_id]
