#!python

"""
Fit Browser.
"""

import sys
from .fitbrowser import *

if not "-m" in sys.argv:
    def runApp(ui=None):
        fitbrowser.run(ui)

    def runUi():
        runApp(True)

    def runCli():
        runApp(False)
