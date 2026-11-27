import io
import html5lib
from .dummyactivities import *
from .fittesthelpers import *

def checkHtmlPage(rg, url):
    out = io.BytesIO()
    assert rg.hasFile(url)
    rg.copyFile(url, out)
    hp = html5lib.HTMLParser(strict=True)
    hp.parse(out)

def test_ActivitiesOverview():
    rg = makeTestResourceGenerator()
    checkHtmlPage(rg, "/index.html")

def test_AnnualPages():
    rg = makeTestResourceGenerator()
    count = 0
    year = rg.activities.calendar.getFirstYear()
    while year is not None:
        count = count + 1
        checkHtmlPage(rg, f"/{year:4d}.html")
        year = rg.activities.calendar.getNextYear(year)
    assert count > 0

def test_LocationPages():
    rg = makeTestResourceGenerator()
    count = 0
    for group in rg.groupedActivities:
        count = count + 1
        checkHtmlPage(rg, f"/location/{group.lat:.5f},{group.lng:.5f}.html")
    assert count > 0

def test_ActivityPages():
    rg = makeTestResourceGenerator()
    count = 0
    for activity in rg.activities:
        count = count + 1
        checkHtmlPage(rg, f"/activity/{activity.time().isoformat()}.html")
    assert count > 0
