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
Handle Fit Browser configuration files.
"""

import math
import json
import pathlib

class DictWrapper:
    """
    Helper to get and set configuration values in a section.
    """

    def __init__(self, config, groupName):
        self.config = config
        self.groupName = groupName

    def __contains__(self, key):
        return key in self.config.config[self.groupName]

    def __getitem__(self, key):
        return self.config.config[self.groupName][key]

    def __setitem__(self, key, value):
        if value != self.config.config[self.groupName][key]:
            self.config.modified = True
            self.config.config[self.groupName][key] = value

    def items(self):
        return self.config.config[self.groupName].items()

class FitConfig:
    """
    Fit Browser configuration.
    """

    configFileLocations = [
        "~/.fitBrowser",
    ]

    defaultConfig = {
        "autostart": True,
        "autoopen": True,
        "groupRadiusKm": 10.0,
        "html": {
            "builtinCss": True,
            "cssFileName": ""
        },
        "http": {
            "hostName": "localhost",
            "portNumber": 0
        },
        "geonames": {
            "enable": False,
            "userName": "",
            "database": "cities15000",
            "cacheRadiusKm": 5.0
        },
        "googleMaps": {
            "enable": False,
            "apiKey": ""
        },
        "locationCache": []
    }

    def __init__(self, useConfigFile, configFile=None):
        self.modified = False
        self.config = FitConfig.defaultConfig
        self.useConfigFile = useConfigFile
        self.configFile = configFile if useConfigFile else None
        self.load()

    def __contains__(self, groupName):
        if groupName not in self.config:
            if groupName in FitConfig.defaultConfig:
                self.config[groupName] = FitConfig.defaultConfig[groupName]
        return groupName in self.config

    def __getitem__(self, groupName):
        if groupName not in self.config:
            if groupName in FitConfig.defaultConfig:
                self.config[groupName] = FitConfig.defaultConfig[groupName]
        if isinstance(self.config[groupName], dict):
            return DictWrapper(self, groupName)
        return self.config[groupName]

    def __setitem__(self, groupName, value):
        if isinstance(self.config[groupName], dict):
            raise Exception("Oops.")
        if value != self.config[groupName]:
            self.config[groupName] = value
            self.modified = True

    def load(self):
        if not self.useConfigFile:
            return
        if self.configFile:
            self.loadConfigFromFile(self.configFile)
            return
        for fileName in FitConfig.configFileLocations:
            try:
                self.loadConfigFromFile(fileName)
                self.configFile = fileName
            except:
                pass

    def save(self):
        if not self.useConfigFile:
            return
        if not self.modified:
            return
        if self.configFile:
            self.writeConfigToFile(self.configFile)
            self.modified = False
            return
        for fileName in FitConfig.configFileLocations:
            try:
                self.writeConfigToFile(fileName)
                self.configFile = fileName
                self.modified = False
            except:
                pass

    def writeConfigToFile(self, fileName):
        path = pathlib.Path(fileName)
        path = path.expanduser()
        with open(path, "w", encoding="utf-8") as file:
            json.dump(self.config, file, indent=4)

    def loadConfigFromFile(self, fileName):
        path = pathlib.Path(fileName)
        path = path.expanduser()
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
        self.merge(data)

    def merge(self, data):
        self.mergeValues(self.config, data, ["autostart", "autoopen", "groupRadiusKm"])
        for toplevel in ["html", "http", "geonames", "googleMaps"]:
            self.mergeToplevel(data, toplevel)
        if "locationCache" in data:
            for record in data["locationCache"]:
                self.addLocationRecord(record)

    def mergeToplevel(self, data, toplevel):
        if toplevel in data:
            keys = FitConfig.defaultConfig[toplevel].keys()
            self.mergeValues(self.config[toplevel], data[toplevel], keys)

    def mergeValues(self, config, data, keys):
        for key in keys:
            if key in data:
                if config[key] != data[key]:
                    config[key] = data[key]
                    self.modified = True

    def haveLocationRecord(self, lat, lon):
        for record in self.config["locationCache"]:
            if math.isclose(lat, record["lat"]) and math.isclose(lon, record["lon"]):
                return True
        return False
                
    def addLocationRecord(self, record):
        if self.haveLocationRecord(record["lat"], record["lon"]):
            return
        self.config["locationCache"].append(record)
        self.modified = True
