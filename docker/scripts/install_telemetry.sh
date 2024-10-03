#!/bin/bash

# This script is run in a GitLab CI pipeline. The CI context provides information such as the paths
# used in this script.

# Set up a virtual environment to install modules needed for building the telemetry package
# but not needed in the image.
START_DIR=$(pwd)
BASEDIR=/ExportTracesRepo/docker/scripts/telemetry
cd "$BASEDIR" || exit
python3 -m venv venv
source venv/bin/activate
python3 -m pip install build

# Build
PROJECT=$(python3 setup.py --name)
VERSION=$(python3 setup.py --version)
python3 -m build

### Transfer
deactivate
# Install to the default Python instance of the image.
python3 -m pip install -U "$BASEDIR/dist/$PROJECT-$VERSION-py3-none-any.whl"

### Tear down
rm -rf "${PROJECT}.egg-info" build dist venv
cd "$START_DIR" || exit
