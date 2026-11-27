from fitbrowser import fitact
from fitbrowser import fitconfig
from fitbrowser import fithtml
from .dummyactivities import *

def makeTestResourceGenerator():
    fc = fitconfig.FitConfig(False)
    activities = DummyActivities()
    groupedActivities = fitact.ActivitiesGroupedByLocation(activities, fc["groupRadiusKm"])
    rg = fithtml.ResourceGenerator(activities, groupedActivities, fc, None)
    assert len(activities) == 2
    assert len(groupedActivities) == 2
    return rg
