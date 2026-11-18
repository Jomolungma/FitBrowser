#!/usr/bin/env python3
"""
Check whether a Google Maps API key is valid, without rendering anything.

Usage:
    python check_google_api_key.py                # checks the key in gmapikey.json
    python check_google_api_key.py --file other.json
    python check_google_api_key.py --key AIza...

Exit codes: 0 = key valid, 1 = key invalid, 2 = check could not be performed
(network error, unreadable key file, unexpected response).

How it works
------------
The Maps JavaScript API loader (maps/api/js) returns the same script for any
key and only validates the key later, in the browser, so it cannot be used for
a headless check. Instead, the key is sent to a Google Maps web-service
endpoint (Geocoding). Google answers there with an explicit
"The provided API key is invalid." (or "... expired.") if it does not know the
key. Any other answer -- success, billing not enabled, API not activated on the
project, referrer/IP restrictions -- means Google recognised the key, so it is
considered valid. No quota is consumed when the request is denied.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

CHECK_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Google API keys are "AIza" followed by 35 URL-safe characters.
_KEY_PATTERN = re.compile(r"^AIza[0-9A-Za-z_-]{35}$")

# Phrases Google uses when the key itself is unknown, malformed or expired.
_INVALID_KEY_MARKERS = (
    "api key is invalid",
    "api key not valid",
    "api key is expired",
    "api key expired",
)


class KeyCheckError(Exception):
    """Raised when the validity of the key could not be determined."""


def check_google_api_key(key, timeout=10.0):
    """
    Return True if Google recognises `key` as a valid API key, False otherwise.

    Raises KeyCheckError if the check could not be performed (e.g. no network),
    so that a connectivity problem is not mistaken for an invalid key.
    """
    if not isinstance(key, str) or not _KEY_PATTERN.match(key.strip()):
        return False
    key = key.strip()

    query = urllib.parse.urlencode({"address": "Boston", "key": key})
    request = urllib.request.Request(f"{CHECK_URL}?{query}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        # Some endpoints answer bad keys with HTTP 400/403 and a message body.
        body = err.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as err:
        raise KeyCheckError(f"Could not reach {CHECK_URL}: {err}") from err

    try:
        data = json.loads(body)
    except ValueError as err:
        raise KeyCheckError(f"Unexpected response from Google: {body[:200]!r}") from err

    status = data.get("status", "")
    message = data.get("error_message", "").lower()

    if any(marker in message for marker in _INVALID_KEY_MARKERS):
        return False
    if status in ("OK", "ZERO_RESULTS", "REQUEST_DENIED", "OVER_QUERY_LIMIT",
                  "OVER_DAILY_LIMIT"):
        # REQUEST_DENIED without an "invalid key" message means the key exists
        # but is restricted / lacks billing / lacks this particular API.
        return True
    if status == "INVALID_REQUEST":
        return True  # the key was accepted; only our query was rejected
    raise KeyCheckError(f"Unexpected status {status!r} from Google: {message!r}")


def load_key(path):
    """Read the "key" field from a JSON file."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as err:
        raise KeyCheckError(f"Could not read {path}: {err}") from err
    key = data.get("key") if isinstance(data, dict) else None
    if not key:
        raise KeyCheckError(f'{path} is missing a "key" field.')
    return key


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check whether a Google Maps API key is valid.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--key", help="API key to check")
    source.add_argument("--file",
                        help=f'JSON file with a "key" field')
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="network timeout in seconds (default: 10)")
    args = parser.parse_args(argv)

    try:
        key = args.key if args.key is not None else load_key(args.file)
        valid = check_google_api_key(key, timeout=args.timeout)
    except KeyCheckError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 2

    print("API key is valid." if valid else "API key is INVALID.")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
