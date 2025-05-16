#!/usr/bin/env bash

# Install GDAL system libs
apt-get update && apt-get install -y gdal-bin libgdal-dev

# Set environment paths if needed
export CPLUS_INCLUDE_PATH=/usr/include/gdal
export C_INCLUDE_PATH=/usr/include/gdal

# Install Python deps
pip install --upgrade pip
pip install -r requirements.txt
