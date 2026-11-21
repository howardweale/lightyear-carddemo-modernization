"""Bounded, anonymous HTTPS GET for pinned public GitHub Release assets only."""
import contextlib
from datetime import timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import math
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class ReadRefused(ValueError):
    """A fixed code safe to print without URLs, signed query strings or response bodies."""


CDN = {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def host(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in {"github.com", *CDN}
            or parts.username is not None or parts.password is not None or parts.port is not None
            or parts.fragment):
        raise ReadRefused("release-origin")
    return parts.hostname


class ReleaseRedirects(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if host(newurl) not in CDN or req.get_method() != "GET":
            raise ReadRefused("release-redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def seconds(value, now):
    if value is None:
        return None
    if re.fullmatch(r"[0-9]{1,12}", value):
        return int(value)
    try:
        date = parsedate_to_datetime(value)
        if date is None or date.tzinfo is None:
            raise ValueError
        return max(0, math.ceil(date.astimezone(timezone.utc).timestamp() - now))
    except (ValueError, TypeError, OverflowError):
        raise ReadRefused("release-retry-after") from None


def delay(status, origin, headers, body, now, retry):
    """Return None on permanent status. Never shorten an indicated wait to fit."""
    if status not in (403, 429):
        return None
    reset = headers.get("x-ratelimit-reset")
    primary = (origin == "github.com" and headers.get("x-ratelimit-remaining") == "0"
               and reset is not None and re.fullmatch(r"[0-9]{1,12}", reset))
    secondary = False
    if origin == "github.com" and len(body) <= 4096:
        try:
            message = json.loads(body).get("message", "")
            secondary = isinstance(message, str) and message.lower().startswith(
                ("you have exceeded a secondary rate limit", "you have triggered an abuse detection mechanism"))
        except (ValueError, AttributeError, UnicodeError):
            pass
    if status == 403 and not (primary or secondary):
        return None
    retry_after = seconds(headers.get("retry-after"), now)
    waits = [2 ** retry]
    if primary:
        waits.append(max(0, math.ceil(int(reset) - now)))
    if retry_after is not None:
        waits.append(retry_after)
    elif secondary or (status == 429 and origin == "github.com" and not primary):
        waits.append(60)
    return max(waits)


class ReadBudget:
    def __init__(self, *, open_request=None, monotonic=time.monotonic, wall=time.time,
                 sleep=time.sleep, jitter=None):
        self.open = open_request or build_opener(ProxyHandler({}), ReleaseRedirects()).open
        self.clock, self.wall, self.sleep = monotonic, wall, sleep
        self.jitter = jitter or (lambda: random.uniform(0, 0.25))
        self.deadline = self.clock() + 165
        self.sleep_left = 75.0

    def get(self, url, size):
        target = urlsplit(url)
        if (host(url) != "github.com" or target.query or not re.fullmatch(
                r"/howardweale/lightyear-carddemo-modernization/releases/download/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", target.path)
                or target.path.rsplit("/", 1)[1] in (".", "..")):
            raise ReadRefused("release-origin")
        for retry in range(3):
            remaining = self.deadline - self.clock()
            if remaining <= 0:
                raise ReadRefused("release-deadline")
            request = Request(url, headers={"Accept-Encoding": "identity", "User-Agent": "lightyear-public-input/1"})
            try:
                with self.open(request, timeout=min(25, remaining)) as response:
                    host(response.geturl())
                    if response.status != 200:
                        raise ReadRefused("release-http-status")
                    chunks = bytearray()
                    while len(chunks) <= size:
                        if self.clock() >= self.deadline:
                            raise ReadRefused("release-deadline")
                        chunk = response.read1(min(16384, size + 1 - len(chunks)))
                        if not chunk:
                            break
                        chunks.extend(chunk)
                    raw = bytes(chunks)
                if self.clock() >= self.deadline or len(raw) != size:
                    raise ReadRefused("release-read-incomplete")
                return raw
            except HTTPError as error:
                with contextlib.closing(error):
                    origin = host(error.geturl())
                    hdr = {k.lower(): v for k, v in error.headers.items()}
                    body = error.read(4097) if error.code in (403, 429) else b""
                    wait = delay(error.code, origin, hdr, body, self.wall(), retry)
                    code = error.code
                if wait is None:
                    raise ReadRefused("release-http-status") from None
                wait += self.jitter()
                if retry == 2 or wait > self.sleep_left or self.clock() + wait >= self.deadline:
                    raise ReadRefused("release-rate-budget") from None
                self.sleep_left -= wait
                print(f"release-read-rate-limit status={code} retry={retry+1} wait_seconds={wait:.3f}", flush=True)
                self.sleep(wait)
            except (URLError, HTTPException, TimeoutError, OSError):
                raise ReadRefused("release-transport") from None
        raise ReadRefused("release-rate-budget")
