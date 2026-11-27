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

import time
import urllib.parse

if __package__ == "fitbrowser":
    from . import fitact
    from . import fitbgfo
    from . import fithttp
    from . import fitconfig
    from . import fitgeo
    from . import fithtml
else:
    import fitact
    import fitbgfo
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

class HttpHtmlGlue:
    """
    This class is the glue between the message container, which stores messages,
    the HTML formatter, which is responsible for the conversion of messages to
    HTML, and the HTTP request handler, wich serves requests from the HTTP server.
    """

    def __init__(self, resourceGenerator):
        self.resourceGenerator = resourceGenerator
        self.statisticsCollector = QuietDownloadStatistics()

    def setStatisticsCollector(self, collector):
        self.statisticsCollector = collector

    def getHttpHeaders(self, httpPath):
        path = urllib.parse.unquote(httpPath)
        if path == "/":
            return 301, {"Location": "index.html"}

        if not self.hasFile(path):
            self.statisticsCollector.oops("Requested file \"" + path + "\" is not available.")
            return 404, None

        contentType = self.getContentTypeFromFileName(path)
        return 200, {"Content-Type": contentType}

    def getFile(self, httpPath, wfile):
        path = urllib.parse.unquote(httpPath)
        updatecb = self.statisticsCollector.start(path)
        try:
            if self.resourceGenerator.hasFile(path):
                self.resourceGenerator.copyFile(path, wfile, updatecb)
            else:
                updatecb.finish(False)
                raise Exception("Oops: \"" + path + "\".")
            updatecb.finish(True)
        except ConnectionAbortedError:
            updatecb.finish(False)
        except ConnectionResetError:
            updatecb.finish(False)

    def hasFile(self, path):
        if self.resourceGenerator.hasFile(path):
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
        self.groupedActivities = None
        self.httpHtmlGlue = None
        self.httpServerManager = None
        self.httpBackend = None
        self.statisticsCollector = None
        self.resourceGenerator = None
        self.config = fitconfig.FitConfig(useConfigFile, configFile)

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

    def updateConfiguration(self):
        self.config.save()

    def open(self, files):
        activities = fitact.open_activities(files)
        self.setActivities(activities)

    def setActivities(self, activities):
        self.stop()
        self.filteredActivities = None
        self.unfilteredActivities = activities
        self.groupedActivities = fitact.ActivitiesGroupedByLocation(self.activities, self.config["groupRadiusKm"])

    def close(self):
        self.stop()
        self.filteredActivities = None
        self.unfilteredActivities = None
        self.groupedActivities = None

    def filterByDateRange(self, fromDate, toDate):
        if not fromDate and not toDate:
            self.resetFilter()
        self.filteredActivities = fitact.ActivitiesFilteredByDate(self.activities, fromDate, toDate)
        self.groupedActivities = fitact.ActivitiesGroupedByLocation(self.activities, self.config["groupRadiusKm"])

    def currentDateRangeFilter(self):
        if not self.filteredActivities:
            return None, None
        return self.filteredActivities.from_time, self.filteredActivities.to_time

    def resetFilter(self):
        self.filteredActivities = None
        self.groupedActivities = fitact.ActivitiesGroupedByLocation(self.activities, self.config["groupRadiusKm"])

    def startHttpServer(self):
        if self.httpServerManager:
            return
        geoLocator = fitgeo.NearestCity(self.config)
        self.resourceGenerator = fithtml.ResourceGenerator(self.activities, self.groupedActivities, self.config, geoLocator)
        self.httpBackend = HttpHtmlGlue(self.resourceGenerator)
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

class ConsoleFileOpener(fitbgfo.BgFilesOpener):
    """
    Halper class to open activity files in the background, showing progress
    on the console.
    """

    updatePeriodMs = 200

    def __init__(self, files, verbosity):
        self.verbosity = verbosity
        self.fileCount = 0
        self.totalCount = 0
        self.lastActivity = time.time()
        self.currentFile = None
        super().__init__(files, self.activityLoaded, self.fileLoaded)

    def fileLoaded(self, fileName, isFinished):
        self.currentFile = fileName
        if self.verbosity > 0:
            if not isFinished:
                self.fileCount = 0
                print(f"Loading \"{self.currentFile}\" ... {self.fileCount} ", end="\r", flush=True)
            else:
                self.totalCount += self.fileCount
                print(f"Loading \"{self.currentFile}\" ... done, {self.fileCount} activities loaded.")

    def activityLoaded(self, activity):
        self.fileCount += 1
        if self.verbosity > 1:
            now = time.time()
            if ((now - self.lastActivity) * 1000) >= ConsoleFileOpener.updatePeriodMs:
                print(f"Loading \"{self.currentFile}\" ... {self.fileCount} ", end="\r", flush=True)
                self.lastActivity = now

    def finish(self):
        if self.verbosity > 0 and self.fileCount != self.totalCount:
            print(f"Loaded {self.totalCount} activities.")

#
# Allow to run from the command line.
#

def run(activityFiles=None, useConfigFile=True, configFile=None, verbosity=0):
    # pylint: disable=import-outside-toplevel
    if activityFiles is None or len(activityFiles) == 0:
        raise Exception("No activity files provided.")
    app = App(useConfigFile, configFile)
    if verbosity > 0:
        app.setStatisticsCollector(ConsoleDownloadStatistics())
    cfo = ConsoleFileOpener(activityFiles, verbosity)
    cfo.wait()
    cfo.finish()
    activities = cfo.get()
    app.setActivities(activities)
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
