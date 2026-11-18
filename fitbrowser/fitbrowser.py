#!python
#

"""
Command-line interface.
"""

import glob
import locale
import argparse

if __package__ == "fitbrowser":
    from . import fitui
    from . import fitapp
else:
    import fitui
    import fitapp

def run(ui=None):
    locale.setlocale(locale.LC_ALL, '')
    parser = argparse.ArgumentParser(prog="Fit Browser")
    parser.add_argument('-n', '--noConfigFile', default=False, action="store_true", help="Do not load default configuration file.")
    parser.add_argument('-c', '--configFile', default=None, help="Use this configuration file.")
    parser.add_argument('-v', '--verbose', default=0, action="count", help="Verbosity level.")
    parser.add_argument('--ui', default=None, action=argparse.BooleanOptionalAction, help="Whether to run the UI or on the console.")
    parser.add_argument('-t', '--title', default=None, help="The title to use for HTML pages.")
    parser.add_argument('activityFiles', nargs="*", default=[], help="The activity files to load.")
    args = parser.parse_args()

    useUi = True if ui is None and args.ui is None else (ui if args.ui is None else args.ui)
    useConfigFile = not args.noConfigFile
    configFile = args.configFile
    verbosity = args.verbose
    title = args.title

    activityFiles = []
    for activityFile in args.activityFiles:
        activityFiles.extend(glob.glob(activityFile))

    if useUi:
        fitui.run(activityFiles, title, useConfigFile, configFile, verbosity)
    else:
        if len(activityFiles) == 0:
            # pylint: disable=consider-using-sys-exit
            print("Must provide activity file.")
            exit(1)
        fitapp.run(activityFiles, title, useConfigFile, configFile, verbosity)

if __name__ == "__main__":
    run()
