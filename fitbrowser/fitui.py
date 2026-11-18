#!python

"""
The GUI.
"""

import datetime
import threading
import tkinter
import tkinter.filedialog
from tkinter import ttk, font
from pathlib import Path

if __package__ == "fitbrowser":
    from . import fitapp
    from . import fitcss
    from . import fitkey
    from . import fitgeo
else:
    import fitapp
    import fitcss
    import fitkey
    import fitgeo

try:
    import pyperclip
    havePyperClip = True
except:
    havePyperClip = False

try:
    import tkinterdnd2
    haveDnd = True
except:
    haveDnd = False

#
# Download statistics collector.
#

class DownloadStatisticsCollector:
    """
    Callback tracking HTTP requests. See wacbapp.HttpHtmlGlue.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.totalDownloads = 0
            self.activeDownloads = 0
            self.successfulDownloads = 0
            self.failedDownloads = 0
            self.bytesServed = 0

    def start(self, fileName):
        with self.lock:
            self.activeDownloads += 1
        return self

    def oops(self, message):
        pass

    def update(self, bytesServed):
        with self.lock:
            self.bytesServed += bytesServed

    def finish(self, success):
        with self.lock:
            self.activeDownloads -= 1
            self.totalDownloads += 1
            if success:
                self.successfulDownloads += 1
            else:
                self.failedDownloads += 1

class HttpConfigurator(tkinter.Toplevel):
    """
    Top-level window for HTTP configuration.
    """

    def __init__(self, parent, currentHostName=None, currentPortNumber=None):
        super().__init__(parent.top)
        self.success = False
        self.parent = parent
        self.top = self.parent.top
        self.hostName = tkinter.StringVar()
        self.portNumber = tkinter.StringVar()
        self.statusMessage = tkinter.StringVar()
        self.widgets = dict()
        self.createWidgets()
        self.statusMessage.set("Edit HTTP Server configuration.")
        if currentHostName:
            self.hostName.set(currentHostName)
        else:
            self.hostName.set("localhost")
        if currentPortNumber:
            self.portNumber.set(str(currentPortNumber))
        else:
            self.portNumber.set("0")

    def __bool__(self):
        return self.success

    def createWidgets(self):
        self.title("HTTP Server configuration")

        hostNameFrame = ttk.Frame(self)
        hostNameLabel = ttk.Label(hostNameFrame, text="Host Name", width=12, font=self.parent.defaultFont)
        hostNameEntry = ttk.Entry(hostNameFrame, width=30, textvariable=self.hostName)
        hostNameLabel.pack(side="left", padx=10)
        hostNameEntry.pack(side="left", fill="x", expand="yes", padx=10)
        hostNameFrame.pack(side="top", fill="x")

        portNumberFrame = ttk.Frame(self)
        portNumberLabel = ttk.Label(portNumberFrame, text="Port Number", width=12, font=self.parent.defaultFont)
        portNumberEntry = ttk.Entry(portNumberFrame, width=30, textvariable=self.portNumber)
        portNumberLabel.pack(side="left", padx=10)
        portNumberEntry.pack(side="left", fill="x", expand="yes", padx=10)
        portNumberFrame.pack(side="top", fill="x")

        buttonFrame = ttk.Frame(self)
        buttonFrameInt = ttk.Frame(buttonFrame)
        okButton = ttk.Button(buttonFrameInt, text="OK", width=12, command=self.okButtonPressed)
        cancelButton = ttk.Button(buttonFrameInt, text="Cancel", width=12, command=self.cancelButtonPressed)
        okButton.pack(side="left", padx=10)
        cancelButton.pack(side="left", padx=10)
        buttonFrameInt.pack(side="top", expand="yes", anchor="c")
        buttonFrame.pack(side="top", padx=10, pady=5)

        statusFrame = ttk.Frame(self)
        statusLabel = ttk.Label(statusFrame, textvariable=self.statusMessage, relief="sunken", width=40)
        statusLabel.pack(side="left", fill="x", expand="yes")
        statusFrame.pack(side="top", fill="x")

    def okButtonPressed(self):
        self.success = True
        self.destroy()

    def cancelButtonPressed(self):
        self.success = False
        self.destroy()

    def run(self):
        self.grab_set()
        self.parent.top.wait_window(self)

class FilterByDate(tkinter.Toplevel):
    """
    Top-level window for filtering by date.
    """

    def __init__(self, parent, app):
        super().__init__(parent.top)
        self.success = False
        self.parent = parent
        self.top = self.parent.top
        self.fromDate = None
        self.toDate = None
        self.fromDateVar = tkinter.StringVar()
        self.toDateVar = tkinter.StringVar()
        self.statusMessage = tkinter.StringVar()
        self.app = app
        self.widgets = dict()
        self.createWidgets()
        self.updateFromAndToDates()
        self.statusMessage.set("Filter By Date.")

    def __bool__(self):
        return self.success

    def createWidgets(self):
        self.title("Filter By Date")

        fromFrame = ttk.Frame(self)
        fromLabel = ttk.Label(fromFrame, text="From", width=8, anchor="e", font=self.parent.defaultFont)
        fromEntry = ttk.Entry(fromFrame, width=30, textvariable=self.fromDateVar)
        fromLabel.pack(side="left", padx=10)
        fromEntry.pack(side="left", fill="x", expand="yes", padx=10)
        fromFrame.pack(side="top", fill="x")

        toFrame = ttk.Frame(self)
        toLabel = ttk.Label(toFrame, text="To", width=8, anchor="e", font=self.parent.defaultFont)
        toEntry = ttk.Entry(toFrame, width=30, textvariable=self.toDateVar)
        toLabel.pack(side="left", padx=10)
        toEntry.pack(side="left", fill="x", expand="yes", padx=10)
        toFrame.pack(side="top", fill="x")

        buttonFrame = ttk.Frame(self)
        buttonFrameInt = ttk.Frame(buttonFrame)
        buttonApply = ttk.Button(buttonFrame, text="Apply", width=12, command=self.applyButtonPressed)
        buttonCancel = ttk.Button(buttonFrame, text="Cancel", width=12, command=self.cancelButtonPressed)
        buttonApply.pack(side="left", padx=10)
        buttonCancel.pack(side="left", padx=10)
        buttonFrameInt.pack(side="top", expand="yes", anchor="c")
        buttonFrame.pack(side="top", padx=10, pady=5)

        statusFrame = ttk.Frame(self)
        statusLabel = ttk.Label(statusFrame, textvariable=self.statusMessage, relief="sunken", width=40)
        statusLabel.pack(side="left", fill="x", expand="yes")
        statusFrame.pack(side="top", fill="x")

    def updateFromAndToDates(self):
        if len(self.app.activities) == 0:
            return
        firstYear, firstMonth, firstDay = self.app.activities.calendar.getFirstDay()
        lastYear, lastMonth, lastDay = self.app.activities.calendar.getLastDay()
        self.fromDateVar.set("{0:04d}-{1:02d}-{2:02d}".format(firstYear, firstMonth, firstDay))
        self.toDateVar.set("{0:04d}-{1:02d}-{2:02d}".format(lastYear, lastMonth, lastDay))

    def getDateFromEntry(self, label, name):
        dateTxt = label.get().strip()
        if len(dateTxt) > 0:
            try:
                date = datetime.datetime.strptime(dateTxt, "%Y-%m-%d").date()
            except:
                self.statusMessage.set("Invalid \"" + name + "\" date, must be yyyy-mm-dd.")
                raise
        else:
            date = None
        return date

    def applyButtonPressed(self):
        try:
            self.fromDate = self.getDateFromEntry(self.fromDateVar, "From")
            self.toDate = self.getDateFromEntry(self.toDateVar, "To")
        except:
            return
        self.success = True
        self.destroy()

    def cancelButtonPressed(self):
        self.success = False
        self.destroy()

    def run(self):
        self.grab_set()
        self.parent.top.wait_window(self)

class GeonamesConfigurator(tkinter.Toplevel):
    """
    Top-level window for Geonames configuration.
    """

    def __init__(self, parent, currentUserName=None, currentDatabase=None):
        super().__init__(parent.top)
        self.success = False
        self.parent = parent
        self.top = self.parent.top
        self.userName = tkinter.StringVar()
        self.database = tkinter.StringVar()
        self.statusMessage = tkinter.StringVar()
        self.widgets = dict()
        self.createWidgets()
        self.statusMessage.set("Edit Geonames configuration.")
        if currentUserName:
            self.userName.set(currentUserName)
        else:
            self.userName.set("")
        if currentDatabase:
            self.database.set(currentDatabase)
        else:
            self.database.set("")

    def __bool__(self):
        return self.success

    def createWidgets(self):
        self.title("Geonames Configuration")

        userNameFrame = ttk.Frame(self)
        userNameLabel = ttk.Label(userNameFrame, text="User Name", width=12, font=self.parent.defaultFont)
        userNameEntry = ttk.Entry(userNameFrame, width=30, textvariable=self.userName)
        userNameLabel.pack(side="left", padx=10)
        userNameEntry.pack(side="left", fill="x", expand="yes", padx=10)
        userNameFrame.pack(side="top", fill="x")

        databaseFrame = ttk.Frame(self)
        databaseLabel = ttk.Label(databaseFrame, text="Database", width=12, font=self.parent.defaultFont)
        databaseEntry = ttk.Entry(databaseFrame, width=30, textvariable=self.database)
        databaseLabel.pack(side="left", padx=10)
        databaseEntry.pack(side="left", fill="x", expand="yes", padx=10)
        databaseFrame.pack(side="top", fill="x")

        buttonFrame = ttk.Frame(self)
        buttonFrameInt = ttk.Frame(buttonFrame)
        okButton = ttk.Button(buttonFrameInt, text="OK", width=12, command=self.okButtonPressed)
        cancelButton = ttk.Button(buttonFrameInt, text="Cancel", width=12, command=self.cancelButtonPressed)
        okButton.pack(side="left", padx=10)
        cancelButton.pack(side="left", padx=10)
        buttonFrameInt.pack(side="top", expand="yes", anchor="c")
        buttonFrame.pack(side="top", padx=10, pady=5)

        statusFrame = ttk.Frame(self)
        statusLabel = ttk.Label(statusFrame, textvariable=self.statusMessage, relief="sunken", width=40)
        statusLabel.pack(side="left", fill="x", expand="yes")
        statusFrame.pack(side="top", fill="x")

    def okButtonPressed(self):
        self.success = True
        self.destroy()

    def cancelButtonPressed(self):
        self.success = False
        self.destroy()

    def run(self):
        self.grab_set()
        self.parent.top.wait_window(self)

class GoogleMapsConfigurator(tkinter.Toplevel):
    """
    Top-level window for Google Maps configuration.
    """

    def __init__(self, parent, currentApiKey=None):
        super().__init__(parent.top)
        self.success = False
        self.parent = parent
        self.top = self.parent.top
        self.apiKey = tkinter.StringVar()
        self.statusMessage = tkinter.StringVar()
        self.widgets = dict()
        self.createWidgets()
        self.statusMessage.set("Edit Google Maps configuration.")
        if currentApiKey:
            self.apiKey.set(currentApiKey)
        else:
            self.apiKey.set("")
        if currentApiKey:
            self.apiKey.set(currentApiKey)
        else:
            self.apiKey.set("")

    def __bool__(self):
        return self.success

    def createWidgets(self):
        self.title("Google Maps Configuration")

        apiKeyFrame = ttk.Frame(self)
        apiKeyLabel = ttk.Label(apiKeyFrame, text="API Key", width=12, font=self.parent.defaultFont)
        apiKeyEntry = ttk.Entry(apiKeyFrame, width=30, textvariable=self.apiKey)
        apiKeyLabel.pack(side="left", padx=10)
        apiKeyEntry.pack(side="left", fill="x", expand="yes", padx=10)
        apiKeyFrame.pack(side="top", fill="x")

        buttonFrame = ttk.Frame(self)
        buttonFrameInt = ttk.Frame(buttonFrame)
        okButton = ttk.Button(buttonFrameInt, text="OK", width=12, command=self.okButtonPressed)
        cancelButton = ttk.Button(buttonFrameInt, text="Cancel", width=12, command=self.cancelButtonPressed)
        okButton.pack(side="left", padx=10)
        cancelButton.pack(side="left", padx=10)
        buttonFrameInt.pack(side="top", expand="yes", anchor="c")
        buttonFrame.pack(side="top", padx=10, pady=5)

        statusFrame = ttk.Frame(self)
        statusLabel = ttk.Label(statusFrame, textvariable=self.statusMessage, relief="sunken", width=40)
        statusLabel.pack(side="left", fill="x", expand="yes")
        statusFrame.pack(side="top", fill="x")

    def okButtonPressed(self):
        self.success = True
        self.destroy()

    def cancelButtonPressed(self):
        self.success = False
        self.destroy()

    def run(self):
        self.grab_set()
        self.parent.top.wait_window(self)

class FitBrowser(tkinter.Frame):
    """
    The main user interface.
    """

    updatePeriodMs = 1000

    def __init__(self, top, useConfigFile=True, configFile=None):
        super().__init__(top)
        self.top = top
        self.app = fitapp.App(useConfigFile, configFile)
        self.autostart = tkinter.BooleanVar()
        self.builtinCss = tkinter.BooleanVar()
        self.numberOfActivities = tkinter.StringVar()
        self.numberOfLocations = tkinter.StringVar()
        self.statusMessage = tkinter.StringVar()
        self.statusMessage.set("Fit Browser.")
        self.statusLoaded = tkinter.StringVar()
        self.statusRunning = tkinter.StringVar()
        self.statisticsCollector = None
        self.widgets = {}
        self.createWidgets()
        self.setupDnd()
        self.updateUiConfigurationFromApp()
        self.updateWidgets()

    def createWidgets(self):
        self.defaultFont = font.Font(family="Times", size=16)
        buttonStyle = ttk.Style()
        buttonStyle.configure("TButton", font=self.defaultFont)
        buttonStyle.configure("TRadiobutton", font=self.defaultFont)

        #
        # Title.
        #

        self.top.title("Fit Browser")

        #
        # Menu bar.
        #

        menuBar = tkinter.Menu()
        fileMenu = tkinter.Menu(menuBar, tearoff=0)
        fileMenu.add_command(label="Open ...", command=self.openFromMenu)
        fileMenu.add_command(label="Close", command=self.closeFromMenu)
        fileMenu.add_separator()
        fileMenu.add_command(label="Exit", command=self.exitFromMenu)
        menuBar.add_cascade(label="File", menu=fileMenu)
        self.widgets["fileMenu"] = fileMenu

        filterMenu = tkinter.Menu(menuBar, tearoff=0)
        filterMenu.add_command(label="By Date ...", command=self.filterByDateFromMenu)
        filterMenu.add_separator()
        filterMenu.add_command(label="Reset", command=self.resetFilterFromMenu)
        menuBar.add_cascade(label="Filter", menu=filterMenu)
        self.widgets["filterMenu"] = filterMenu

        serverMenu = tkinter.Menu(menuBar, tearoff=0)
        serverMenu.add_command(label="Start", command=self.startFromMenu)
        serverMenu.add_command(label="Stop", command=self.stopFromMenu)
        serverMenu.add_separator()
        serverMenu.add_command(label="Copy URL to Clipboard", command=self.copyUrlFromMenu)
        serverMenu.add_command(label="Open URL in Browser", command=self.openUrlFromMenu)
        menuBar.add_cascade(label="Server", menu=serverMenu)
        self.widgets["serverMenu"] = serverMenu

        optionsMenu = tkinter.Menu(menuBar, tearoff=0)
        optionsMenu.add_checkbutton(label="Autostart", variable=self.autostart, onvalue=True, offvalue=False)

        cssMenu = tkinter.Menu(optionsMenu, tearoff=0)
        cssMenu.add_checkbutton(label="Built-In", variable=self.builtinCss, onvalue=True, offvalue=False)
        cssMenu.add_command(label="Load ...", command=self.selectCssFileFromMenu)
        cssMenu.add_command(label="Save Template As ...", command=self.saveCssTemplateFromMenu)
        optionsMenu.add_cascade(label="Style Sheet", menu=cssMenu)
        
        optionsMenu.add_command(label="HTTP ...", command=self.configureHTTPFromMenu)
        optionsMenu.add_command(label="Google Maps ...", command=self.configureGoogleMapsFromMenu)
        optionsMenu.add_command(label="Geonames ...", command=self.configureGeonamesFromMenu)
        menuBar.add_cascade(label="Options", menu=optionsMenu)
        self.widgets["optionsMenu"] = optionsMenu

        self.top.config(menu=menuBar)
        self.top.bind("<Control-o>", self.openFromHotkey)
        self.top.bind("<Control-w>", self.closeFromHotkey)
        self.top.bind("<Control-x>", self.exitFromHotkey)
        self.widgets["menuBar"] = menuBar

        #
        # First frame: Number of activities.
        #

        activitiesFrame = ttk.Frame(self.top)
        activitiesIntFrame = ttk.Frame(activitiesFrame)
        activitiesEntry = ttk.Label(activitiesIntFrame, width=10, textvariable=self.numberOfActivities, anchor="e", font=self.defaultFont)
        activitiesLabel = ttk.Label(activitiesIntFrame, text="Activities", width=12, font=self.defaultFont)
        activitiesEntry.pack(side="left", fill="x", padx=10)
        activitiesLabel.pack(side="left")
        activitiesIntFrame.pack(side="top", fill="x")
        activitiesFrame.pack(side="top", anchor="c", padx=10, pady=5)

        #
        # Second frame: Number of locations.
        #

        locationsFrame = ttk.Frame(self.top)
        locationsIntFrame = ttk.Frame(locationsFrame)
        locationsEntry = ttk.Label(locationsIntFrame, width=10, textvariable=self.numberOfLocations, anchor="e", font=self.defaultFont)
        locationsLabel = ttk.Label(locationsIntFrame, text="Locations", width=12, font=self.defaultFont)
        locationsEntry.pack(side="left", fill="x", padx=10)
        locationsLabel.pack(side="left")
        locationsIntFrame.pack(side="top", fill="x")
        locationsFrame.pack(side="top", anchor="c", padx=10, pady=5)

        #
        # Status.
        #

        statusFrame = ttk.Frame(self.top)
        statusLabel = ttk.Label(statusFrame, textvariable=self.statusMessage, relief="sunken", width=40)
        statusLoaded = tkinter.Label(statusFrame, textvariable=self.statusLoaded, relief="sunken", width=12)
        statusRunning = tkinter.Label(statusFrame, textvariable=self.statusRunning, relief="sunken", width=12)
        statusLabel.pack(side="left", fill="x", expand="yes")
        statusLoaded.pack(side="left")
        statusRunning.pack(side="left")
        statusFrame.pack(side="top", fill="x")
        self.widgets["statusLoaded"] = statusLoaded
        self.widgets["statusRunning"] = statusRunning
        statusLoaded.bind("<Button-1>", self.statusLoadedClicked)
        statusRunning.bind("<Button-1>", self.statusRunningClicked)

    @property
    def loaded(self):
        return bool(self.app.activities)

    @property
    def running(self):
        return self.app.running

    #
    # Irritatingly, event.data is a Tcl style list.
    # - File names with spaces are quoted, Tcl-style, with {}.
    # - Multiple file names are separated with spaces.
    #

    def filesDropped(self, event=None):
        if event and event.data:
            fileNames = []
            data = event.data
            pos = 0
            while pos < len(data):
                if data[pos] == "{":
                    ep = data.find("}", pos)
                    if ep == -1:
                        return
                    fileNames.append(data[pos+1:ep])
                    pos = ep + 1
                elif data[pos] == " ":
                    pos = pos + 1
                else:
                    ep = data.find(" ", pos)
                    if ep == -1:
                        fileNames.append(data[pos:])
                        pos = len(data)
                    else:
                        fileNames.append(data[pos:ep])
                        pos = ep
            self.open(fileNames)

    def setupDnd(self):
        if haveDnd:
            self.top.drop_target_register(tkinterdnd2.DND_FILES)
            self.top.dnd_bind("<<Drop>>", self.filesDropped)

    def updateUiConfigurationFromApp(self):
        config = self.app.config
        self.autostart.set(config["autostart"])
        self.builtinCss.set(config["html"]["builtinCss"])

    def updateAppConfigurationFromUi(self):
        config = self.app.config
        config["autostart"] = self.autostart.get()
        config["html"]["builtinCss"] = self.builtinCss.get()
        self.app.updateConfiguration()

    def updateButtonState(self, name, state):
        stateValue = "!disabled" if state else "disabled"
        self.widgets[name].state([stateValue])

    def updateMenuItemState(self, menu, item, state):
        stateValue = "normal" if state else "disabled"
        self.widgets[menu].entryconfig(item, state=stateValue)

    def updateFileMenuItemState(self, item, state):
        self.updateMenuItemState("fileMenu", item, state)

    def updateServerMenuItemState(self, item, state):
        self.updateMenuItemState("serverMenu", item, state)

    def updateMenuBarItemState(self, item, state):
        self.updateMenuItemState("menuBar", item, state)

    def updateWidgets(self):
        self.updateAppConfigurationFromUi()
        self.updateFileMenuItemState("Open ...", not self.running)
        self.updateFileMenuItemState("Close", self.loaded)
        self.updateServerMenuItemState("Start", self.loaded and not self.running)
        self.updateServerMenuItemState("Stop", self.running)
        self.updateServerMenuItemState("Copy URL to Clipboard", havePyperClip and self.running)
        self.updateServerMenuItemState("Open URL in Browser", self.running)
        self.updateMenuBarItemState("Filter", self.loaded and not self.running)
        self.updateMenuBarItemState("Options", not self.running)

        loadedBackground = "#00ff00" if self.loaded else self.widgets["statusLoaded"].configure()["background"][3]
        self.widgets["statusLoaded"].configure(background=loadedBackground)
        loadedMessage = "Loaded." if self.loaded else "No file."
        self.statusLoaded.set(loadedMessage)

        runningBackground = "#00ff00" if self.running else self.widgets["statusRunning"].configure()["background"][3]
        self.widgets["statusRunning"].configure(background=runningBackground)
        runningMessage = "Running." if self.running else "Stopped."
        self.statusRunning.set(runningMessage)

    def browseForFilesToOpen(self):
        title = "Select chat(s) to open."
        fileTypeSuggestion = [["FIT Files", "*.fit"], ["Training Center Files", "*.tcx"], ["Sport Tracks Files", "*.logbook3"], ["Apple Health Files", "*.gpx"], ["Zip Files", "*.zip"]]
        return tkinter.filedialog.askopenfilenames(title=title, filetypes=fileTypeSuggestion)

    def updateWidgetsAfterOpen(self):
        numberOfActivities = len(self.app.activities)
        numberOfLocations = len(self.app.groupedActivities)
        self.numberOfActivities.set(str(numberOfActivities))
        self.numberOfLocations.set(str(numberOfLocations))
        self.statusMessage.set("{0} activities loaded.".format(numberOfActivities))
        
        self.updateWidgets()
        if self.loaded and self.app.config["autostart"]:
            self.start()

    def open(self, fileNames):
        try:
            self.app.open(fileNames)
        except:
            self.statusMessage.set("Failed to load \"" + str(fileNames) + "\".")
            return
        self.updateWidgetsAfterOpen()

    def close(self):
        self.app.close()
        self.numberOfActivities.set("")
        self.numberOfLocations.set("")
        self.updateWidgets()
        self.statusMessage.set("No file.")

    def start(self):
        if not self.loaded:
            return
        self.updateAppConfigurationFromUi()
        self.statisticsCollector = DownloadStatisticsCollector()
        self.app.setStatisticsCollector(self.statisticsCollector)
        self.app.start()
        self.updateWidgets()
        self.statusMessage.set("Server started at " + self.app.url + ".")
        self.top.after(FitBrowser.updatePeriodMs, self.updateStatistics)

    def updateStatistics(self):
        if not self.running:
            return
        totalDownloads = self.statisticsCollector.totalDownloads
        activeDownloads = self.statisticsCollector.activeDownloads
        bytesServed = self.statisticsCollector.bytesServed
        if totalDownloads > 0 or bytesServed > 0:
            statsMessage = "{0} downloads, ".format(totalDownloads)
            statsMessage += "{0} active, ".format(activeDownloads)
            statsMessage += "{0:.1f} MB served.".format(bytesServed / (1 << 20))
            self.statusMessage.set(statsMessage)
        self.top.after(FitBrowser.updatePeriodMs, self.updateStatistics)

    def stop(self):
        self.app.stop()
        self.updateWidgets()
        self.statusMessage.set("Stopped.")

    def exitFromMenu(self):
        self.app.stop()
        self.app.close()
        self.top.quit()

    def exitFromHotkey(self, event=None):
        self.exitFromMenu()

    def openFromMenu(self):
        fileNames = self.browseForFilesToOpen()
        if len(fileNames) > 0:
            self.open(fileNames)

    def openFromHotkey(self, event=None):
        self.openFromMenu()

    def closeFromMenu(self):
        self.close()
        self.statusMessage.set("No file loaded.")

    def closeFromHotkey(self, event=None):
        self.closeFromMenu()

    def startFromMenu(self):
        self.start()

    def stopFromMenu(self):
        self.stop()

    def configureHTTPFromMenu(self):
        currentHttpHostName = self.app.config["http"]["hostName"]
        currentHttpPortNumber = self.app.config["http"]["portNumber"]
        httpConfigurator = HttpConfigurator(self, currentHttpHostName, currentHttpPortNumber)
        httpConfigurator.run()
        if httpConfigurator:
            newHostName = httpConfigurator.hostName.get().strip()
            newPortNumber = httpConfigurator.portNumber.get().strip()
            if len(newPortNumber) == 0:
                newPortNumber = "0"
            if (len(newHostName) > 0) and newPortNumber.isdigit():
                self.app.config["http"]["hostName"] = newHostName
                self.app.config["http"]["portNumber"] = int(newPortNumber)
                self.updateAppConfigurationFromUi()
                self.statusMessage.set("HTTP Server configuration updated.")
            else:
                self.statusMessage.set("Invalid HTTP Server configuration.")
        else:
            self.statusMessage.set("HTTP Server configuration canceled.")

    def configureGeonamesFromMenu(self):
        currentUserName = self.app.config["geonames"]["userName"]
        currentDatabase = self.app.config["geonames"]["database"]
        geonamesConfigurator = GeonamesConfigurator(self, currentUserName, currentDatabase)
        geonamesConfigurator.run()
        if geonamesConfigurator:
            newUserName = geonamesConfigurator.userName.get().strip()
            newDatabase = geonamesConfigurator.database.get().strip()
            if len(newUserName) > 0 and len(newDatabase) > 0:
                try:
                    isUserNameValid = fitgeo.check_geonames_username(newUserName)
                except:
                    isUserNameValid = False
                if isUserNameValid:
                    self.app.config["geonames"]["userName"] = newUserName
                    self.app.config["geonames"]["database"] = newDatabase
                    self.updateAppConfigurationFromUi()
                    self.statusMessage.set("Geonames configuration updated.")
                else:
                    self.statusMessage.set("Invalid Geonnames user name.")
            else:
                self.statusMessage.set("Invalid Geonames configuration.")
        else:
            self.statusMessage.set("Geonames configuration canceled.")

    def configureGoogleMapsFromMenu(self):
        currentApiKey = self.app.config["googleMaps"]["apiKey"]
        googleMapsConfigurator = GoogleMapsConfigurator(self, currentApiKey)
        googleMapsConfigurator.run()
        if googleMapsConfigurator:
            newApiKey = googleMapsConfigurator.apiKey.get().strip()
            if len(newApiKey) > 0:
                try:
                    isKeyValid = fitkey.check_google_api_key(newApiKey)
                except:
                    isKeyValid = False
                if isKeyValid:
                    self.app.config["googleMaps"]["apiKey"] = newApiKey
                    self.updateAppConfigurationFromUi()
                    self.statusMessage.set("Google Maps configuration updated.")
                else:
                    self.statusMessage.set("Invalid Google Maps API key.")
            else:
                self.statusMessage.set("Invalid Google Maps configuration.")
        else:
            self.statusMessage.set("Google Maps configuration canceled.")

    def filterByDateFromMenu(self):
        self.statusMessage.set("Filtering by date ...")
        dateFilter = FilterByDate(self, self.app)
        dateFilter.run()
        if dateFilter:
            self.app.filterByDateRange(dateFilter.fromDate, dateFilter.toDate)
            self.statusMessage.set(str(len(self.app.activities)) + " activities filtered.")
        else:
            self.statusMessage.set("Filter canceled.")

    def resetFilterFromMenu(self):
        if not self.loaded:
            return
        self.app.resetFilter()
        self.statusMessage.set("Filter reset, " + str(len(self.app.activities)) + " messages loaded.")

    def copyUrlFromMenu(self):
        if self.running:
            if havePyperClip:
                pyperclip.copy(self.app.url)
                self.statusMessage.set("Copied \"" + self.app.url + "\" to clipboard.")
            else:
                self.statusMessage.set("Cannot copy to clipboard: Please install \"pyperclip\" module.")

    def openUrlFromMenu(self):
        if self.running:
            webbrowser.open(self.app.url)
            self.statusMessage.set("Opening browser for \"" + self.app.url + "\".")

    def selectCssFileFromMenu(self):
        self.statusMessage.set("CSS document selection...")
        fileTypeSuggestion = [["CSS Files", "*.css"]]
        fileName = tkinter.filedialog.askopenfilename(filetypes=fileTypeSuggestion)
        if fileName == "":
            return
        cssFileName = str(Path(fileName))
        self.builtinCss.set(False)
        self.config["html"]["cssFileName"] = cssFileName
        self.statusMessage.set("Using CSS document \"" + cssFileName + "\".")
        self.updateAppConfigurationFromUi()

    def saveCssTemplateFromMenu(self):
        self.statusMessage.set("Saving CSS document template ...")
        defaultExtension = ".css"
        fileTypeSuggestion = [["CSS Files", "*.css"]]
        fileName = tkinter.filedialog.asksaveasfilename(filetypes=fileTypeSuggestion, defaultextension=defaultExtension)
        if fileName == "":
            return
        if not fileName.endswith(".css"):
            fileName += ".css"
        try:
            css = fitcss.makeBuiltinCss()
            with open(fileName, "w", encoding="utf-8") as cssFile:
                cssFile.write(css.data)
        except:
            self.statusMessage.set("Error writing CSS template to \"" + fileName + "\".")
            return
        self.statusMessage.set("CSS template saved as \"" + fileName + "\".")

    def statusLoadedClicked(self, event):
        if self.loaded:
            self.close()
        else:
            self.openFromMenu()

    def statusRunningClicked(self, event):
        if self.running:
            self.stop()
        else:
            self.start()

def run(activityFiles=None, title=None, useConfigFile=True, configFile=None, verbosity=0):
    if haveDnd:
        top = tkinterdnd2.TkinterDnD.Tk()
    else:
        top = tkinter.Tk()
    app = FitBrowser(top, useConfigFile, configFile)
    if activityFiles:
        app.open(activityFiles)
    if title:
        app.title.set(title)
    top.mainloop()

if __name__ == "__main__":
    if __package__ == "fitbrowser":
        from . import fitbrowser
    else:
        import fitbrowser
    fitbrowser.run(True)
