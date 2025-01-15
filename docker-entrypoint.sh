#!/bin/bash
~/.local/bin/ddtrace-run .local/bin/gunicorn --workers 2 --bind 0:8000 app:app
