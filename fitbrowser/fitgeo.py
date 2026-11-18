#!/usr/bin/env python3
"""Find the nearest city to a given latitude/longitude using GeoNames, with a local cache."""

import argparse
import json
import math
import os
import sys
import requests

if __package__ == "fitbrowser":
    from . import fitconfig
else:
    import fitconfig

EARTH_RADIUS_KM = 6371.0

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))

# GeoNames status codes (https://www.geonames.org/export/webservice-exception.html)
_GEONAMES_AUTH_ERROR = 10                    # user does not exist / invalid / not enabled
_GEONAMES_LIMIT_ERRORS = {18, 19, 20}        # daily / hourly / weekly credit limit exceeded


def check_geonames_username(username: str, timeout: float = 10) -> bool:
    """Return True if `username` is a valid GeoNames account name.

    Sends one cheap request (timezone lookup, 1 credit) to GeoNames.
    Returns False if GeoNames rejects the user (unknown user, empty name, or
    an account not enabled for the free web services). An account that has
    used up its credit limit still exists, so it counts as valid.

    Raises requests.RequestException if GeoNames cannot be reached and
    RuntimeError on an unexpected answer, so that a network problem is not
    mistaken for an invalid username.
    """
    if not isinstance(username, str) or not username.strip():
        return False

    url = "http://api.geonames.org/timezoneJSON"
    params = {"lat": 0, "lng": 0, "username": username.strip()}
    response = requests.get(url, params=params, timeout=timeout)
    # GeoNames answers an unknown user with HTTP 401 and a JSON body, so
    # look at the body before treating the HTTP status as an error.
    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        raise RuntimeError(f"Unexpected GeoNames response: {response.text[:200]!r}")

    status = data.get("status")
    if status is None:
        return True
    code = status.get("value")
    if code == _GEONAMES_AUTH_ERROR:
        return False
    if code in _GEONAMES_LIMIT_ERRORS:
        return True
    raise RuntimeError(f"GeoNames error: {status.get('message', status)}")

class NearestCity:
    """Resolves lat/lon coordinates to the nearest city, backed by an in-memory cache."""

    def __init__(self, config):
        self.config = config
        self.good = False
        if "geonames" in config:
            if "userName" in config["geonames"]:
                if len(config["geonames"]["userName"]) > 0:
                    self.good = True

    def find_in_cache(self, lat: float, lon: float):
        """Return (country, city, distance) of the closest cached record within radius_km, or None."""
        best = None
        radius_km = float(self.config["geonames"]["cacheRadiusKm"])
        for record in self.config["locationCache"]:
            d = haversine_km(lat, lon, record["lat"], record["lon"])
            if d <= radius_km and (best is None or d < best[0]):
                best = (d, (record["country"], record["city"], record["distance"]))
        return best[1] if best else None

    def query_geonames(self, lat: float, lon: float) -> tuple:
        """Return (country, city, distance_km) for the nearest populated place to (lat, lon)."""
        url = "http://api.geonames.org/findNearbyPlaceNameJSON"
        username = self.config["geonames"]["userName"]
        database = self.config["geonames"]["database"]
        params = {"lat": lat, "lng": lon, "username": username, "cities": database}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "status" in data:
            self.good = False
            raise RuntimeError(f"GeoNames error: {data['status'].get('message', data['status'])}")
        if not data.get("geonames"):
            raise ValueError(f"No nearby place found for lat={lat}, lon={lon}")

        place = data["geonames"][0]
        country = place.get("countryName", "")
        city = place['name']
        distance = float(place["distance"])

        return (country, city, distance)

    def nearest_city(self, lat: float, lon: float) -> tuple:
        """Return (country, city, distance_km), using the cache when within CACHE_RADIUS_KM."""
        cached = self.find_in_cache(lat, lon)
        if cached is not None:
            return cached
        if not self.good:
            return None

        country, city, distance = self.query_geonames(lat, lon)
        self.config.addLocationRecord({"lat": lat, "lon": lon, "country": country, "city": city, "distance": distance})
        return (country, city, distance)

    def find_city_in_cache(self, country: str, city: str):
        """Return (lat, lon, distance) of the first cached record matching
        country and city (case-insensitive), or None."""
        country_key, city_key = country.casefold(), city.casefold()
        for record in self.config["locationCache"]:
            if record["country"].casefold() == country_key and record["city"].casefold() == city_key:
                return (record["lat"], record["lon"], record["distance"])
        return None

    def query_geonames_city(self, country: str, city: str) -> tuple:
        """Return (country, city, lat, lon) as named by GeoNames for the
        populated place called `city` in the country named `country`."""
        url = "http://api.geonames.org/searchJSON"
        username = self.config["geonames"]["userName"]
        params = {
            "name_equals": city,
            "featureClass": "P",
            "maxRows": 100,
            "orderby": "population",
            "username": username,
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "status" in data:
            self.good = False
            raise RuntimeError(f"GeoNames error: {data['status'].get('message', data['status'])}")

        country_key = country.casefold()
        for place in data.get("geonames", []):
            if place.get("countryName", "").casefold() == country_key:
                return (place["countryName"], place["name"], float(place["lat"]), float(place["lng"]))

        raise ValueError(f"No place named {city!r} found in {country!r}")

    def location_from_city(self, country: str, city: str) -> tuple:
        """Return (lat, lon, distance) for a city, using the cache first.

        On a cache miss, GeoNames is queried and the result is added to the
        cache with a distance of 0 (the coordinate is the place itself)."""
        cached = self.find_city_in_cache(country, city)
        if cached is not None:
            return cached
        if not self.good:
            return None

        found_country, found_city, lat, lon = self.query_geonames_city(country, city)
        self.records.append(
            {"lat": lat, "lon": lon, "country": found_country, "city": found_city, "distance": 0.0}
        )
        return (lat, lon, 0.0)

def main():
    parser = argparse.ArgumentParser(description="Find the nearest city to a lat/lon coordinate.")
    parser.add_argument('-n', '--noConfigFile', default=False, action="store_true", help="Do not load default configuration file.")
    parser.add_argument('-c', '--configFile', default=None, help="Use this configuration file.")
    parser.add_argument('-v', '--verbose', default=0, action="count", help="Verbosity level.")
    parser.add_argument("latitude", type=float, help="Latitude, e.g. 48.1")
    parser.add_argument("longitude", type=float, help="Longitude, e.g. 11.5")
    args = parser.parse_args()

    useConfigFile = not args.noConfigFile
    configFile = args.configFile
    verbosity = args.verbose
    config = fitconfig.FitConfig(useConfigFile, configFile)

    try:
        finder = NearestCity(config)
        country, place, distance = finder.nearest_city(args.latitude, args.longitude)
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Nearest city to ({args.latitude}, {args.longitude}): {place}, {country} ({distance:.2f} km)")
    config.save()

if __name__ == "__main__":
    main()
