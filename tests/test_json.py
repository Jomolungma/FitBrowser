import io
import json
from .dummyactivities import *
from .fittesthelpers import *

def checkJson(rg, url):
    out = io.BytesIO()
    assert rg.hasFile(url)
    rg.copyFile(url, out)
    json.loads(out.getvalue())

def test_ActivitiesOverview():
    rg = makeTestResourceGenerator()
    checkJson(rg, "/index.json")

def test_ActivityRecords():
    rg = makeTestResourceGenerator()
    count = 0
    for activity in rg.activities:
        count = count + 1
        checkJson(rg, f"/activity/{activity.time().isoformat()}.json")
    assert count > 0
