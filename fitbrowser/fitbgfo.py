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
Open a activity file(s) in a background, calling a callback for each
file that is processed and for all activity that is loaded.
"""

import threading

if __package__ == "fitbrowser":
    from . import fitact
else:
    import fitact

class BgFileOpener:
    """
    Open an activity file in a background, calling a callback for each
    activity that is loaded.
    """

    def __init__(self, file, activityCallback=None, fileCallback=None):
        self.file = file
        self.activities = None
        self.success = False
        self.thread = None
        self.activityCallback = activityCallback
        self.fileCallback = fileCallback
        self.canceled = False
        self.running = True
        self.thread = threading.Thread(target=self.openActivities)
        self.thread.start()

    def __del__(self):
        self.close()

    def __bool__(self):
        return self.success

    @property
    def done(self):
        return not self.running

    def get(self):
        return self.activities

    def cancel(self):
        self.canceled = True

    def close(self):
        if self.thread and self.thread != threading.current_thread():
            self.thread.join()
            self.thread = None

    def wait(self):
        if self.running:
            self.close()

    def openFinished(self, success):
        self.success = success
        self.running = False
        if self.fileCallback is not None:
            self.fileCallback(self.file, True)

    def openActivities(self):
        if self.fileCallback is not None:
            self.fileCallback(self.file, False)

        try:
            self.activities = fitact.open_activities(self.file, self.activityCallback)
        except Exception:
            self.openFinished(False)
            return

        self.openFinished(not self.canceled)

class BgFilesIterator:
    """
    Iterator helper for downloading multiple files.
    """

    def __init__(self, downloader):
        self.downloader = downloader
        self.index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= len(self.downloader):
            raise StopIteration
        this = self.downloader[self.index]
        self.index += 1
        return this

class BgFilesOpener:
    """
    Sequentially open multiple activity files in the background.
    """

    def __init__(self, files, activityCallback=None, fileCallback=None):
        self.index = 0
        self.files = files
        self.activities = None
        self.canceled = False
        self.running = True
        self.currentFile = None
        self.downloads = [None for i in range(len(files))]
        self.activityCallback = activityCallback
        self.fileCallback = fileCallback
        self.startDownload()

    def __bool__(self):
        success = True
        for download in self.downloads:
            if (download is None) or not bool(download):
                success = False
        return success

    def __len__(self):
        return len(self.files)

    def __iter__(self):
        return BgFilesIterator(self)

    def __contains__(self, index):
        return (index >= 0) and (index < len(self.files))

    def __getitem__(self, index):
        if index >= len(self.files):
            raise IndexError
        return self.downloads[index]

    @property
    def done(self):
        return not self.running

    def cancel(self):
        self.canceled = True
        if self.running:
            self.downloads[self.index].cancel()

    def wait(self):
        while self.running:
            if self.index >= len(self.files):
                return
            self.downloads[self.index].wait()

    def startDownload(self):
        if (self.index < len(self.files)) and not self.canceled:
            file = self.files[self.index]
            self.downloads[self.index] = BgFileOpener(file, self.activityCallback, self.openFinished)
        elif self.running:
            if bool(self):
                self.activities = fitact.MergedActivities([sub.activities for sub in self.downloads])
            self.running = False

    def openFinished(self, currentFile, isFinished):
        if self.fileCallback is not None:
            self.fileCallback(currentFile, isFinished)
        if not isFinished:
            self.currentFile = currentFile
            return
        if not self.running or self.canceled:
            return
        if self.downloads[self.index] is None:
            return
        if self.downloads[self.index].done:
            self.index += 1
            self.startDownload()

    def getCurrentName(self):
        return self.currentFile
