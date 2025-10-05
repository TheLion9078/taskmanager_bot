#!/bin/bash
set -o errexit  # stop on error

pip install -r requirements.txt
python main.py
