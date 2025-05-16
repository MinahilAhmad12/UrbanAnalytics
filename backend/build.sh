#!/usr/bin/env bash

# Install system dependencies
apt-get update && apt-get install -y binutils libproj-dev gdal-bin

# Install Python dependencies
pip install -r requirements.txt
