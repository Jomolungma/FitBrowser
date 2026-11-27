"""Synthetic, fully hardcoded activities for unit tests:

- the 2026 Boston Marathon (Monday, April 20, 2026, 10:00 EDT start), from
  the start line on Main Street in Hopkinton to the finish line on Boylston
  Street in Boston, in 3:04:07;
- the 2026 Loch Ness Marathon (Sunday, September 27, 2026, 10:00 BST start),
  from the start on the B862 near Whitebridge, south of Loch Ness, to the
  finish in Bught Park, Inverness, in 2:56:57.

Each covers 42.195 km, with one record at every full kilometer plus one at
the finish line. Only the start and finish locations are real (the Loch
Ness start only approximately); every record in between - location, time,
elevation - is linearly interpolated between them, so each course runs in a
straight line and descends at a constant grade. No record has a heart rate.
"""

from datetime import datetime, timedelta, timezone

from fitbrowser.fitact import Activities


class DummyActivities(Activities):
    """An Activities container holding the two activities above, in
    chronological order. Implements the same public API as FitActivity/
    TcxActivities: summarize_activity, extract_records, extract_pauses,
    extract_elevation.
    """

    BOSTON_START = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
    LOCH_NESS_START = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone(timedelta(hours=1)))

    SUMMARIES = {
        BOSTON_START: {
            'id': 'Boston Marathon 2026',
            'timestamp': BOSTON_START,
            'sport': 'running',
            'distance_m': 42195.0,
            'duration_s': 11047.0,  # 3:04:07
            'start_lat': 42.229838,
            'start_lng': -71.519356,
            'ascent': 0.0,
            'descent': 138.0,
        },
        LOCH_NESS_START: {
            'id': 'Loch Ness Marathon 2026',
            'timestamp': LOCH_NESS_START,
            'sport': 'running',
            'distance_m': 42195.0,
            'duration_s': 10617.0,  # 2:56:57
            'start_lat': 57.177500,
            'start_lng': -4.582200,
            'ascent': 0.0,
            'descent': 303.0,
        },
    }

    RECORDS = {
        BOSTON_START: [
            {'lat': 42.229838, 'lng': -71.519356, 'time': '2026-04-20T10:00:00-04:00', 'ele': 141.0, 'heart_rate': None, 'distance_m': 0.0, 'duration_s': 0.0},
            {'lat': 42.232684, 'lng': -71.508900, 'time': '2026-04-20T10:04:22-04:00', 'ele': 137.7, 'heart_rate': None, 'distance_m': 1000.0, 'duration_s': 262.0},
            {'lat': 42.235529, 'lng': -71.498445, 'time': '2026-04-20T10:08:44-04:00', 'ele': 134.5, 'heart_rate': None, 'distance_m': 2000.0, 'duration_s': 524.0},
            {'lat': 42.238375, 'lng': -71.487989, 'time': '2026-04-20T10:13:05-04:00', 'ele': 131.2, 'heart_rate': None, 'distance_m': 3000.0, 'duration_s': 785.0},
            {'lat': 42.241220, 'lng': -71.477533, 'time': '2026-04-20T10:17:27-04:00', 'ele': 127.9, 'heart_rate': None, 'distance_m': 4000.0, 'duration_s': 1047.0},
            {'lat': 42.244066, 'lng': -71.467077, 'time': '2026-04-20T10:21:49-04:00', 'ele': 124.6, 'heart_rate': None, 'distance_m': 5000.0, 'duration_s': 1309.0},
            {'lat': 42.246912, 'lng': -71.456622, 'time': '2026-04-20T10:26:11-04:00', 'ele': 121.4, 'heart_rate': None, 'distance_m': 6000.0, 'duration_s': 1571.0},
            {'lat': 42.249757, 'lng': -71.446166, 'time': '2026-04-20T10:30:33-04:00', 'ele': 118.1, 'heart_rate': None, 'distance_m': 7000.0, 'duration_s': 1833.0},
            {'lat': 42.252603, 'lng': -71.435710, 'time': '2026-04-20T10:34:54-04:00', 'ele': 114.8, 'heart_rate': None, 'distance_m': 8000.0, 'duration_s': 2094.0},
            {'lat': 42.255449, 'lng': -71.425254, 'time': '2026-04-20T10:39:16-04:00', 'ele': 111.6, 'heart_rate': None, 'distance_m': 9000.0, 'duration_s': 2356.0},
            {'lat': 42.258294, 'lng': -71.414799, 'time': '2026-04-20T10:43:38-04:00', 'ele': 108.3, 'heart_rate': None, 'distance_m': 10000.0, 'duration_s': 2618.0},
            {'lat': 42.261140, 'lng': -71.404343, 'time': '2026-04-20T10:48:00-04:00', 'ele': 105.0, 'heart_rate': None, 'distance_m': 11000.0, 'duration_s': 2880.0},
            {'lat': 42.263985, 'lng': -71.393887, 'time': '2026-04-20T10:52:22-04:00', 'ele': 101.8, 'heart_rate': None, 'distance_m': 12000.0, 'duration_s': 3142.0},
            {'lat': 42.266831, 'lng': -71.383431, 'time': '2026-04-20T10:56:44-04:00', 'ele': 98.5, 'heart_rate': None, 'distance_m': 13000.0, 'duration_s': 3404.0},
            {'lat': 42.269677, 'lng': -71.372976, 'time': '2026-04-20T11:01:05-04:00', 'ele': 95.2, 'heart_rate': None, 'distance_m': 14000.0, 'duration_s': 3665.0},
            {'lat': 42.272522, 'lng': -71.362520, 'time': '2026-04-20T11:05:27-04:00', 'ele': 91.9, 'heart_rate': None, 'distance_m': 15000.0, 'duration_s': 3927.0},
            {'lat': 42.275368, 'lng': -71.352064, 'time': '2026-04-20T11:09:49-04:00', 'ele': 88.7, 'heart_rate': None, 'distance_m': 16000.0, 'duration_s': 4189.0},
            {'lat': 42.278214, 'lng': -71.341608, 'time': '2026-04-20T11:14:11-04:00', 'ele': 85.4, 'heart_rate': None, 'distance_m': 17000.0, 'duration_s': 4451.0},
            {'lat': 42.281059, 'lng': -71.331153, 'time': '2026-04-20T11:18:33-04:00', 'ele': 82.1, 'heart_rate': None, 'distance_m': 18000.0, 'duration_s': 4713.0},
            {'lat': 42.283905, 'lng': -71.320697, 'time': '2026-04-20T11:22:54-04:00', 'ele': 78.9, 'heart_rate': None, 'distance_m': 19000.0, 'duration_s': 4974.0},
            {'lat': 42.286750, 'lng': -71.310241, 'time': '2026-04-20T11:27:16-04:00', 'ele': 75.6, 'heart_rate': None, 'distance_m': 20000.0, 'duration_s': 5236.0},
            {'lat': 42.289596, 'lng': -71.299785, 'time': '2026-04-20T11:31:38-04:00', 'ele': 72.3, 'heart_rate': None, 'distance_m': 21000.0, 'duration_s': 5498.0},
            {'lat': 42.292442, 'lng': -71.289330, 'time': '2026-04-20T11:36:00-04:00', 'ele': 69.0, 'heart_rate': None, 'distance_m': 22000.0, 'duration_s': 5760.0},
            {'lat': 42.295287, 'lng': -71.278874, 'time': '2026-04-20T11:40:22-04:00', 'ele': 65.8, 'heart_rate': None, 'distance_m': 23000.0, 'duration_s': 6022.0},
            {'lat': 42.298133, 'lng': -71.268418, 'time': '2026-04-20T11:44:43-04:00', 'ele': 62.5, 'heart_rate': None, 'distance_m': 24000.0, 'duration_s': 6283.0},
            {'lat': 42.300979, 'lng': -71.257962, 'time': '2026-04-20T11:49:05-04:00', 'ele': 59.2, 'heart_rate': None, 'distance_m': 25000.0, 'duration_s': 6545.0},
            {'lat': 42.303824, 'lng': -71.247507, 'time': '2026-04-20T11:53:27-04:00', 'ele': 56.0, 'heart_rate': None, 'distance_m': 26000.0, 'duration_s': 6807.0},
            {'lat': 42.306670, 'lng': -71.237051, 'time': '2026-04-20T11:57:49-04:00', 'ele': 52.7, 'heart_rate': None, 'distance_m': 27000.0, 'duration_s': 7069.0},
            {'lat': 42.309515, 'lng': -71.226595, 'time': '2026-04-20T12:02:11-04:00', 'ele': 49.4, 'heart_rate': None, 'distance_m': 28000.0, 'duration_s': 7331.0},
            {'lat': 42.312361, 'lng': -71.216140, 'time': '2026-04-20T12:06:32-04:00', 'ele': 46.2, 'heart_rate': None, 'distance_m': 29000.0, 'duration_s': 7592.0},
            {'lat': 42.315207, 'lng': -71.205684, 'time': '2026-04-20T12:10:54-04:00', 'ele': 42.9, 'heart_rate': None, 'distance_m': 30000.0, 'duration_s': 7854.0},
            {'lat': 42.318052, 'lng': -71.195228, 'time': '2026-04-20T12:15:16-04:00', 'ele': 39.6, 'heart_rate': None, 'distance_m': 31000.0, 'duration_s': 8116.0},
            {'lat': 42.320898, 'lng': -71.184772, 'time': '2026-04-20T12:19:38-04:00', 'ele': 36.3, 'heart_rate': None, 'distance_m': 32000.0, 'duration_s': 8378.0},
            {'lat': 42.323744, 'lng': -71.174317, 'time': '2026-04-20T12:24:00-04:00', 'ele': 33.1, 'heart_rate': None, 'distance_m': 33000.0, 'duration_s': 8640.0},
            {'lat': 42.326589, 'lng': -71.163861, 'time': '2026-04-20T12:28:21-04:00', 'ele': 29.8, 'heart_rate': None, 'distance_m': 34000.0, 'duration_s': 8901.0},
            {'lat': 42.329435, 'lng': -71.153405, 'time': '2026-04-20T12:32:43-04:00', 'ele': 26.5, 'heart_rate': None, 'distance_m': 35000.0, 'duration_s': 9163.0},
            {'lat': 42.332280, 'lng': -71.142949, 'time': '2026-04-20T12:37:05-04:00', 'ele': 23.3, 'heart_rate': None, 'distance_m': 36000.0, 'duration_s': 9425.0},
            {'lat': 42.335126, 'lng': -71.132494, 'time': '2026-04-20T12:41:27-04:00', 'ele': 20.0, 'heart_rate': None, 'distance_m': 37000.0, 'duration_s': 9687.0},
            {'lat': 42.337972, 'lng': -71.122038, 'time': '2026-04-20T12:45:49-04:00', 'ele': 16.7, 'heart_rate': None, 'distance_m': 38000.0, 'duration_s': 9949.0},
            {'lat': 42.340817, 'lng': -71.111582, 'time': '2026-04-20T12:50:11-04:00', 'ele': 13.4, 'heart_rate': None, 'distance_m': 39000.0, 'duration_s': 10211.0},
            {'lat': 42.343663, 'lng': -71.101126, 'time': '2026-04-20T12:54:32-04:00', 'ele': 10.2, 'heart_rate': None, 'distance_m': 40000.0, 'duration_s': 10472.0},
            {'lat': 42.346508, 'lng': -71.090671, 'time': '2026-04-20T12:58:54-04:00', 'ele': 6.9, 'heart_rate': None, 'distance_m': 41000.0, 'duration_s': 10734.0},
            {'lat': 42.349354, 'lng': -71.080215, 'time': '2026-04-20T13:03:16-04:00', 'ele': 3.6, 'heart_rate': None, 'distance_m': 42000.0, 'duration_s': 10996.0},
            {'lat': 42.349909, 'lng': -71.078176, 'time': '2026-04-20T13:04:07-04:00', 'ele': 3.0, 'heart_rate': None, 'distance_m': 42195.0, 'duration_s': 11047.0},
        ],
        LOCH_NESS_START: [
            {'lat': 57.177500, 'lng': -4.582200, 'time': '2026-09-27T10:00:00+01:00', 'ele': 311.0, 'heart_rate': None, 'distance_m': 0.0, 'duration_s': 0.0},
            {'lat': 57.184425, 'lng': -4.574043, 'time': '2026-09-27T10:04:12+01:00', 'ele': 303.8, 'heart_rate': None, 'distance_m': 1000.0, 'duration_s': 252.0},
            {'lat': 57.191350, 'lng': -4.565885, 'time': '2026-09-27T10:08:24+01:00', 'ele': 296.6, 'heart_rate': None, 'distance_m': 2000.0, 'duration_s': 504.0},
            {'lat': 57.198275, 'lng': -4.557728, 'time': '2026-09-27T10:12:36+01:00', 'ele': 289.5, 'heart_rate': None, 'distance_m': 3000.0, 'duration_s': 756.0},
            {'lat': 57.205200, 'lng': -4.549571, 'time': '2026-09-27T10:16:47+01:00', 'ele': 282.3, 'heart_rate': None, 'distance_m': 4000.0, 'duration_s': 1007.0},
            {'lat': 57.212125, 'lng': -4.541413, 'time': '2026-09-27T10:20:59+01:00', 'ele': 275.1, 'heart_rate': None, 'distance_m': 5000.0, 'duration_s': 1259.0},
            {'lat': 57.219050, 'lng': -4.533256, 'time': '2026-09-27T10:25:11+01:00', 'ele': 267.9, 'heart_rate': None, 'distance_m': 6000.0, 'duration_s': 1511.0},
            {'lat': 57.225975, 'lng': -4.525098, 'time': '2026-09-27T10:29:23+01:00', 'ele': 260.7, 'heart_rate': None, 'distance_m': 7000.0, 'duration_s': 1763.0},
            {'lat': 57.232900, 'lng': -4.516941, 'time': '2026-09-27T10:33:35+01:00', 'ele': 253.6, 'heart_rate': None, 'distance_m': 8000.0, 'duration_s': 2015.0},
            {'lat': 57.239825, 'lng': -4.508784, 'time': '2026-09-27T10:37:47+01:00', 'ele': 246.4, 'heart_rate': None, 'distance_m': 9000.0, 'duration_s': 2267.0},
            {'lat': 57.246750, 'lng': -4.500626, 'time': '2026-09-27T10:41:59+01:00', 'ele': 239.2, 'heart_rate': None, 'distance_m': 10000.0, 'duration_s': 2519.0},
            {'lat': 57.253675, 'lng': -4.492469, 'time': '2026-09-27T10:46:10+01:00', 'ele': 232.0, 'heart_rate': None, 'distance_m': 11000.0, 'duration_s': 2770.0},
            {'lat': 57.260600, 'lng': -4.484312, 'time': '2026-09-27T10:50:22+01:00', 'ele': 224.8, 'heart_rate': None, 'distance_m': 12000.0, 'duration_s': 3022.0},
            {'lat': 57.267525, 'lng': -4.476154, 'time': '2026-09-27T10:54:34+01:00', 'ele': 217.6, 'heart_rate': None, 'distance_m': 13000.0, 'duration_s': 3274.0},
            {'lat': 57.274450, 'lng': -4.467997, 'time': '2026-09-27T10:58:46+01:00', 'ele': 210.5, 'heart_rate': None, 'distance_m': 14000.0, 'duration_s': 3526.0},
            {'lat': 57.281375, 'lng': -4.459840, 'time': '2026-09-27T11:02:58+01:00', 'ele': 203.3, 'heart_rate': None, 'distance_m': 15000.0, 'duration_s': 3778.0},
            {'lat': 57.288300, 'lng': -4.451682, 'time': '2026-09-27T11:07:10+01:00', 'ele': 196.1, 'heart_rate': None, 'distance_m': 16000.0, 'duration_s': 4030.0},
            {'lat': 57.295225, 'lng': -4.443525, 'time': '2026-09-27T11:11:22+01:00', 'ele': 188.9, 'heart_rate': None, 'distance_m': 17000.0, 'duration_s': 4282.0},
            {'lat': 57.302150, 'lng': -4.435367, 'time': '2026-09-27T11:15:33+01:00', 'ele': 181.7, 'heart_rate': None, 'distance_m': 18000.0, 'duration_s': 4533.0},
            {'lat': 57.309075, 'lng': -4.427210, 'time': '2026-09-27T11:19:45+01:00', 'ele': 174.6, 'heart_rate': None, 'distance_m': 19000.0, 'duration_s': 4785.0},
            {'lat': 57.316000, 'lng': -4.419053, 'time': '2026-09-27T11:23:57+01:00', 'ele': 167.4, 'heart_rate': None, 'distance_m': 20000.0, 'duration_s': 5037.0},
            {'lat': 57.322925, 'lng': -4.410895, 'time': '2026-09-27T11:28:09+01:00', 'ele': 160.2, 'heart_rate': None, 'distance_m': 21000.0, 'duration_s': 5289.0},
            {'lat': 57.329850, 'lng': -4.402738, 'time': '2026-09-27T11:32:21+01:00', 'ele': 153.0, 'heart_rate': None, 'distance_m': 22000.0, 'duration_s': 5541.0},
            {'lat': 57.336775, 'lng': -4.394581, 'time': '2026-09-27T11:36:33+01:00', 'ele': 145.8, 'heart_rate': None, 'distance_m': 23000.0, 'duration_s': 5793.0},
            {'lat': 57.343700, 'lng': -4.386423, 'time': '2026-09-27T11:40:45+01:00', 'ele': 138.7, 'heart_rate': None, 'distance_m': 24000.0, 'duration_s': 6045.0},
            {'lat': 57.350625, 'lng': -4.378266, 'time': '2026-09-27T11:44:56+01:00', 'ele': 131.5, 'heart_rate': None, 'distance_m': 25000.0, 'duration_s': 6296.0},
            {'lat': 57.357550, 'lng': -4.370109, 'time': '2026-09-27T11:49:08+01:00', 'ele': 124.3, 'heart_rate': None, 'distance_m': 26000.0, 'duration_s': 6548.0},
            {'lat': 57.364475, 'lng': -4.361951, 'time': '2026-09-27T11:53:20+01:00', 'ele': 117.1, 'heart_rate': None, 'distance_m': 27000.0, 'duration_s': 6800.0},
            {'lat': 57.371400, 'lng': -4.353794, 'time': '2026-09-27T11:57:32+01:00', 'ele': 109.9, 'heart_rate': None, 'distance_m': 28000.0, 'duration_s': 7052.0},
            {'lat': 57.378325, 'lng': -4.345636, 'time': '2026-09-27T12:01:44+01:00', 'ele': 102.8, 'heart_rate': None, 'distance_m': 29000.0, 'duration_s': 7304.0},
            {'lat': 57.385250, 'lng': -4.337479, 'time': '2026-09-27T12:05:56+01:00', 'ele': 95.6, 'heart_rate': None, 'distance_m': 30000.0, 'duration_s': 7556.0},
            {'lat': 57.392175, 'lng': -4.329322, 'time': '2026-09-27T12:10:07+01:00', 'ele': 88.4, 'heart_rate': None, 'distance_m': 31000.0, 'duration_s': 7807.0},
            {'lat': 57.399100, 'lng': -4.321164, 'time': '2026-09-27T12:14:19+01:00', 'ele': 81.2, 'heart_rate': None, 'distance_m': 32000.0, 'duration_s': 8059.0},
            {'lat': 57.406025, 'lng': -4.313007, 'time': '2026-09-27T12:18:31+01:00', 'ele': 74.0, 'heart_rate': None, 'distance_m': 33000.0, 'duration_s': 8311.0},
            {'lat': 57.412950, 'lng': -4.304850, 'time': '2026-09-27T12:22:43+01:00', 'ele': 66.8, 'heart_rate': None, 'distance_m': 34000.0, 'duration_s': 8563.0},
            {'lat': 57.419875, 'lng': -4.296692, 'time': '2026-09-27T12:26:55+01:00', 'ele': 59.7, 'heart_rate': None, 'distance_m': 35000.0, 'duration_s': 8815.0},
            {'lat': 57.426800, 'lng': -4.288535, 'time': '2026-09-27T12:31:07+01:00', 'ele': 52.5, 'heart_rate': None, 'distance_m': 36000.0, 'duration_s': 9067.0},
            {'lat': 57.433725, 'lng': -4.280378, 'time': '2026-09-27T12:35:19+01:00', 'ele': 45.3, 'heart_rate': None, 'distance_m': 37000.0, 'duration_s': 9319.0},
            {'lat': 57.440650, 'lng': -4.272220, 'time': '2026-09-27T12:39:30+01:00', 'ele': 38.1, 'heart_rate': None, 'distance_m': 38000.0, 'duration_s': 9570.0},
            {'lat': 57.447575, 'lng': -4.264063, 'time': '2026-09-27T12:43:42+01:00', 'ele': 30.9, 'heart_rate': None, 'distance_m': 39000.0, 'duration_s': 9822.0},
            {'lat': 57.454500, 'lng': -4.255905, 'time': '2026-09-27T12:47:54+01:00', 'ele': 23.8, 'heart_rate': None, 'distance_m': 40000.0, 'duration_s': 10074.0},
            {'lat': 57.461425, 'lng': -4.247748, 'time': '2026-09-27T12:52:06+01:00', 'ele': 16.6, 'heart_rate': None, 'distance_m': 41000.0, 'duration_s': 10326.0},
            {'lat': 57.468350, 'lng': -4.239591, 'time': '2026-09-27T12:56:18+01:00', 'ele': 9.4, 'heart_rate': None, 'distance_m': 42000.0, 'duration_s': 10578.0},
            {'lat': 57.469700, 'lng': -4.238000, 'time': '2026-09-27T12:57:07+01:00', 'ele': 8.0, 'heart_rate': None, 'distance_m': 42195.0, 'duration_s': 10617.0},
        ],
    }

    def __init__(self):
        super().__init__([self.BOSTON_START, self.LOCH_NESS_START])

    def summarize_activity(self, timestamp):
        self._check_timestamp(timestamp)
        return dict(self.SUMMARIES[timestamp])

    def extract_records(self, timestamp):
        self._check_timestamp(timestamp)
        return [dict(record) for record in self.RECORDS[timestamp]]

    def extract_pauses(self, timestamp):
        self._check_timestamp(timestamp)
        return []

    def extract_elevation(self, timestamp):
        self._check_timestamp(timestamp)
        summary = self.SUMMARIES[timestamp]
        return {'ascent': summary['ascent'], 'descent': summary['descent']}

    def _check_timestamp(self, timestamp):
        if timestamp not in self.SUMMARIES:
            available = ', '.join(t.isoformat() for t in self.list_activities())
            raise ValueError(f'No activity starts at {timestamp.isoformat()}. Available: {available}')
