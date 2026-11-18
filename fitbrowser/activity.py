"""Reading Garmin FIT/TCX activity files, in one place:

- FitActivity: loads a single .FIT file - from a path or an already-open
  stream - and exposes it as one activity.
- TcxActivities: loads a Garmin Training Center Database (.tcx) file - which
  can hold multiple activities - and gives access to each one by its start
  timestamp (used as the activity identifier, same as its <Id> in the file).
- Logbook3Activities: loads a SportTracks 3 logbook (.logbook3) file and
  gives access to each of its activities by start timestamp, with GPS
  tracks decoded from each activity's binary <GPSRoute>.
- AppleHealthActivity: loads a single workout route .gpx file from an
  Apple Health export and exposes it as one activity (like FitActivity).
- MergedActivities: combines several of the above into one timeline.
- ZippedActivities: loads every .fit/.tcx/.gpx/.logbook3 file in a Zip
  archive - streamed from memory, nothing extracted to disk - using the
  matching class above for each entry, merged into one timeline.
- ActivitiesFilteredByLocation: wraps any of the above, keeping only the
  activities that start within a given distance of a given point.
- ActivitiesFilteredByDate: wraps any of the above, keeping only the
  activities that start between two dates/times.
- ActivitiesGroupedByLocation: wraps any of the above, sorting its
  activities into groups of nearby start locations.
- open_activities(path): picks whichever of the classes above matches
  path's extension (.fit / .zip / .tcx / .logbook3 / .gpx).

All of these classes have the identical public API: list_activities,
summarize_activity, extract_records, extract_pauses, extract_elevation -
plus __iter__/__len__/__contains__/__getitem__, inherited from the shared
Activities base class - which is what lets activity_to_json.py/
activity_summary.py treat every supported file type uniformly instead of
needing separate tools per format.

Unlike FIT, TCX timestamps carry no time zone information at all (they're
always UTC, denoted by a trailing "Z"), and there's no per-activity field
comparable to FIT's local_timestamp/time_offset to recover the original
local time from. So TCX times parsed here stay in UTC - there is no local
time to convert to without guessing.

Used by activity_to_json.py (one activity -> data.json for the map viewer)
and activity_summary.py (summary of every activity in a file).
"""

import os
import sys
import json
import math
import re
import base64
import bisect
import struct
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta, timezone

from garmin_fit_sdk import Decoder, Stream

SEMICIRCLE_TO_DEGREE = 180 / 2147483648
INVALID_LAT_LON = 0x7FFFFFFF
FIT_EPOCH = 631065600  # seconds between the Unix epoch and the FIT epoch (1989-12-31T00:00:00Z)
EARTH_RADIUS_M = 6371008.8  # mean Earth radius, for haversine distances

# FIT "sport" enum values this app has a specific label for; anything else
# (walking, hiking, generic, ...) is reported as the generic "moving".
KNOWN_SPORTS = {'running', 'cycling'}

class Calendar:
    """
    Helper class for a calendar, with navigation.

    This calendar collects all dates for which messages are available.
    I.e., it is not a general-purpose wall calendar, but it only has
    entries for which at least one message is available.

    E.g., "getNextDay" returns the next day for which there is a
    chat message. If there are messages on Jan 17 and Feb 12,
    getNextDay(Jan 17) would not return Jan 18, but Feb 12.
    """

    def __init__(self):
        # A sorted array of years.
        self.years = list()
        # For each year, a sorted array of months.
        self.months = dict()
        # For each year and each month, a sorted array of days.
        self.days = dict()

    def __contains__(self, timestamp):
        year, month, day = timestamp.year, timestamp.month, timestamp.day
        return (year in self.days) and (month in self.days[year]) and (day in self.days[year][month])

    def add(self, timestamp):
        year, month, day = timestamp.year, timestamp.month, timestamp.day

        if year not in self.years:
            self.years.append(year)
            self.years.sort()
            self.months[year] = list()
            self.days[year] = dict()

        if month not in self.months[year]:
            self.months[year].append(month)
            self.months[year].sort()
            self.days[year][month] = list()

        if day not in self.days[year][month]:
            self.days[year][month].append(day)
            self.days[year][month].sort()

    #
    # Get the first and last days.
    #

    @property
    def first(self):
        year, month, day = self.getFirstDay()
        return date(year, month, day)

    @property
    def last(self):
        year, month, day = self.getLastDay()
        return date(year, month, day)

    #
    # Get the first and last years, months and days.
    #

    def getFirstYear(self):
        return self.years[0]

    def getLastYear(self):
        return self.years[-1]

    def getFirstMonth(self, year=None):
        firstYear = year if year else self.getFirstYear()
        return firstYear, self.months[firstYear][0]

    def getLastMonth(self, year=None):
        lastYear = year if year else self.getLastYear()
        return lastYear, self.months[lastYear][-1]

    def getFirstDay(self, year=None, month=None):
        firstYear = year if year else self.getFirstYear()
        firstMonth = month if month else self.getFirstMonth(firstYear)[1]
        return firstYear, firstMonth, self.days[firstYear][firstMonth][0]

    def getLastDay(self, year=None, month=None):
        lastYear = year if year else self.getLastYear()
        lastMonth = month if month else self.getLastMonth(lastYear)[1]
        return lastYear, lastMonth, self.days[lastYear][lastMonth][-1]

    #
    # Find the previous available year.
    #

    def getPrevYear(self, year):
        yp = self.years.index(year)
        if yp > 0:
            prevYear = self.years[yp-1]
            return prevYear
        return None

    #
    # Find the previous available month.
    #

    def getPrevMonth(self, year, month):
        mp = self.months[year].index(month)
        if mp > 0:
            prevMonth = self.months[year][mp-1]
            return year, prevMonth
        prevYear = self.getPrevYear(year)
        if prevYear:
            prevMonth = self.months[prevYear][-1]
            return prevYear, prevMonth
        return None, None

    #
    # Find the previous available day.
    #

    def getPrevDay(self, year, month, day):
        dp = self.days[year][month].index(day)
        if dp > 0:
            prevDay = self.days[year][month][dp-1]
            return year, month, prevDay
        prevYear, prevMonth = self.getPrevMonth(year, month)
        if prevMonth:
            prevDay = self.days[prevYear][prevMonth][-1]
            return prevYear, prevMonth, prevDay
        return None, None, None

    #
    # Find the next available year.
    #

    def getNextYear(self, year):
        yp = self.years.index(year)
        if (yp+1) < len(self.years):
            nextYear = self.years[yp+1]
            return nextYear
        return None

    #
    # Find the next available month.
    #

    def getNextMonth(self, year, month):
        mp = self.months[year].index(month)
        if (mp+1) < len(self.months[year]):
            nextMonth = self.months[year][mp+1]
            return year, nextMonth
        nextYear = self.getNextYear(year)
        if nextYear:
            nextMonth = self.months[nextYear][0]
            return nextYear, nextMonth
        return None, None

    #
    # Find the next available day.
    #

    def getNextDay(self, year, month, day):
        dp = self.days[year][month].index(day)
        if (dp+1) < len(self.days[year][month]):
            nextDay = self.days[year][month][dp+1]
            return year, month, nextDay
        nextYear, nextMonth = self.getNextMonth(year, month)
        if nextMonth:
            nextDay = self.days[nextYear][nextMonth][0]
            return nextYear, nextMonth, nextDay
        return None, None, None

class Activity:
    """Wraps one activity from an Activities container (FitActivity,
    ZippedActivities, ...) as a (container, timestamp) pair, so callers
    don't have to keep re-passing the timestamp themselves. Each method
    delegates to the container's equivalent method for this timestamp.

    summary() and records() are computed on first use and cached in this
    Activity object, so calling them again is free. They return the cached
    dict/list itself, not a copy - callers must not modify it.
    """

    def __init__(self, container, timestamp):
        self.container = container
        self.timestamp = timestamp
        self._summary = None
        self._records = None
        self._keys = {}  # 'distance_m'/'duration_s' -> list of that field over records()

    def time(self):
        """This activity's start timestamp (a datetime)."""
        return self.timestamp

    def summary(self):
        """The container's summarize_activity() dict for this activity:
        id, timestamp, sport, distance_m, duration_s, start_lat, start_lng,
        ascent, descent. Cached after the first call.
        """
        if self._summary is None:
            self._summary = self.container.summarize_activity(self.timestamp)
        return self._summary

    def records(self):
        """GPS records for this activity: a list of {lat, lng, time, ele,
        heart_rate, distance_m, duration_s}.
        Cached after the first call.
        """
        if self._records is None:
            self._records = self.container.extract_records(self.timestamp)
        return self._records

    def pauses(self):
        return self.container.extract_pauses(self.timestamp)

    def distance_to_record(self, distance_m):
        """A record synthesized at exactly distance_m meters from the start:
        {lat, lng, time, ele, heart_rate, distance_m, duration_s}, linearly
        interpolated between the records just before and just after that
        distance (see _interpolate_record). None if the activity has no records or
        distance_m is outside 0 .. the last record's distance_m.
        """
        return self._interpolate_record('distance_m', distance_m)

    def duration_to_record(self, duration_s):
        """A record synthesized at exactly duration_s seconds into the
        activity (pause-excluding, like the records' duration_s): {lat, lng,
        time, ele, heart_rate, distance_m, duration_s}, linearly interpolated
        between the records just before and just after that duration (see
        _interpolate_record). None if the activity has no records or
        duration_s is outside 0 .. the last record's duration_s.
        """
        return self._interpolate_record('duration_s', duration_s)

    def distance_to_index(self, distance_m):
        """Index into records() of the first record whose distance_m is
        exactly distance_m or the smallest one larger than it. 0 for a
        distance_m at or before the start; None if the activity has no
        records or distance_m is beyond the last record's distance_m.
        """
        return self._index_of('distance_m', distance_m)

    def duration_to_index(self, duration_s):
        """Index into records() of the first record whose duration_s is
        exactly duration_s or the smallest one larger than it (like
        distance_to_index, for the pause-excluding duration). None if the
        activity has no records or duration_s is beyond the last record's
        duration_s.
        """
        return self._index_of('duration_s', duration_s)

    def average_heart_rate(self, start_index, end_index):
        """Mean heart_rate (bpm, a float) over records()[start_index:
        end_index] - start_index included, end_index excluded, e.g. (0, 10)
        averages records 0 through 9. Records without a heart_rate (None)
        are left out; None if no record in the range has one. Indices
        follow Python slicing, so an end_index past the last record just
        means "to the end", and end_index <= start_index gives None.
        """
        rates = [record['heart_rate'] for record in self.records()[start_index:end_index]
                 if record.get('heart_rate') is not None]
        return sum(rates) / len(rates) if rates else None

    def _index_of(self, key, value):
        # Both distance_m and duration_s are non-decreasing along the
        # records, so the first record reaching value is found by binary
        # search (on a plateau - standing still, a pause - the first
        # record of it).
        records = self.records()
        if not records or value > records[-1][key]:
            return None
        if key not in self._keys:
            self._keys[key] = [record[key] for record in records]
        return bisect.bisect_left(self._keys[key], value)

    def _interpolate_record(self, key, value):
        # Both distance_m and duration_s are non-decreasing along the
        # records, so the bracketing pair is found by binary search. Either
        # can stay constant over several records (standing still; a pause),
        # in which case a value on such a plateau resolves to the first
        # record reaching it. lat/lng/ele/time and the other cumulative
        # field are interpolated linearly - fine over the few meters
        # between consecutive GPS points - heart_rate too, rounded to an
        # int. ele, heart_rate or time is None if it is None on either side.
        records = self.records()
        if not records or not (0 <= value <= records[-1][key]):
            return None

        if key not in self._keys:
            self._keys[key] = [record[key] for record in records]
        index = bisect.bisect_left(self._keys[key], value)
        after = records[index]
        if index == 0 or after[key] == value:
            return dict(after)
        before = records[index - 1]

        fraction = (value - before[key]) / (after[key] - before[key])

        def lerp(a, b):
            return None if a is None or b is None else a + (b - a) * fraction

        time = None
        if before['time'] is not None and after['time'] is not None:
            t0, t1 = datetime.fromisoformat(before['time']), datetime.fromisoformat(after['time'])
            time = (t0 + (t1 - t0) * fraction).isoformat()

        heart_rate = lerp(before.get('heart_rate'), after.get('heart_rate'))

        record = {
            'lat': lerp(before['lat'], after['lat']),
            'lng': lerp(before['lng'], after['lng']),
            'time': time,
            'ele': lerp(before['ele'], after['ele']),
            'heart_rate': round(heart_rate) if heart_rate is not None else None,
            'distance_m': lerp(before['distance_m'], after['distance_m']),
            'duration_s': lerp(before['duration_s'], after['duration_s']),
        }
        record[key] = value  # exactly as asked, free of rounding
        return record


class ActivityIterator:
    """Iterates over a FitActivity/TcxActivities/...
    container's activities in chronological order. Each __next__ call
    returns the next activity as an Activity object (a container/timestamp
    pair - see above).

    The same iterator class is shared by all three container classes (each
    gets it via its own __iter__); it only relies on list_activities(),
    which all three already return in chronological order, so there's
    nothing format-specific to know here.
    """

    def __init__(self, container):
        self._container = container
        self._timestamps = iter(container.list_activities())

    def __iter__(self):
        return self

    def __next__(self):
        return Activity(self._container, next(self._timestamps))


class Activities:
    """Base class for FitActivity/TcxActivities/...,
    providing everything about iterating/indexing over a container's
    activities - list_activities, __iter__, __len__, __contains__,
    __getitem__ - since activities are identified and ordered purely by
    their start timestamp, which is the same for all three formats.

    A subclass parses/loads its activities however is appropriate for its
    own format, then calls Activities.__init__ with the resulting list of
    start timestamps in chronological order. That list is stored as-is and
    doesn't change afterward - a subclass still needs its own way to look
    an activity itself up by timestamp (e.g. a dict), this base class only
    knows about their ordering/count/position.
    """

    # add_cumulative_fields only scales a record series to match a stored
    # total if that changes it by at most this fraction (see there).
    MAX_SCALE_DEVIATION = 0.05

    # A gap of at least this many seconds between consecutive records is
    # taken as a pause in formats that don't record pauses themselves
    # (GPX, TCX - see pauses_from_gaps); and a first GPS record at least
    # this long after an activity's recorded start means recording began
    # before the device had a GPS fix (see late_gps_start), a last one this
    # long before its recorded end that the GPS signal was lost before
    # recording ended (see early_gps_end). Devices record
    # a point every 1-10 s or so while moving; gaps of 60 s or more are rare
    # and, checked against real files, are pauses.
    PAUSE_GAP_S = 60

    # ... unless the device's own distance advanced at least this fast
    # (m/s) across the gap: then the device was still recording, only
    # without GPS - a dropout while moving, not a pause.
    PAUSE_MAX_SPEED_MPS = 0.5

    # add_heart_rate interpolates between the two heart rate samples around
    # a record if they are at most this many seconds apart; otherwise (or
    # before the first/after the last sample) it takes the nearest sample
    # if that is at most HEART_RATE_TOLERANCE_S away, else None.
    HEART_RATE_MAX_GAP_S = 60
    HEART_RATE_TOLERANCE_S = 5

    def __init__(self, timestamps):
        self._calendar = Calendar()
        self._timestamps = timestamps
        for timestamp in timestamps:
            self._calendar.add(timestamp)

    @property
    def calendar(self):
        return self._calendar

    def list_activities(self):
        """Every activity's start timestamp (a datetime), in chronological
        order - used as that activity's identifier by summarize_activity/
        extract_records/extract_pauses/extract_elevation.
        """
        return self._timestamps

    def __iter__(self):
        return ActivityIterator(self)

    def __len__(self):
        return len(self._timestamps)

    def __contains__(self, key):
        """key can be an int (0-based position, chronological order) or a
        datetime - in which case this returns whether an activity starts at
        exactly that timestamp.
        """
        if isinstance(key, datetime):
            return key in self._timestamps
        return 0 <= key < len(self._timestamps)

    def __getitem__(self, key):
        """The Activity at position key (0-based, chronological order) if
        key is an int, or the Activity starting at key (a datetime) if key
        is a datetime - raising KeyError if no activity starts exactly then.
        """
        if isinstance(key, datetime):
            if key not in self:
                raise KeyError(key)
            return Activity(self, key)
        return Activity(self, self._timestamps[key])

    def findByTimestamp(self, when):
        """Index (0-based, chronological order) of the first activity whose
        start timestamp is equal to or later than when, or -1 if every
        activity starts earlier.

        when: a date or a datetime, compared as in ActivitiesFilteredByDate
        - a date against each activity's local start date (so any activity
        starting on that day matches), a naive datetime against its local
        wall-clock start time, a timezone-aware one as an exact instant.
        """
        for index, timestamp in enumerate(self._timestamps):
            if self.compare_timestamp(timestamp, when) >= 0:
                return index
        return -1

    def findByLocation(self, lat, lng, distance_km, starting_index=0):
        """Index (0-based, chronological order) of the first activity, at
        or after starting_index, whose start location lies within
        distance_km kilometers (great-circle distance) of lat/lng (degrees),
        or -1 if there is none. Activities with no known start location
        (e.g. GPS-less ones) never match.
        """
        max_distance_m = distance_km * 1000
        for index in range(max(starting_index, 0), len(self._timestamps)):
            location = self.start_location(self, self._timestamps[index])
            if location is not None and self.haversine_m(lat, lng, *location) <= max_distance_m:
                return index
        return -1

    @staticmethod
    def start_location(activities, timestamp):
        """(start_lat, start_lng) of an activity in activities, in degrees -
        or None if it has no known start location (e.g. a GPS-less one).
        """
        summary = activities.summarize_activity(timestamp)
        start_lat, start_lng = summary['start_lat'], summary['start_lng']
        if start_lat is None or start_lng is None:
            return None
        return start_lat, start_lng

    @staticmethod
    def compare_timestamp(timestamp, bound):
        """-1/0/1 as timestamp (an activity's start time, a timezone-aware
        datetime) is before/at/after bound - a date (compared against
        timestamp's local date), a naive datetime (against its local
        wall-clock time) or a timezone-aware datetime (as an exact instant).
        """
        # datetime is a subclass of date, so it has to be checked first.
        if isinstance(bound, datetime):
            if bound.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=None)
        else:
            timestamp = timestamp.date()
        return (timestamp > bound) - (timestamp < bound)

    @classmethod
    def elevation_from_records(cls, records, threshold_m=3.0):
        """Total ascent/descent in meters, estimated from altitude readings.
        Used as a fallback when a source file has no device-reported
        ascent/descent summary of its own.

        Raw altitude readings jitter by a few meters from sample to sample
        even on flat ground, so naively summing every up/down tick between
        consecutive points wildly overcounts - checked against real FIT
        files' own device-reported ascent/descent, that naive sum overshot
        by 50-60%. Instead, this only counts a move once it has accumulated
        to at least threshold_m away from the last confirmed elevation;
        once counted, that point becomes the new reference to measure the
        next move from. This "hysteresis" filter is a standard way to
        reject noise in elevation-gain calculations - the 3m default
        matches the noise floor of typical consumer barometric altimeters,
        and tracks real device-reported totals much more closely than any
        fixed per-step threshold on raw deltas does.

        records: iterable of dicts with an 'ele' key (meters, or None).
        """
        ascent = descent = 0.0
        reference = None

        for record in records:
            ele = record.get('ele')
            if ele is None:
                continue
            if reference is None:
                reference = ele
                continue

            delta = ele - reference
            if delta >= threshold_m:
                ascent += delta
                reference = ele
            elif delta <= -threshold_m:
                descent += -delta
                reference = ele

        return {'ascent': ascent, 'descent': descent}

    @classmethod
    def distance_from_records(cls, records):
        """Total distance in meters along a track, summing great-circle
        (haversine) distances between consecutive points - or None for a
        track with no points. Used as a fallback when a source file has no
        stored distance of its own; checked against SportTracks' own stored
        totals, this lands within about 1% of them.

        records: sequence of dicts with 'lat'/'lng' keys (degrees).
        """
        if not records:
            return None

        distance = 0.0
        for prev, cur in zip(records, records[1:]):
            distance += cls.haversine_m(prev['lat'], prev['lng'], cur['lat'], cur['lng'])

        return distance

    @classmethod
    def add_cumulative_fields(cls, records, pauses, total_distance_m=None, total_duration_s=None):
        """Add 'distance_m' and 'duration_s' to each record (in place), both
        cumulative from the start of the activity: 0 at the first record,
        the activity's totals at the last. Returns records.

        records: list of dicts with 'lat'/'lng' (degrees), 'time' (ISO 8601
        string), and optionally 'device_distance' - a cumulative distance
        in meters recorded by the device itself (FIT record distance, TCX
        DistanceMeters). Where present, a record's distance is the device's
        own, relative to the first record's; elsewhere (and for records
        lacking it) it's the haversine distance from the previous record
        added on. 'device_distance' is removed from each record afterward.
        pauses: list of {start, end} (ISO 8601 strings). Neither value
        increases during a pause: duration_s is time since the first
        record, not counting time spent in these pauses, and any distance
        between two records is only counted for the part of the time
        between them that wasn't paused - so the distance from the last
        record before a pause to the first record after it (moving to a
        different place while paused) is not counted at all.
        total_distance_m/total_duration_s: the activity's totals from its
        summary, if known. When given, distance_m/duration_s are scaled so
        the last record's values equal them exactly - e.g. a computed
        haversine distance is typically within ~1% of a device's total.
        But if that would change them by more than MAX_SCALE_DEVIATION
        (5%), the stored total evidently doesn't describe this track (GPS
        gaps, totals edited by hand, ...), so that series is left
        unscaled and its last value then differs from the total.
        """
        if not records:
            return records

        pause_ranges = sorted(
            (datetime.fromisoformat(p['start']), datetime.fromisoformat(p['end'])) for p in pauses)

        def paused_before(time):
            return sum(max(0.0, (min(time, end) - start).total_seconds())
                       for start, end in pause_ranges if start < time)

        first_time = next((datetime.fromisoformat(r['time']) for r in records if r.get('time')), None)
        distance = duration = 0.0
        prev = prev_time = prev_paused = max_device = None

        for record in records:
            device = record.pop('device_distance', None)
            time = datetime.fromisoformat(record['time']) if record.get('time') else None
            paused = paused_before(time) if time is not None else None

            if prev is not None:
                # The fraction of the time since the previous record that
                # wasn't paused - 1 if either record has no time.
                moving = 1.0
                if time is not None and prev_time is not None:
                    elapsed = (time - prev_time).total_seconds()
                    if elapsed > 0:
                        moving = max(0.0, 1.0 - (paused - prev_paused) / elapsed)
                if device is not None and max_device is not None:
                    step = max(0.0, device - max_device)
                else:
                    step = cls.haversine_m(prev['lat'], prev['lng'], record['lat'], record['lng'])
                distance += step * moving

            if time is not None and first_time is not None:
                duration = max(duration, (time - first_time).total_seconds() - paused)
            if device is not None:
                max_device = device if max_device is None else max(max_device, device)
            record['distance_m'] = distance
            record['duration_s'] = duration
            prev = record
            if time is not None:
                prev_time, prev_paused = time, paused

        for key, total in (('distance_m', total_distance_m), ('duration_s', total_duration_s)):
            last = records[-1][key]
            if total is not None and last > 0:
                factor = total / last
                if abs(factor - 1) > cls.MAX_SCALE_DEVIATION:
                    continue
                for record in records:
                    record[key] *= factor

        return records

    @classmethod
    def add_heart_rate(cls, records, samples):
        """Add 'heart_rate' (beats per minute, an int, or None) to each
        record (in place), matched by time against samples. Returns records.

        samples: (datetime, bpm) pairs, in any order - the activity's heart
        rate readings, which needn't coincide with its GPS records (a FIT/
        TCX device can log heart rate without a position, a logbook keeps a
        separate heart rate track, and Apple Health a separate series of
        readings). Readings of None or 0 (no reading) are ignored.
        A record at exactly a sample's time takes its value; one between two
        samples at most HEART_RATE_MAX_GAP_S apart is interpolated linearly
        between them; otherwise it takes the nearest sample if that is at
        most HEART_RATE_TOLERANCE_S away. Anything else - including every
        record of an activity without heart rate data - gets None.
        """
        samples = sorted((time, bpm) for time, bpm in samples if time is not None and bpm)
        times = [time for time, _ in samples]
        for record in records:
            time = datetime.fromisoformat(record['time']) if record.get('time') and samples else None
            record['heart_rate'] = cls._heart_rate_at(times, samples, time) if time is not None else None
        return records

    @classmethod
    def _heart_rate_at(cls, times, samples, time):
        index = bisect.bisect_left(times, time)
        before = samples[index - 1] if index > 0 else None
        after = samples[index] if index < len(samples) else None
        if after is not None and after[0] == time:
            return after[1]
        if before is not None and after is not None:
            gap = (after[0] - before[0]).total_seconds()
            if gap <= cls.HEART_RATE_MAX_GAP_S:
                fraction = (time - before[0]).total_seconds() / gap
                return round(before[1] + (after[1] - before[1]) * fraction)
        nearest = min((s for s in (before, after) if s is not None),
                      key=lambda s: abs((s[0] - time).total_seconds()), default=None)
        if nearest is not None and abs((nearest[0] - time).total_seconds()) <= cls.HEART_RATE_TOLERANCE_S:
            return nearest[1]
        return None

    @classmethod
    def pauses_from_gaps(cls, times, device_distances=None):
        """Synthesized pause intervals for a format that doesn't record
        pauses: one {start, end} (ISO 8601 strings) for each gap of at least
        PAUSE_GAP_S seconds between consecutive times (datetimes, in track
        order), from the time before the gap to the time after it.

        device_distances: optionally, the device's own cumulative distance
        (meters, or None) at each of those times. A gap across which it
        advanced at PAUSE_MAX_SPEED_MPS or more is a GPS dropout while
        moving, not a pause, and is skipped.
        """
        if device_distances is None:
            device_distances = [None] * len(times)
        pauses = []
        for (prev, d0), (cur, d1) in zip(zip(times, device_distances), list(zip(times, device_distances))[1:]):
            gap = (cur - prev).total_seconds()
            if gap < cls.PAUSE_GAP_S:
                continue
            if d0 is not None and d1 is not None and (d1 - d0) / gap >= cls.PAUSE_MAX_SPEED_MPS:
                continue
            pauses.append({'start': prev.isoformat(), 'end': cur.isoformat()})
        return pauses

    @classmethod
    def late_gps_start(cls, start_time, records):
        """Whether recording started before the device had a GPS fix: the
        first record (a dict with an ISO 8601 'time') comes at least
        PAUSE_GAP_S seconds after the activity's recorded start_time (a
        datetime).
        """
        if start_time is None or not records or not records[0].get('time'):
            return False
        first = datetime.fromisoformat(records[0]['time'])
        return (first - start_time).total_seconds() >= cls.PAUSE_GAP_S

    @classmethod
    def early_gps_end(cls, start_time, records, pauses, total_duration_s):
        """Whether the GPS signal was lost before recording ended: the
        activity's recorded end - start_time (a datetime) plus its stored
        total_duration_s (seconds, excluding pauses) plus its pauses
        ({start, end} ISO 8601 strings) - comes at least PAUSE_GAP_S
        seconds after the last record's ISO 8601 'time'.
        """
        if start_time is None or total_duration_s is None or not records or not records[-1].get('time'):
            return False
        paused = sum((datetime.fromisoformat(p['end']) - datetime.fromisoformat(p['start'])).total_seconds()
                     for p in pauses)
        recorded_end = start_time + timedelta(seconds=total_duration_s + paused)
        last = datetime.fromisoformat(records[-1]['time'])
        return (recorded_end - last).total_seconds() >= cls.PAUSE_GAP_S

    @classmethod
    def stored_totals(cls, start_time, records, pauses, total_distance_m, total_duration_s):
        """(total_distance_m, total_duration_s) as stored in the file for
        an activity - or (None, None) if they cover more than its GPS track
        does, because recording started before the device had a GPS fix
        (late_gps_start) or the GPS signal was lost before recording ended
        (early_gps_end). The activity's totals are then the track's own:
        its last record's distance_m/duration_s.
        records: the activity's records (dicts with an ISO 8601 'time');
        pauses: its pauses ({start, end} ISO 8601 strings); start_time: its
        recorded start (a datetime).
        """
        if (cls.late_gps_start(start_time, records)
                or cls.early_gps_end(start_time, records, pauses, total_duration_s)):
            return None, None
        return total_distance_m, total_duration_s

    @classmethod
    def haversine_m(cls, lat1, lng1, lat2, lng2):
        """Great-circle (haversine) distance in meters between two points
        given in degrees.
        """
        lat1, lng1 = math.radians(lat1), math.radians(lng1)
        lat2, lng2 = math.radians(lat2), math.radians(lng2)
        h = (math.sin((lat2 - lat1) / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
        return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))

    @classmethod
    def parse_timestamp(cls, text):
        """Parse a timestamp string (e.g. from the command line) into a
        datetime, for use with summarize_activity/extract_records/etc.
        Accepts a trailing "Z" or an explicit numeric UTC offset.
        """
        return datetime.fromisoformat(text.replace('Z', '+00:00'))

class FitActivity(Activities):
    """Loads a single .FIT file - from a path or an already-open binary
    stream - and exposes it as one activity. Public API mirrors
    TcxActivities/AppleHealthActivity: list_activities, summarize_activity,
    extract_records, extract_pauses, extract_elevation (plus __iter__/
    __len__/__contains__/__getitem__, from the shared Activities base
    class). list_activities always returns a list of at most one
    timestamp, since a FIT file holds a single activity - but the timestamp
    argument to summarize_activity/extract_records/extract_pauses/
    extract_elevation must still match this file's actual start time, the
    same as the other classes, for full API compatibility when a
    ZippedActivities or MergedActivities delegates here.
    """

    def __init__(self, source, name=None):
        """source: a path (str/os.PathLike) to a .FIT file, or an
        already-open binary stream - a file object, a zipfile.ZipExtFile,
        or anything else Stream.from_buffered_reader accepts.
        name: identifier for this activity (summarize_activity's 'id', and
        used in error messages); defaults to the path, or to the stream's
        own `name` attribute if it has one.
        """
        if isinstance(source, (str, os.PathLike)):
            self.name = name if name is not None else str(source)
            self.messages = self._decode_fit(Stream.from_file(source))
        else:
            self.name = name if name is not None else getattr(source, 'name', None)
            self.messages = self._decode_fit(Stream.from_buffered_reader(source))

        self.utc_offset_seconds = self._extract_utc_offset_seconds(self.messages)
        start_time, start_lat, start_lng = self._session_start(self.messages)
        self.start_time = self._to_local_datetime(start_time, self.utc_offset_seconds)
        self.start_lat = self._semicircles_to_degrees(start_lat)
        self.start_lng = self._semicircles_to_degrees(start_lng)

        super().__init__([self.start_time] if self.start_time is not None else [])

    def summarize_activity(self, timestamp):
        """Summary dict for this activity: id, timestamp, sport,
        distance_m, duration_s, start_lat, start_lng, ascent, descent
        (meters, as returned by extract_elevation).
        """
        self._check_timestamp(timestamp)
        records = self.extract_records(timestamp)
        total_distance_m, total_duration_s = self._totals(records, self.extract_pauses(timestamp))
        if total_distance_m is None and total_duration_s is None and records:
            # incomplete track (or no session totals): the track's own totals
            total_distance_m, total_duration_s = records[-1]['distance_m'], records[-1]['duration_s']
        elevation = self._extract_elevation_from_messages(self.messages, records)

        return {
            'id': self.name,
            'timestamp': self.start_time,
            'sport': self._extract_sport(self.messages),
            'distance_m': total_distance_m,
            'duration_s': total_duration_s,
            'start_lat': self.start_lat,
            'start_lng': self.start_lng,
            'ascent': elevation['ascent'],
            'descent': elevation['descent'],
        }

    def extract_records(self, timestamp):
        """GPS records for this activity: a list of {lat, lng, time (ISO
        8601 string), ele, heart_rate, distance_m, duration_s} - the last two
        cumulative from the start (see Activities.add_cumulative_fields),
        from the device's own record distances, ending at the session's
        total_distance/total_timer_time - unless those cover more than the
        track does (Activities.stored_totals), in which case they aren't
        used.
        """
        self._check_timestamp(timestamp)
        records = self._extract_records_from_messages(self.messages, self.utc_offset_seconds)
        self.add_heart_rate(records, self._extract_heart_rate_from_messages(self.messages))
        pauses = self.extract_pauses(timestamp)
        return self.add_cumulative_fields(records, pauses, *self._totals(records, pauses))

    def _totals(self, records, pauses):
        # (total_distance_m, total_duration_s) from the session summary -
        # (None, None) if they cover more than the track (see stored_totals).
        sessions = self.messages.get('session_mesgs', [])
        session = sessions[0] if sessions else {}
        return self.stored_totals(self.start_time, records, pauses,
                                  session.get('total_distance'), session.get('total_timer_time'))

    def extract_pauses(self, timestamp):
        """Pause intervals for this activity: a list of {start, end} (ISO
        8601 strings), derived from the FIT file's timer stop/start events.
        """
        self._check_timestamp(timestamp)
        return self._extract_pauses_from_messages(self.messages, self.utc_offset_seconds)

    def extract_elevation(self, timestamp):
        """{ascent, descent} in meters for this activity, from the device's
        own summary when present, otherwise estimated from its GPS records.
        """
        self._check_timestamp(timestamp)
        return self._extract_elevation_from_messages(self.messages, self.extract_records(timestamp))

    def _check_timestamp(self, timestamp):
        if self.start_time != timestamp:
            available = self.start_time.isoformat() if self.start_time is not None else '(none)'
            raise ValueError(f'No activity in {self.name} starts at {timestamp.isoformat()}. Available: {available}')

    # --- FIT message decoding/parsing (private) -------------------------

    @classmethod
    def _decode_fit(cls, stream):
        """Decode a garmin_fit_sdk.Stream into its dict of FIT messages."""
        decoder = Decoder(stream)
        messages, errors = decoder.read()
        if errors:
            raise RuntimeError(f'FIT decode errors: {errors}')
        return messages

    @classmethod
    def _extract_utc_offset_seconds(cls, messages):
        # The FIT SDK decodes "timestamp" fields as proper UTC datetimes,
        # but a device's local wall-clock time isn't stored anywhere as a
        # timezone - it has to be derived. The "activity" message's
        # local_timestamp field is the FIT-documented way to do this: it's
        # the same instant as timestamp, but expressed as if it were UTC,
        # so the delta between the two is the device's configured UTC
        # offset in seconds.
        for mesg in messages.get('activity_mesgs', []):
            timestamp = mesg.get('timestamp')
            local_timestamp = mesg.get('local_timestamp')
            if timestamp is not None and local_timestamp is not None:
                timestamp_fit_epoch_seconds = timestamp.timestamp() - FIT_EPOCH
                return round(local_timestamp - timestamp_fit_epoch_seconds)

        # Fallback: device_settings' own record of its configured UTC offset.
        for mesg in messages.get('device_settings_mesgs', []):
            offset = mesg.get('time_offset')
            if offset:
                return int(offset)

        return 0

    @classmethod
    def _to_local_datetime(cls, timestamp, utc_offset_seconds):
        if timestamp is None:
            return None
        local_tz = timezone(timedelta(seconds=utc_offset_seconds))
        return timestamp.astimezone(local_tz)

    @classmethod
    def _to_local_iso(cls, timestamp, utc_offset_seconds):
        local_dt = cls._to_local_datetime(timestamp, utc_offset_seconds)
        return local_dt.isoformat() if local_dt is not None else None

    @classmethod
    def _extract_sport(cls, messages):
        for mesg in messages.get('session_mesgs', []):
            sport = mesg.get('sport')
            if sport in KNOWN_SPORTS:
                return sport
        return 'moving'

    @classmethod
    def _semicircles_to_degrees(cls, value):
        if value is None or value == INVALID_LAT_LON:
            return None
        return value * SEMICIRCLE_TO_DEGREE

    @classmethod
    def _extract_records_from_messages(cls, messages, utc_offset_seconds):
        records = []
        for mesg in messages.get('record_mesgs', []):
            lat = mesg.get('position_lat')
            lon = mesg.get('position_long')
            if lat is None or lon is None or lat == INVALID_LAT_LON or lon == INVALID_LAT_LON:
                continue

            altitude = mesg.get('enhanced_altitude', mesg.get('altitude'))

            records.append({
                'lat': lat * SEMICIRCLE_TO_DEGREE,
                'lng': lon * SEMICIRCLE_TO_DEGREE,
                'time': cls._to_local_iso(mesg.get('timestamp'), utc_offset_seconds),
                'ele': altitude,
                'device_distance': mesg.get('distance'),
            })

        return records

    @classmethod
    def _extract_heart_rate_from_messages(cls, messages):
        # (UTC datetime, bpm) for every record message with a heart rate -
        # including those without a position (e.g. before the GPS fix), so
        # a GPS record lacking one of its own can be matched to a nearby
        # reading (see add_heart_rate). 255 is FIT's "invalid" uint8.
        return [(mesg.get('timestamp'), mesg.get('heart_rate'))
                for mesg in messages.get('record_mesgs', [])
                if mesg.get('heart_rate') not in (None, 0, 255)]

    @classmethod
    def _extract_pauses_from_messages(cls, messages, utc_offset_seconds):
        # Pairs up timer stop/start "event" messages into pause intervals.
        # A file can auto-pause and resume any number of times; each stop
        # is matched with the next start that follows it.
        pauses = []
        pause_start = None

        for mesg in messages.get('event_mesgs', []):
            if mesg.get('event') != 'timer':
                continue

            timestamp = mesg.get('timestamp')
            event_type = mesg.get('event_type')
            if timestamp is None:
                continue

            if pause_start is None and event_type in ('stop', 'stop_all'):
                pause_start = timestamp
            elif pause_start is not None and event_type == 'start':
                pauses.append({
                    'start': cls._to_local_iso(pause_start, utc_offset_seconds),
                    'end': cls._to_local_iso(timestamp, utc_offset_seconds),
                })
                pause_start = None

        return pauses

    @classmethod
    def _extract_elevation_from_messages(cls, messages, records):
        for mesg in messages.get('session_mesgs', []):
            ascent = mesg.get('total_ascent')
            descent = mesg.get('total_descent')
            if ascent is not None and descent is not None:
                return {'ascent': ascent, 'descent': descent}

        # Fallback for files without a session summary.
        return cls.elevation_from_records(records)

    @classmethod
    def _session_start(cls, messages):
        # Returns (start_time, start_lat, start_lng) - raw FIT values (a UTC
        # datetime, semicircle ints) - preferring the session summary,
        # falling back to the first GPS-carrying record for files whose
        # session summary is missing or incomplete.
        sessions = messages.get('session_mesgs', [])
        session = sessions[0] if sessions else {}
        start_time = session.get('start_time')
        start_lat = session.get('start_position_lat')
        start_lng = session.get('start_position_long')

        if start_time is None or start_lat is None or start_lng is None:
            for mesg in messages.get('record_mesgs', []):
                lat = mesg.get('position_lat')
                lon = mesg.get('position_long')
                if lat is not None and lon is not None and lat != INVALID_LAT_LON and lon != INVALID_LAT_LON:
                    start_time = start_time if start_time is not None else mesg.get('timestamp')
                    start_lat = start_lat if start_lat is not None else lat
                    start_lng = start_lng if start_lng is not None else lon
                    break

        return start_time, start_lat, start_lng


class TcxActivities(Activities):
    """Loads every activity in a .tcx file. Public API mirrors
    FitActivity/AppleHealthActivity: list_activities, summarize_activity,
    extract_records, extract_pauses, extract_elevation (plus __iter__/
    __len__/__contains__/__getitem__, from the shared Activities base
    class). The four per-activity methods take one of the timestamps
    list_activities() returns; passing anything else raises KeyError.
    """

    NS = {'tcx': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'}

    # TCX "Sport" attribute values this app has a specific label for;
    # anything else (e.g. "Other") is reported as the generic "moving",
    # matching the FIT-side convention (see KNOWN_SPORTS above).
    SPORT_MAP = {'Running': 'running', 'Biking': 'cycling'}

    def __init__(self, source, name=None):
        """Load and fully parse every activity in a .tcx file. Memory usage
        is not a concern here, unlike the previous iterparse-based version -
        the whole file is parsed up front.
        source: a path to a .tcx file, or an already-open file object (e.g.
        a zipfile.ZipExtFile).
        name: identifier for the file; defaults to the path, or to the
        stream's own `name` attribute if it has one.
        """
        self.name = name if name is not None else (
            str(source) if isinstance(source, (str, os.PathLike)) else getattr(source, 'name', None))
        tree = ET.parse(source)
        self._activities = {}  # start time (datetime) -> parsed activity dict
        for activity_elem in tree.getroot().findall('tcx:Activities/tcx:Activity', self.NS):
            activity_id = self._child_text(activity_elem, 'Id')
            try:
                activity = self._parse_activity(activity_elem)
            except Exception as err:
                print(f'warning: skipping activity {activity_id}: {err}', file=sys.stderr)
                continue
            start_time = activity['start_time']
            if start_time is None:
                print(f'warning: activity {activity_id} has no determinable start time, excluding it', file=sys.stderr)
                continue
            if start_time in self._activities:
                print(f'warning: activity {activity_id} starts at the same time as another one, excluding it', file=sys.stderr)
                continue
            self._activities[start_time] = activity

        super().__init__(sorted(self._activities.keys()))

    # --- per-activity access, given a timestamp -----------------------

    def summarize_activity(self, timestamp):
        """Summary dict for the activity starting at timestamp (a datetime,
        as returned by list_activities): id, timestamp, sport, distance_m,
        duration_s, start_lat, start_lng, ascent, descent (meters, as
        returned by extract_elevation).
        """
        activity = self._activities[timestamp]
        records = self.extract_records(timestamp)
        total_distance_m, total_duration_s = self._totals(activity, records)
        if total_distance_m is None and total_duration_s is None and records:
            # incomplete track: the track's own totals - see stored_totals
            total_distance_m, total_duration_s = records[-1]['distance_m'], records[-1]['duration_s']
        first = self._first_trackpoint(activity)
        elevation = self.elevation_from_records(records)

        return {
            'id': activity['id'],
            'timestamp': activity['start_time'],
            'sport': activity['sport'],
            'distance_m': total_distance_m,
            'duration_s': total_duration_s,
            'start_lat': first['lat'] if first else None,
            'start_lng': first['lng'] if first else None,
            'ascent': elevation['ascent'],
            'descent': elevation['descent'],
        }

    def extract_records(self, timestamp):
        """GPS records for the activity starting at timestamp (a datetime,
        as returned by list_activities): a list of {lat, lng, time (ISO 8601
        string), ele, heart_rate, distance_m, duration_s}, laps combined into one
        continuous track, in order. distance_m/duration_s are cumulative from
        the start (see Activities.add_cumulative_fields), from the
        trackpoints' own DistanceMeters where present, not increasing during
        pauses (see extract_pauses), ending at the laps' total
        DistanceMeters/TotalTimeSeconds - unless those cover more than the
        track does (Activities.stored_totals), in which case they aren't
        used.
        """
        activity = self._activities[timestamp]
        trackpoints = self._merged_trackpoints(activity)
        records = [
            {'lat': tp['lat'], 'lng': tp['lng'], 'time': tp['time'].isoformat(), 'ele': tp['ele'],
             'device_distance': tp['distance']}
            for tp in trackpoints
        ]
        self.add_heart_rate(records, activity['heart_rate'])
        pauses = self._pauses(trackpoints)
        return self.add_cumulative_fields(records, pauses, *self._totals(activity, records))

    def extract_pauses(self, timestamp):
        """Pause intervals for the activity starting at timestamp: a list
        of {start, end} (ISO 8601 strings). TCX has no equivalent of FIT's
        timer stop/start events, but a device stops recording trackpoints
        while paused, so they are synthesized from gaps of at least
        PAUSE_GAP_S seconds between trackpoints across which the
        trackpoints' DistanceMeters barely advanced
        (Activities.pauses_from_gaps).
        """
        activity = self._activities[timestamp]
        return self._pauses(self._merged_trackpoints(activity))

    def _pauses(self, trackpoints):
        return self.pauses_from_gaps([tp['time'] for tp in trackpoints],
                                     [tp['distance'] for tp in trackpoints])

    def _totals(self, activity, records):
        # (total_distance_m, total_duration_s) from the laps - (None, None)
        # if they cover more than the track (see stored_totals).
        return self.stored_totals(activity['start_time'], records,
                                  self._pauses(self._merged_trackpoints(activity)),
                                  *self._lap_totals(activity))

    def extract_elevation(self, timestamp):
        """{ascent, descent} in meters for the activity starting at
        timestamp, estimated by summing consecutive altitude changes across
        its records (Activities.elevation_from_records) - TCX has no
        device-reported ascent/descent summary to prefer instead, unlike
        FIT.
        """
        return self.elevation_from_records(self.extract_records(timestamp))

    # --- trackpoint helpers ----------------------------------------------

    @staticmethod
    def _lap_totals(activity):
        # (distance_m, duration_s) summed over the activity's laps - each
        # None if no lap has that value.
        laps = activity['laps']
        distances = [lap['distance_m'] for lap in laps if lap['distance_m'] is not None]
        durations = [lap['total_time_s'] for lap in laps if lap['total_time_s'] is not None]
        return (sum(distances) if distances else None, sum(durations) if durations else None)

    def _first_trackpoint(self, activity):
        trackpoints = self._merged_trackpoints(activity)
        return trackpoints[0] if trackpoints else None

    @staticmethod
    def _merged_trackpoints(activity):
        # All of an activity's laps' trackpoints combined into one track, in
        # order (laps are already chronological within the file).
        return [tp for lap in activity['laps'] for tp in lap['trackpoints']]

    # --- XML parsing (private) ------------------------------------------

    @classmethod
    def _sport_for(cls, sport_attr):
        return cls.SPORT_MAP.get(sport_attr, 'moving')

    @classmethod
    def _child_text(cls, elem, tag):
        child = elem.find(f'tcx:{tag}', cls.NS)
        return child.text if child is not None and child.text is not None else None

    @classmethod
    def _child_float(cls, elem, tag):
        text = cls._child_text(elem, tag)
        return float(text) if text is not None else None

    @classmethod
    def _parse_trackpoint(cls, tp_elem):
        # Returns None for a <Trackpoint> lacking a Time or Position (e.g.
        # an indoor/GPS-less sample) - such points can't be plotted anyway.
        time_text = cls._child_text(tp_elem, 'Time')
        if time_text is None:
            return None

        position = tp_elem.find('tcx:Position', cls.NS)
        if position is None:
            return None
        lat_text = cls._child_text(position, 'LatitudeDegrees')
        lng_text = cls._child_text(position, 'LongitudeDegrees')
        if lat_text is None or lng_text is None:
            return None

        return {
            'time': cls.parse_timestamp(time_text),
            'lat': float(lat_text),
            'lng': float(lng_text),
            'ele': cls._child_float(tp_elem, 'AltitudeMeters'),
            'distance': cls._child_float(tp_elem, 'DistanceMeters'),
        }

    @classmethod
    def _parse_heart_rate(cls, tp_elem):
        # (datetime, bpm) from a <Trackpoint>'s <HeartRateBpm><Value>, or
        # None if it has no time or heart rate.
        time_text = cls._child_text(tp_elem, 'Time')
        hr_elem = tp_elem.find('tcx:HeartRateBpm', cls.NS)
        value = cls._child_text(hr_elem, 'Value') if hr_elem is not None else None
        if time_text is None or value is None:
            return None
        try:
            return cls.parse_timestamp(time_text), round(float(value))
        except ValueError:
            return None

    @classmethod
    def _parse_activity(cls, activity_elem):
        # {'id': str, 'start_time': datetime, 'sport': str, 'laps': [lap, ...],
        #  'heart_rate': [(datetime, bpm), ...]},
        # where each lap is
        # {'start_time': str, 'total_time_s': float, 'distance_m': float,
        #  'trackpoints': [trackpoint, ...]}.
        laps = []
        heart_rate = []  # (datetime, bpm) from every trackpoint, with a position or not
        for lap_elem in activity_elem.findall('tcx:Lap', cls.NS):
            trackpoints = []
            for tp_elem in lap_elem.findall('tcx:Track/tcx:Trackpoint', cls.NS):
                tp = cls._parse_trackpoint(tp_elem)
                if tp is not None:
                    trackpoints.append(tp)
                sample = cls._parse_heart_rate(tp_elem)
                if sample is not None:
                    heart_rate.append(sample)

            laps.append({
                'start_time': lap_elem.get('StartTime'),
                'total_time_s': cls._child_float(lap_elem, 'TotalTimeSeconds'),
                'distance_m': cls._child_float(lap_elem, 'DistanceMeters'),
                'trackpoints': trackpoints,
            })

        # The activity starts at its <Id> (by TCX convention its start
        # time), else its first lap's StartTime, else its first trackpoint
        # - not necessarily the first trackpoint, as recording can begin
        # before the device has a GPS fix.
        activity_id = cls._child_text(activity_elem, 'Id')
        start_time = None
        for text in (activity_id, laps[0]['start_time'] if laps else None):
            try:
                start_time = cls.parse_timestamp(text)
                break
            except (TypeError, ValueError):
                pass
        if start_time is None:
            start_time = next((lap['trackpoints'][0]['time'] for lap in laps if lap['trackpoints']), None)

        return {
            'id': activity_id,
            'start_time': start_time,
            'sport': cls._sport_for(activity_elem.get('Sport')),
            'laps': laps,
            'heart_rate': heart_rate,
        }


class Logbook3Activities(Activities):
    """Loads every activity in a SportTracks 3 logbook (.logbook3) file.
    Public API mirrors FitActivity/TcxActivities/...:
    list_activities, summarize_activity, extract_records, extract_pauses,
    extract_elevation (plus __iter__/__len__/__contains__/__getitem__, from
    the shared Activities base class). The four per-activity methods take
    one of the timestamps list_activities() returns; passing anything else
    raises KeyError.

    A logbook is XML, with one <Activity> element per activity under
    <Athlete>/<Activities>. Its totals are attributes on <Activity>; its GPS
    track is a binary, base64-encoded <GPSRoute>/<TrackData> (see
    _decode_gps_route). Unlike TCX, each activity records its own
    timeZoneUtcOffset, so - like FIT - times here are converted to the
    activity's local time zone. Activities without a <GPSRoute> (manually
    entered ones, treadmill runs, ...) are still listed, just with no
    records.
    """

    NS = {'st': 'urn:uuid:D0EB2ED5-49B6-44e3-B13C-CF15BE7DD7DD'}

    # SportTracks category names this app has a specific label for;
    # categories are user-defined, so anything else is reported as the
    # generic "moving", matching the FIT-side convention (see KNOWN_SPORTS).
    SPORT_MAP = {'Running': 'running', 'Cycling': 'cycling'}

    # <TrackData version="4"> timestamps count seconds from this epoch, UTC.
    TRACK_EPOCH = datetime(1990, 1, 1, tzinfo=timezone.utc)

    def __init__(self, source, name=None):
        """Load and fully parse every activity in a .logbook3 file. Memory
        usage is not a concern - the whole file is parsed up front, GPS
        routes included.
        source: a path to a .logbook3 file, or an already-open file object
        (e.g. a zipfile.ZipExtFile).
        name: identifier for the file; defaults to the path, or to the
        stream's own `name` attribute if it has one.
        """
        self.name = name if name is not None else (
            str(source) if isinstance(source, (str, os.PathLike)) else getattr(source, 'name', None))
        tree = ET.parse(source)
        self._activities = {}  # start time (datetime) -> parsed activity dict
        for activity_elem in tree.getroot().iter(f'{{{self.NS["st"]}}}Activity'):
            activity_id = activity_elem.get('referenceId')
            try:
                activity = self._parse_activity(activity_elem)
            except Exception as err:
                print(f'warning: skipping activity {activity_id}: {err}', file=sys.stderr)
                continue
            start_time = activity['start_time']
            if start_time is None:
                print(f'warning: activity {activity_id} has no determinable start time, excluding it', file=sys.stderr)
                continue
            if start_time in self._activities:
                print(f'warning: activity {activity_id} starts at the same time as another one, excluding it', file=sys.stderr)
                continue
            self._activities[start_time] = activity

        super().__init__(sorted(self._activities.keys()))

    # --- per-activity access, given a timestamp -----------------------

    def summarize_activity(self, timestamp):
        """Summary dict for the activity starting at timestamp (a datetime,
        as returned by list_activities): id, timestamp, sport, distance_m,
        duration_s, start_lat, start_lng, ascent, descent (meters, as
        returned by extract_elevation).
        """
        activity = self._activities[timestamp]
        records = activity['records']
        first = records[0] if records else None
        total_distance_m, total_duration_s = self._totals(activity)
        if total_distance_m is None and total_duration_s is None and records:
            # incomplete track: the track's own totals - see stored_totals
            last = self.extract_records(timestamp)[-1]
            total_distance_m, total_duration_s = last['distance_m'], last['duration_s']
        elevation = self.extract_elevation(timestamp)

        return {
            'id': activity['id'],
            'timestamp': activity['start_time'],
            'sport': activity['sport'],
            'distance_m': total_distance_m,
            'duration_s': total_duration_s,
            'start_lat': first['lat'] if first else None,
            'start_lng': first['lng'] if first else None,
            'ascent': elevation['ascent'],
            'descent': elevation['descent'],
        }

    def extract_records(self, timestamp):
        """GPS records for the activity starting at timestamp (a datetime,
        as returned by list_activities): a list of {lat, lng, time (ISO 8601
        string), ele, heart_rate, distance_m, duration_s}, decoded from its <GPSRoute> -
        [] if it has none. distance_m/duration_s are cumulative from the
        start (see Activities.add_cumulative_fields), computed from the
        track and its <TimerPauses> (neither increasing during a pause),
        ending at the activity's totalDistance/totalTime - unless those
        cover more than the track does (Activities.stored_totals), in which
        case they aren't used.
        """
        activity = self._activities[timestamp]
        records = self.add_heart_rate([dict(record) for record in activity['records']], activity['heart_rate'])
        return self.add_cumulative_fields(records, activity['pauses'], *self._totals(activity))

    def _totals(self, activity):
        # (total_distance_m, total_duration_s) as stored - (None, None) if
        # they cover more than the track (see stored_totals).
        return self.stored_totals(activity['start_time'], activity['records'], activity['pauses'],
                                  activity['distance_m'], activity['duration_s'])

    def extract_pauses(self, timestamp):
        """Pause intervals for the activity starting at timestamp: a list of
        {start, end} (ISO 8601 strings), from its <TimerPauses>.
        """
        activity = self._activities[timestamp]
        return [dict(pause) for pause in activity['pauses']]

    def extract_elevation(self, timestamp):
        """{ascent, descent} in meters for the activity starting at
        timestamp, from its totalAscend/totalDescend attributes when
        present, otherwise estimated from its GPS records.
        """
        activity = self._activities[timestamp]
        if activity['elevation'] is not None:
            return dict(activity['elevation'])
        return self.elevation_from_records(activity['records'])

    # --- XML/track parsing (private) ------------------------------------

    @classmethod
    def _sport_for(cls, category_name):
        return cls.SPORT_MAP.get(category_name, 'moving')

    @staticmethod
    def _float_attr(elem, name):
        text = elem.get(name)
        return float(text) if text is not None else None

    @classmethod
    def _parse_activity(cls, activity_elem):
        # {'id', 'start_time', 'sport', 'distance_m', 'duration_s',
        #  'elevation', 'records', 'pauses', 'heart_rate'} - times already
        # converted to the activity's local time zone (heart_rate's are UTC
        # datetimes, which compare fine against them).
        offset_hours = cls._float_attr(activity_elem, 'timeZoneUtcOffset') or 0.0
        local_tz = timezone(timedelta(hours=offset_hours))

        start_text = activity_elem.get('startTime')
        start_time = cls.parse_timestamp(start_text).astimezone(local_tz) if start_text else None

        ascent = cls._float_attr(activity_elem, 'totalAscend')
        descent = cls._float_attr(activity_elem, 'totalDescend')
        # SportTracks stores the descent as a negative number.
        elevation = {'ascent': ascent, 'descent': abs(descent)} if ascent is not None and descent is not None else None

        track_data = activity_elem.find('st:GPSRoute/st:TrackData', cls.NS)
        records = []
        if track_data is not None and track_data.text:
            version = track_data.get('version')
            if version != '4':
                raise ValueError(f'unsupported GPSRoute TrackData version {version}')
            records = [
                {'lat': lat, 'lng': lng, 'time': time.astimezone(local_tz).isoformat(), 'ele': ele}
                for time, lat, lng, ele in cls._decode_gps_route(base64.b64decode(track_data.text))
            ]

        hr_data = activity_elem.find('st:HeartRateTrack/st:TrackData', cls.NS)
        heart_rate = []
        if hr_data is not None and hr_data.text:
            # Heart rate is secondary: if it can't be decoded, keep the
            # activity, just without it.
            try:
                version = hr_data.get('version')
                if version != '4':
                    raise ValueError(f'unsupported TrackData version {version}')
                heart_rate = list(cls._decode_heart_rate_track(base64.b64decode(hr_data.text)))
            except (ValueError, IndexError, struct.error) as err:
                print(f'warning: activity {activity_elem.get("referenceId")}: '
                      f'ignoring its heart rate track: {err}', file=sys.stderr)

        pauses = []
        for pause_elem in activity_elem.findall('st:TimerPauses/st:Pause', cls.NS):
            pause_start = cls.parse_timestamp(pause_elem.get('start')).astimezone(local_tz)
            pause_end = pause_start + timedelta(seconds=float(pause_elem.get('duration', 0)))
            pauses.append({'start': pause_start.isoformat(), 'end': pause_end.isoformat()})

        return {
            'id': activity_elem.get('referenceId'),
            'start_time': start_time,
            'sport': cls._sport_for(activity_elem.get('categoryName')),
            # A few GPS-tracked activities have no stored totalDistance at
            # all (SportTracks derives it from the track on the fly).
            'distance_m': cls._float_attr(activity_elem, 'totalDistance') or cls.distance_from_records(records),
            'duration_s': cls._float_attr(activity_elem, 'totalTime'),
            'elevation': elevation,
            'records': records,
            'pauses': pauses,
            'heart_rate': heart_rate,
        }

    @classmethod
    def _decode_heart_rate_track(cls, data):
        # Yields (time as UTC datetime, bpm) for each reading of a version 4
        # <HeartRateTrack>. After one leading byte (always 1 - presumably
        # bytes per value), the track is a sequence of blocks:
        #   int64  block start, seconds since TRACK_EPOCH (0 ends the track)
        #   uint8  number of readings in the block
        #   uint8  layout: 0 = per reading, uint8 seconds since block start
        #          then uint8 bpm; 1 = one uint8 bpm per second from the
        #          block start on (no offsets stored)
        # A bpm of 0 means no reading. (Reverse-engineered: this decodes
        # every heart rate track in a real logbook to exactly its end.)
        if not data or data[0] != 1:
            raise ValueError('unsupported HeartRateTrack layout')
        pos = 1
        while pos + 8 <= len(data):
            (block_start,) = struct.unpack_from('<q', data, pos)
            pos += 8
            if block_start == 0 or pos + 2 > len(data):
                break
            count, layout = data[pos], data[pos + 1]
            pos += 2
            block_time = cls.TRACK_EPOCH + timedelta(seconds=block_start)
            if layout == 0:
                readings = [(data[pos + 2 * i], data[pos + 2 * i + 1]) for i in range(count)]
                pos += 2 * count
            elif layout == 1:
                readings = list(enumerate(data[pos:pos + count]))
                pos += count
            else:
                raise ValueError(f'unsupported HeartRateTrack block layout {layout}')
            for offset, bpm in readings:
                if bpm:
                    yield block_time + timedelta(seconds=offset), bpm

    @classmethod
    def _decode_gps_route(cls, data):
        # Yields (time as UTC datetime, lat, lng, ele) for each point of a
        # version 4 <GPSRoute> track. The track is a sequence of blocks:
        #   int64  block start, seconds since TRACK_EPOCH (0 ends the track)
        #   uint8  number of points in the block
        #   per point: uint8 seconds since block start, then float32
        #              latitude, longitude, and elevation (meters; NaN if
        #              unknown)
        # all little-endian. A block spans at most 255 seconds, since each
        # point's offset from its block start must fit in one byte.
        pos = 0
        while pos + 8 <= len(data):
            (block_start,) = struct.unpack_from('<q', data, pos)
            pos += 8
            if block_start == 0:
                break
            count = data[pos]
            pos += 1
            block_time = cls.TRACK_EPOCH + timedelta(seconds=block_start)
            for _ in range(count):
                offset, lat, lng, ele = struct.unpack_from('<Bfff', data, pos)
                pos += 13
                if math.isnan(lat) or math.isnan(lng):
                    continue
                yield block_time + timedelta(seconds=offset), lat, lng, (None if math.isnan(ele) else ele)


class AppleHealthActivity(Activities):
    """Loads a single workout route .gpx file from an Apple Health export
    (the files under its workout-routes/ directory) - from a path or an
    already-open binary stream - and exposes it as one activity. Public API
    mirrors FitActivity: list_activities, summarize_activity,
    extract_records, extract_pauses, extract_elevation (plus __iter__/
    __len__/__contains__/__getitem__, from the shared Activities base
    class). list_activities returns at most one timestamp, and the timestamp
    argument to the four per-activity methods must match it.

    Such a GPX file is just one <trk> of <trkpt>s (lat/lon, <ele>, UTC
    <time>, plus speed/course/accuracy extensions) - no sport, distance,
    duration, ascent or pause information. So:
    - sport is "moving" unless the track has a GPX <type> naming a known
      sport (Apple's export never writes one);
    - ascent/descent are computed from the track
      (Activities.elevation_from_records);
    - pauses are inferred from gaps in the track of at least
      PAUSE_GAP_S seconds, since Apple stops recording points while a
      workout is paused;
    - distance and duration (elapsed time from first to last point, minus
      pauses) are the last record's cumulative distance_m/duration_s;
    - heart rate comes from the export's export.xml (its heart rate
      <Record>s during the route), when that is at hand - see __init__.

    Times in the file are UTC, but Apple names each file after the
    workout's end in the phone's local time, e.g. "route_2026-09-29_3.03pm.gpx"
    for a track ending at 13:03:24Z in Munich (UTC+2). The UTC offset is
    recovered from that difference (rounded to 15 minutes), so - like FIT -
    times are converted to local time. If the name doesn't follow that
    pattern (or the result is implausible), times stay in UTC.
    """

    NS = {'gpx': 'http://www.topografix.com/GPX/1/1'}

    # GPX <type> values (lowercased) this app has a specific label for.
    SPORT_MAP = {'running': 'running', 'run': 'running', 'cycling': 'cycling', 'biking': 'cycling'}

    FILENAME_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})_(\d{1,2})\.(\d{2})\s*([ap]m)', re.IGNORECASE)

    HEART_RATE_TYPE = 'HKQuantityTypeIdentifierHeartRate'

    # Parsed heart rate series of export XML files, by absolute path, so a
    # folder of routes reads its export only once (see _find_heart_rate).
    _export_cache = {}

    def __init__(self, source, name=None, heart_rate=None):
        """source: a path (str/os.PathLike) to a .gpx file, or an
        already-open file object (e.g. a zipfile.ZipExtFile).
        name: identifier for this activity (summarize_activity's 'id', and
        used in error messages, and to recover the UTC offset); defaults to
        the path, or to the stream's own `name` attribute if it has one.
        heart_rate: the export's heart rate readings, as returned by
        read_heart_rate - the route file itself has none. If not given and
        source is a path, the export XML is looked for in the route's own
        folder and the one above it (Apple's export puts the routes in a
        workout-routes/ subfolder next to export.xml); without one, every
        record's heart_rate is None.
        """
        if isinstance(source, (str, os.PathLike)):
            self.name = name if name is not None else str(source)
            if heart_rate is None:
                heart_rate = self._find_heart_rate(source)
        else:
            self.name = name if name is not None else getattr(source, 'name', None)

        root = ET.parse(source).getroot()
        trk = root.find('gpx:trk', self.NS)
        sport_text = self._child_text(trk, 'type') if trk is not None else None
        self.sport = self.SPORT_MAP.get((sport_text or '').strip().lower(), 'moving')

        points = []  # (UTC datetime, lat, lng, ele)
        for trkpt in root.iterfind('gpx:trk/gpx:trkseg/gpx:trkpt', self.NS):
            time_text = self._child_text(trkpt, 'time')
            lat, lng = trkpt.get('lat'), trkpt.get('lon')
            if time_text is None or lat is None or lng is None:
                continue
            ele = self._child_text(trkpt, 'ele')
            points.append((self.parse_timestamp(time_text), float(lat), float(lng),
                           float(ele) if ele is not None else None))
        points.sort(key=lambda p: p[0])

        self.utc_offset_seconds = self._utc_offset_from_name(self.name, points[-1][0]) if points else 0
        local_tz = timezone(timedelta(seconds=self.utc_offset_seconds))
        self._points = [(time.astimezone(local_tz), lat, lng, ele) for time, lat, lng, ele in points]

        self.start_time = self._points[0][0] if self._points else None
        self.start_lat = self._points[0][1] if self._points else None
        self.start_lng = self._points[0][2] if self._points else None

        # Keep only the readings during the route (plus a margin for
        # add_heart_rate's matching) - an export spans years.
        self._heart_rate = []
        if heart_rate and self._points:
            margin = timedelta(seconds=self.HEART_RATE_MAX_GAP_S)
            times = [time for time, _ in heart_rate]
            first = bisect.bisect_left(times, self._points[0][0] - margin)
            last = bisect.bisect_right(times, self._points[-1][0] + margin)
            self._heart_rate = heart_rate[first:last]

        super().__init__([self.start_time] if self.start_time is not None else [])

    def summarize_activity(self, timestamp):
        """Summary dict for this activity: id, timestamp, sport,
        distance_m, duration_s, start_lat, start_lng, ascent, descent
        (meters, as returned by extract_elevation).
        """
        self._check_timestamp(timestamp)
        # The file has no totals of its own: they are the last record's
        # cumulative distance and (pause-excluding) duration.
        records = self.extract_records(timestamp)
        elevation = self.elevation_from_records(records)

        return {
            'id': self.name,
            'timestamp': self.start_time,
            'sport': self.sport,
            'distance_m': records[-1]['distance_m'],
            'duration_s': records[-1]['duration_s'],
            'start_lat': self.start_lat,
            'start_lng': self.start_lng,
            'ascent': elevation['ascent'],
            'descent': elevation['descent'],
        }

    def extract_records(self, timestamp):
        """GPS records for this activity: a list of {lat, lng, time (ISO
        8601 string), ele, heart_rate, distance_m, duration_s} - the last two cumulative
        from the start (see Activities.add_cumulative_fields), computed from
        the track and its inferred pauses.
        """
        self._check_timestamp(timestamp)
        records = [{'lat': lat, 'lng': lng, 'time': time.isoformat(), 'ele': ele}
                   for time, lat, lng, ele in self._points]
        self.add_heart_rate(records, self._heart_rate)
        return self.add_cumulative_fields(records, self.extract_pauses(timestamp))

    def extract_pauses(self, timestamp):
        """Pause intervals for this activity: a list of {start, end} (ISO
        8601 strings), inferred from gaps of at least PAUSE_GAP_S seconds
        between consecutive track points.
        """
        self._check_timestamp(timestamp)
        return self.pauses_from_gaps([point[0] for point in self._points])

    def extract_elevation(self, timestamp):
        """{ascent, descent} in meters for this activity, estimated from its
        GPS records - the GPX file has no ascent/descent summary.
        """
        return self.elevation_from_records(self.extract_records(timestamp))

    def _check_timestamp(self, timestamp):
        if self.start_time is None or self.start_time != timestamp:
            available = self.start_time.isoformat() if self.start_time is not None else '(none)'
            raise ValueError(f'No activity in {self.name} starts at {timestamp.isoformat()}. Available: {available}')

    # --- heart rate from the Apple Health export ------------------------

    @classmethod
    def read_heart_rate(cls, source):
        """Every heart rate reading in an Apple Health export XML file
        (export.xml - <HealthData> with <Record type=
        "HKQuantityTypeIdentifierHeartRate" startDate=... value=...>
        elements), as a list of (datetime, bpm int) sorted by time. Returns
        None if source isn't a <HealthData> document (or isn't XML at all).
        source: a path or an open binary stream. The file is streamed, not
        loaded whole - a full export can be gigabytes.
        """
        samples = []
        try:
            context = ET.iterparse(source, events=('start', 'end'))
            _, root = next(context)
            if root.tag != 'HealthData':
                return None
            depth = 1  # inside root
            for event, elem in context:
                if event == 'start':
                    depth += 1
                    continue
                depth -= 1
                if depth != 1:
                    continue  # only look at (and free) the root's direct children
                if elem.tag == 'Record' and elem.get('type') == cls.HEART_RATE_TYPE:
                    try:
                        time = datetime.strptime(elem.get('startDate'), '%Y-%m-%d %H:%M:%S %z')
                        samples.append((time, round(float(elem.get('value')))))
                    except (TypeError, ValueError):
                        pass
                root.clear()
        except (ET.ParseError, StopIteration):
            return None
        samples.sort(key=lambda sample: sample[0])
        return samples

    @classmethod
    def _find_heart_rate(cls, gpx_path):
        # The heart rate readings of the first Apple Health export XML in
        # the route's folder or its parent folder - None if there is none.
        route_dir = os.path.dirname(os.path.abspath(gpx_path))
        for folder in (route_dir, os.path.dirname(route_dir)):
            try:
                names = sorted(os.listdir(folder))
            except OSError:
                continue
            for name in names:
                if not name.lower().endswith('.xml'):
                    continue
                path = os.path.join(folder, name)
                if path not in cls._export_cache:
                    cls._export_cache[path] = cls.read_heart_rate(path)
                if cls._export_cache[path] is not None:
                    return cls._export_cache[path]
        return None

    # --- GPX parsing (private) ------------------------------------------

    @classmethod
    def _child_text(cls, elem, tag):
        child = elem.find(f'gpx:{tag}', cls.NS)
        return child.text if child is not None and child.text is not None else None

    @classmethod
    def _utc_offset_from_name(cls, name, end_time_utc):
        # The file name holds the track's end in local time, to the minute
        # (see the class docstring); its difference from the last point's
        # UTC time, rounded to 15 minutes, is the UTC offset. Returns 0 if
        # the name doesn't match, or the offset isn't a plausible one.
        match = cls.FILENAME_RE.search(os.path.basename(name or ''))
        if match is None:
            return 0
        year, month, day, hour, minute, ampm = match.groups()
        hour = int(hour) % 12 + (12 if ampm.lower() == 'pm' else 0)
        try:
            local_end = datetime(int(year), int(month), int(day), hour, int(minute), tzinfo=timezone.utc)
        except ValueError:
            return 0
        utc_end = end_time_utc.astimezone(timezone.utc).replace(second=0, microsecond=0)
        offset = round((local_end - utc_end).total_seconds() / 900) * 900
        return offset if abs(offset) <= 14 * 3600 else 0


class MergedActivities(Activities):
    """Merges several Activities instances (of any kind - FitActivity,
    ZippedActivities, TcxActivities, even another MergedActivities) into
    a single combined timeline. Public API mirrors the other three classes:
    list_activities, summarize_activity, extract_records, extract_pauses,
    extract_elevation (plus __iter__/__len__/__contains__/__getitem__, from
    the shared Activities base class). The four per-activity methods take
    one of the timestamps list_activities() returns; passing anything else
    raises KeyError.
    """

    def __init__(self, activities_list):
        """activities_list: a list of Activities instances to merge into
        one timeline - typically one per source file. Nothing is copied,
        this just indexes into the instances given.
        """
        self.activities_list = activities_list
        self._activity_index = {}  # start time (datetime) -> index into activities_list

        for index, activities in enumerate(activities_list):
            for timestamp in activities.list_activities():
                if timestamp in self._activity_index:
                    continue  # duplicate timestamp across sources: keep the first, ignore the rest
                self._activity_index[timestamp] = index

        super().__init__(sorted(self._activity_index.keys()))

    # --- per-activity access, given a timestamp -----------------------

    def summarize_activity(self, timestamp):
        return self.activities_list[self._activity_index[timestamp]].summarize_activity(timestamp)

    def extract_records(self, timestamp):
        return self.activities_list[self._activity_index[timestamp]].extract_records(timestamp)

    def extract_pauses(self, timestamp):
        return self.activities_list[self._activity_index[timestamp]].extract_pauses(timestamp)

    def extract_elevation(self, timestamp):
        return self.activities_list[self._activity_index[timestamp]].extract_elevation(timestamp)


class ZippedActivities(MergedActivities):
    """Loads every activity file in a Zip archive - any entry, in any
    subdirectory, whose extension is one of ZIPPED_EXTENSIONS (.fit, .tcx,
    .gpx, .logbook3) - and merges them all into one timeline, exactly like
    MergedActivities does for separate files. An Apple Health export XML in
    the archive provides the heart rate of its .gpx routes (see
    AppleHealthActivity.read_heart_rate); other entries are ignored.

    Nothing is extracted to disk: each entry is opened as an in-memory
    stream (zipfile.ZipFile.open()) and handed straight to the class for its
    extension, which parses it from that stream. An entry that fails to
    parse is skipped with a warning on stderr rather than aborting the
    whole archive.
    """

    def __init__(self, zip_path):
        """Load and parse every activity file in a Zip archive. Memory usage
        is not a concern - the whole archive is parsed up front.
        """
        self.zip_path = zip_path
        activities_list = []

        with zipfile.ZipFile(zip_path) as archive:
            entries = sorted((info for info in archive.infolist() if not info.is_dir()),
                             key=lambda i: i.filename)
            heart_rate = self._read_apple_heart_rate(archive, entries)
            for info in entries:
                ext = os.path.splitext(info.filename)[1].lower()
                activity_class = ZIPPED_EXTENSIONS.get(ext)
                if activity_class is None:
                    continue
                kwargs = {'heart_rate': heart_rate} if activity_class is AppleHealthActivity else {}
                try:
                    with archive.open(info) as stream:
                        activities = activity_class(stream, name=info.filename, **kwargs)
                except Exception as err:
                    print(f'warning: skipping {info.filename}: {err}', file=sys.stderr)
                    continue
                if len(activities) == 0:
                    print(f'warning: {info.filename} has no activities with a determinable start time, excluding it', file=sys.stderr)
                    continue
                activities_list.append(activities)

        super().__init__(activities_list)

    @staticmethod
    def _read_apple_heart_rate(archive, entries):
        # The heart rate readings of the first Apple Health export XML in
        # the archive (see AppleHealthActivity.read_heart_rate), for its
        # .gpx routes - None if there is none.
        for info in entries:
            if not info.filename.lower().endswith('.xml'):
                continue
            with archive.open(info) as stream:
                heart_rate = AppleHealthActivity.read_heart_rate(stream)
            if heart_rate is not None:
                return heart_rate
        return None


class ActivitiesSubset(Activities):
    """A view onto some of another Activities instance's activities, given
    by their start timestamps. Public API mirrors the other classes:
    list_activities, summarize_activity, extract_records, extract_pauses,
    extract_elevation (plus __iter__/__len__/__contains__/__getitem__, from
    the shared Activities base class). The four per-activity methods take
    one of the timestamps list_activities() returns; passing anything else
    raises KeyError. Base class for ActivitiesFilteredByLocation and
    LocationGroup.
    """

    def __init__(self, activities, timestamps):
        """activities: the Activities instance to take a subset of. Nothing
        is copied, this just indexes into it.
        timestamps: the start timestamps of the activities to include, in
        chronological order.
        """
        self.activities = activities
        self._timestamp_set = set(timestamps)
        super().__init__(timestamps)

    # --- per-activity access, given a timestamp -----------------------

    def summarize_activity(self, timestamp):
        self._check_timestamp(timestamp)
        return self.activities.summarize_activity(timestamp)

    def extract_records(self, timestamp):
        self._check_timestamp(timestamp)
        return self.activities.extract_records(timestamp)

    def extract_pauses(self, timestamp):
        self._check_timestamp(timestamp)
        return self.activities.extract_pauses(timestamp)

    def extract_elevation(self, timestamp):
        self._check_timestamp(timestamp)
        return self.activities.extract_elevation(timestamp)

    def _check_timestamp(self, timestamp):
        # The underlying instance would happily serve activities outside
        # this subset, so reject those here.
        if timestamp not in self._timestamp_set:
            raise KeyError(timestamp)


class ActivitiesFilteredByLocation(ActivitiesSubset):
    """A view onto another Activities instance, restricted to the activities
    whose start location lies within a given distance of a given point.
    Same public API as ActivitiesSubset.

    Activities with no known start location (e.g. GPS-less ones) are
    excluded, since they can't be placed relative to the given point.
    """

    def __init__(self, activities, lat, lng, distance_km):
        """activities: the Activities instance to filter. Nothing is copied,
        this just indexes into it.
        lat, lng: the center point, in degrees.
        distance_km: maximum great-circle distance, in kilometers, between
        the center point and an activity's start location for that activity
        to be included.
        """
        self.lat = lat
        self.lng = lng
        self.distance_km = distance_km

        max_distance_m = distance_km * 1000
        timestamps = []
        for timestamp in activities.list_activities():
            location = self.start_location(activities, timestamp)
            if location is None:
                continue
            if self.haversine_m(lat, lng, *location) <= max_distance_m:
                timestamps.append(timestamp)

        # activities.list_activities() is already in chronological order.
        super().__init__(activities, timestamps)


class ActivitiesFilteredByDate(ActivitiesSubset):
    """A view onto another Activities instance, restricted to the activities
    starting between two points in time, both inclusive. Same public API as
    ActivitiesSubset.

    Each bound can be a date or a datetime (or None, for no bound on that
    side). A date covers that whole calendar day, so from_time=to_time=
    date(2026, 1, 1) selects every activity starting on January 1st. Dates
    are compared against each activity's local start date. A naive datetime
    is likewise compared against an activity's local wall-clock start time,
    whereas a timezone-aware one is compared as an exact instant.
    """

    def __init__(self, activities, from_time, to_time):
        """activities: the Activities instance to filter. Nothing is copied,
        this just indexes into it.
        from_time, to_time: the earliest/latest start time to include - a
        date, a datetime, or None (unbounded).
        """
        self.from_time = from_time
        self.to_time = to_time

        timestamps = [
            timestamp for timestamp in activities.list_activities()
            if (from_time is None or self.compare_timestamp(timestamp, from_time) >= 0)
            and (to_time is None or self.compare_timestamp(timestamp, to_time) <= 0)
        ]

        # activities.list_activities() is already in chronological order.
        super().__init__(activities, timestamps)


class LocationGroup(ActivitiesSubset):
    """One group of an ActivitiesGroupedByLocation: the activities assigned
    to it, plus its center (lat, lng, in degrees) - the start location of
    the group's first activity. Same public API as ActivitiesSubset.
    """

    def __init__(self, activities, lat, lng, timestamps):
        self.lat = lat
        self.lng = lng
        super().__init__(activities, timestamps)

    def describe(self):
        """Summary of this group, e.g. for a map marker: {lat, lng} (the
        mean start location of its activities - not its center, which is
        just its first activity's start location), count, first/last
        (dates of its first/last activity, ISO 8601 strings), and sports
        (sport -> number of activities, most frequent first).
        """
        summaries = [activity.summary() for activity in self]

        # Mean of the unit vectors rather than of raw lat/lng, so a group
        # straddling the antimeridian doesn't average out to the wrong side
        # of the globe.
        x = y = z = 0.0
        for s in summaries:
            lat, lng = math.radians(s['start_lat']), math.radians(s['start_lng'])
            x += math.cos(lat) * math.cos(lng)
            y += math.cos(lat) * math.sin(lng)
            z += math.sin(lat)
        lat = math.degrees(math.atan2(z, math.hypot(x, y)))
        lng = math.degrees(math.atan2(y, x))

        # A group's activities are already in chronological order.
        times = self.list_activities()
        sports = {}
        for s in summaries:
            sports[s['sport']] = sports.get(s['sport'], 0) + 1

        return {
            'lat': lat,
            'lng': lng,
            'count': len(self),
            'first': times[0].date().isoformat(),
            'last': times[-1].date().isoformat(),
            'sports': dict(sorted(sports.items(), key=lambda kv: -kv[1])),
        }


class ActivitiesGroupedByLocation:
    """Groups another Activities instance's activities by start location.
    Activities are visited in chronological order; each joins the existing
    group whose center is nearest to its start location, provided that's
    within the given distance - otherwise it starts a new group, centered on
    its own start location. A group's center never moves once created.

    The groups are available as `groups`, a list of LocationGroup in order
    of creation (i.e. by their first activity's start time), and this
    object can also be iterated/indexed/len()'d directly as that list.

    Activities with no known start location (e.g. GPS-less ones) aren't
    assigned to any group.
    """

    def __init__(self, activities, distance_km):
        """activities: the Activities instance to group. Nothing is copied,
        the groups just index into it.
        distance_km: maximum great-circle distance, in kilometers, between
        a group's center and an activity's start location for that activity
        to join the group.
        """
        self.activities = activities
        self.distance_km = distance_km

        max_distance_m = distance_km * 1000
        groups = []  # [lat, lng, [timestamp, ...]] per group, in creation order
        for timestamp in activities.list_activities():
            location = ActivitiesSubset.start_location(activities, timestamp)
            if location is None:
                continue

            nearest, nearest_distance_m = None, None
            for group in groups:
                distance_m = Activities.haversine_m(group[0], group[1], *location)
                if distance_m <= max_distance_m and (nearest is None or distance_m < nearest_distance_m):
                    nearest, nearest_distance_m = group, distance_m

            if nearest is not None:
                nearest[2].append(timestamp)
            else:
                groups.append([location[0], location[1], [timestamp]])

        # Timestamps were visited in chronological order, so each group's
        # list already is too.
        self.groups = [LocationGroup(activities, lat, lng, timestamps) for lat, lng, timestamps in groups]

    def __iter__(self):
        return iter(self.groups)

    def __len__(self):
        return len(self.groups)

    def __getitem__(self, index):
        return self.groups[index]

    def find_by_location(self, lat, lng):
        """The LocationGroup whose center lies within self.distance_km
        (great-circle distance) of lat/lng (degrees) - the nearest one if
        several do, i.e. the group an activity starting there would join.
        None if no group is within range.
        """
        max_distance_m = self.distance_km * 1000
        nearest, nearest_distance_m = None, None
        for group in self.groups:
            distance_m = Activities.haversine_m(group.lat, group.lng, lat, lng)
            if distance_m <= max_distance_m and (nearest is None or distance_m < nearest_distance_m):
                nearest, nearest_distance_m = group, distance_m
        return nearest


EXTENSIONS = {
    '.fit': FitActivity,
    '.zip': ZippedActivities,
    '.tcx': TcxActivities,
    '.logbook3': Logbook3Activities,
    '.gpx': AppleHealthActivity,
}

# The formats ZippedActivities loads from inside an archive - every class
# here takes (stream, name=...) - i.e. everything but a nested .zip.
ZIPPED_EXTENSIONS = {ext: cls for ext, cls in EXTENSIONS.items() if cls is not ZippedActivities}


def open_activities(path):
    """Return an instance of whichever Activities class matches path's
    extension (see EXTENSIONS: .fit / .zip / .tcx / .logbook3 / .gpx) - or, if
    path is a list of two or more paths, a MergedActivities combining all
    of their activities into a single timeline. A list of exactly one path
    is treated the same as passing that path directly.
    Raises ValueError for an unrecognized extension.
    """
    if isinstance(path, (list, tuple)):
        if len(path) == 1:
            return open_activities(path[0])
        return MergedActivities([open_activities(p) for p in path])

    ext = os.path.splitext(path)[1].lower()
    activity_class = EXTENSIONS.get(ext)
    if activity_class is None:
        expected = ', '.join(sorted(EXTENSIONS))
        raise ValueError(f'Unsupported file type "{ext}" for {path} (expected one of: {expected})')
    return activity_class(path)
