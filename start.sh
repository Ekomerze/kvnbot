#!/bin/bash
python kvn.py
gunicorn -b 0.0.0.0:5000 kvn:app
