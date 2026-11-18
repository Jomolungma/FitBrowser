#!python

#
#    Fit Browser
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""
The classes here integrate the handling of activity files, HTML formatting
and HTTP serving -- everything except the user interface.
"""

import sys
import json
import glob
import pkgutil
import argparse
import datetime
import urllib.parse
from pathlib import Path
from os import path

if __package__ == "fitbrowser":
    from . import activity
    from . import fithttp
    from . import fitconfig
    from . import fitgeo
    from . import fithtml
else:
    import activity
    import fithttp
    import fitconfig
    import fitgeo
    import fithtml

class QuietDownloadStatistics:
    """
    Statistics collector that does not do anything, i.e., it is quiet.
    """

    def start(self, fileName):
        return self

    def oops(self, message):
        pass

    def update(self, bytesServed):
        pass

    def finish(self, success):
        pass

class ConsoleDownloadStatisticsHelper:
    """
    Statistics collector that prints information to the console.
    """

    def __init__(self, fileName):
        self.fileName = fileName

    def update(self, bytesServed):
        pass

    def finish(self, success):
        successOrFailure = "finished" if success else "failed"
        print("Download of \"" + self.fileName + "\" " + successOrFailure + ".")

class ConsoleDownloadStatistics:
    """
    Statistics collector that prints information to the console.
    """

    def start(self, fileName):
        print("Starting download of \"" + fileName + "\".")
        return ConsoleDownloadStatisticsHelper(fileName)

    def oops(self, message):
        print(message)

class ActivitiesWrapper:
    fileList = [
        "activity.js",
        "overview.js"
    ]

    def __init__(self, activities, groupedActivities, config, geoLocator):
        self.config = config
        self.activities = activities
        self.groupedActivities = groupedActivities
        self.htmlFormatter = fithtml.FitHtmlFormatter(self.config["html"], activities, groupedActivities, geoLocator, self.config["groupRadiusKm"])
        self.files = dict()
        for fileName in ActivitiesWrapper.fileList:
            self.loadFile(fileName)

    def loadFile(self, fileName):
        if "fitbrowser" in sys.modules:
            self.files[fileName] = pkgutil.get_data("fitbrowser", fileName)
        else:
            filePath = path.abspath(path.join(path.dirname(__file__), fileName))
            with open(filePath, "rb") as fileFile:
                self.files[fileName] = fileFile.read()

    def getTimestampFromName(self, name):
        if ((len(name) >= 2) and (name[0] == "/")):
            name = name[1:]
        if name.startswith("activity/"):
            name = name[9:]
        lastDot = name.rfind(".")
        if lastDot == -1:
            return None
        ext = name[lastDot+1:]
        try:
            return self.activities.parse_timestamp(name[:lastDot])
        except:
            return None

    def copyActivityJson(self, timestamp, outputFile):
        activity = self.activities[timestamp]

        summary = activity.summary()
        records = activity.records()
        pauses = activity.pauses()

        data = {
            'sport': summary['sport'],
            'records': records,
            'pauses': pauses,
            'elevation': {'ascent': summary['ascent'], 'descent': summary['descent']},
        }

        binData = json.dumps(data, indent=2).encode("utf-8")
        outputFile.write(binData)

    def hasFile(self, name):
        if ((len(name) >= 2) and (name[0] == "/")):
            name = name[1:]
        if name in self.files:
            return True
        elif self.htmlFormatter.hasFile(name):
            return True
        elif name.endswith("gmapikey.json"):
            return True
        elif name.endswith("index.json"):
            return True
        elif name.startswith("activity/"):
            timestamp = self.getTimestampFromName(name)
            if timestamp is None:
                return False
            haveTimestamp = timestamp in self.activities
            isHtml = name.endswith(".html")
            isJson = name.endswith(".json")
            return haveTimestamp and (isHtml or isJson)
        else:
            return False

    def makeGmApiKeyJson(self, outputFile):
        data = '{ "key": "' + self.config["googleMaps"]["apiKey"] + '" }'
        outputFile.write(data.encode())

    def makeActivityMarkersJson(self, outputFile):
        markers = []
        for group in self.groupedActivities:
            marker = group.describe()
            marker["url"] = f'/location/{group.lat:.5f},{group.lng:.5f}.html'
            markers.append(marker)
        binData = json.dumps(markers, indent=2).encode("utf-8")
        outputFile.write(binData)

    def copyFile(self, name, outputFile, updatecb=None):
        if ((len(name) >= 2) and (name[0] == "/")):
            name = name[1:]
        if name in self.files:
            outputFile.write(self.files[name])
        elif self.htmlFormatter.hasFile(name):
            self.htmlFormatter.copyFile(name, outputFile)
        elif name.endswith("gmapikey.json"):
            self.makeGmApiKeyJson(outputFile)
        elif name.endswith("index.json"):
            self.makeActivityMarkersJson(outputFile)
        elif name.startswith("activity/"):
            timestamp = self.getTimestampFromName(name)
            isHtml = name.endswith(".html")
            isJson = name.endswith(".json")

            if isHtml:
                self.copyActivityHtml(timestamp, outputFile)
            else:
                self.copyActivityJson(timestamp, outputFile)

class HttpHtmlGlue:
    """
    This class is the glue between the message container, which stores messages,
    the HTML formatter, which is responsible for the conversion of messages to
    HTML, and the HTTP request handler, wich serves requests from the HTTP server.
    """

    def __init__(self, activitiesWrapper):
        self.activitiesWrapper = activitiesWrapper
        self.statisticsCollector = QuietDownloadStatistics()

    def setStatisticsCollector(self, collector):
        self.statisticsCollector = collector

    def getHttpHeaders(self, path):
        path = urllib.parse.unquote(path)
        if path == "/":
            return 301, {"Location": "index.html"}

        if not self.hasFile(path):
            self.statisticsCollector.oops("Requested file \"" + path + "\" is not available.")
            return 404, None

        contentType = self.getContentTypeFromFileName(path)
        return 200, {"Content-Type": contentType}

    def getFile(self, path, wfile):
        path = urllib.parse.unquote(path)
        updatecb = self.statisticsCollector.start(path)
        try:
            if self.activitiesWrapper.hasFile(path):
                self.activitiesWrapper.copyFile(path, wfile, updatecb)
            else:
                updatecb.finish(False)
                raise Exception("Oops: \"" + path + "\".")
            updatecb.finish(True)
        except ConnectionAbortedError:
            updatecb.finish(False)
        except ConnectionResetError:
            updatecb.finish(False)

    def hasFile(self, path):
        if self.activitiesWrapper.hasFile(path):
            return True
        return False

    extToContentTypeMap = {
        "html": "text/html; charset=utf-8",
        "css":  "text/css; charset=utf-8",
        "js":   "text/javascript; charset=utf-8",
        "jpeg": "image/jpeg",
        "jpg":  "image/jpeg",
        "png":  "image/png",
        "webp": "image/webp",
        "svg":  "image/svg+xml",
        "ogg":  "audio/ogg",
        "opus": "audio/ogg",
        "mp3":  "audio/mpeg",
        "m4a":  "audio/mp4",
        "mp4":  "video/mp4",
        "mov":  "video/quicktime",
        "pdf":  "application/pdf",
        "json": "application/json"
    }

    def getContentTypeFromFileName(self, fileName):
        lastDot = fileName.rfind(".")
        if lastDot == -1:
            return None
        ext = fileName[lastDot+1:]
        if ext in HttpHtmlGlue.extToContentTypeMap:
            return HttpHtmlGlue.extToContentTypeMap[ext]
        return "application/octet-stream"

class App:
    """
    This class does everything but the UI, i.e., it is the model in MVC terms.
    """

    def __init__(self, useConfigFile=True, configFile=None):
        self.running = False
        self.unfilteredActivities = None
        self.filteredActivities = None
        self.groupedActtivities = None
        self.httpHtmlGlue = None
        self.httpServerManager = None
        self.httpBackend = None
        self.statisticsCollector = None
        self.activitiesWrapper = None
        self.title = None
        self.config = fitconfig.FitConfig(useConfigFile, configFile)
        self.geoLocator = fitgeo.NearestCity(self.config)

    def __del__(self):
        self.stop()

    @property
    def url(self):
        return self.httpServerManager.url

    @property
    def activities(self):
        return self.filteredActivities if self.filteredActivities else self.unfilteredActivities

    def setStatisticsCollector(self, collector):
        self.statisticsCollector = collector

    def configure(self, configData):
        self.config.load()
        self.config.merge(configData)
        self.geoLocator = fitgeo.NearestCity(self.config)

    def updateConfiguration(self):
        self.geoLocator = fitgeo.NearestCity(self.config)
        self.config.save()

    def open(self, files):
        self.stop()
        self.filteredActivities = None
        self.unfilteredActivities = activity.open_activities(files)
        self.groupedActivities = activity.ActivitiesGroupedByLocation(self.activities, self.config["groupRadiusKm"])

    def close(self):
        self.stop()
        self.filteredActivities = None
        self.unfilteredActivities = None
        self.groupedActivities = None

    def filterByDateRange(self, fromDate, toDate):
        if not fromDate and not toDate:
            self.resetFilter()
        self.filteredActivities = activity.ActivitiesFilteredByDate(self.activities, fromDate, toDate)
        self.groupedActivities = activity.ActivitiesGroupedByLocation(self.activities, self.config["groupRadiusKm"])

    def currentDateRangeFilter(self):
        if not self.filteredActivities:
            return None, None
        return self.filteredActivities.from_time, self.filteredActivities.to_time

    def resetFilter(self):
        self.filteredActivities = None
        self.groupedActivities = activity.ActivitiesGroupedByLocation(self.activities, self.config["groupRadiusKm"])

    def startHttpServer(self):
        if self.httpServerManager:
            return
        self.activitiesWrapper = ActivitiesWrapper(self.activities, self.groupedActivities, self.config, self.geoLocator)
        self.httpBackend = HttpHtmlGlue(self.activitiesWrapper)
        if self.statisticsCollector:
            self.httpBackend.setStatisticsCollector(self.statisticsCollector)
        self.httpServerManager = fithttp.FitHttpServerManager(self.httpBackend)
        self.httpServerManager.configure(self.config["http"])
        self.httpServerManager.start()

    def start(self):
        if not self.activities:
            return
        self.running = True
        self.startHttpServer()

    def stop(self):
        if self.httpServerManager:
            self.httpServerManager.stop()
            self.httpServerManager = None
        self.running = False
        self.updateConfiguration()

#
# Allow to run from the command line.
#

def run(activityFiles=None, title=None, useConfigFile=True, configFile=None, verbosity=0):
    # pylint: disable=import-outside-toplevel
    import time
    if activityFiles is None or len(activityFiles) == 0:
        raise Exception("No activity files provided.")
    app = App(useConfigFile, configFile)
    if verbosity > 0:
        app.setStatisticsCollector(ConsoleDownloadStatistics())
    app.open(activityFiles)
    if title:
        app.title = title
    app.start()
    print("Running at \"" + app.url + "\".")
    try:
        while True:
            time.sleep(1000)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("Oops: " + str(e))
    print("Stopping.")
    app.stop()
    app.close()

if __name__ == "__main__":
    if __package__ == "fitbrowser":
        from . import fitbrowser
    else:
        import fitbrowser
    fitbrowser.run(False)
