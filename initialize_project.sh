#!/bin/bash

# NOTE: Ensure that the following applications are present in your system
# # - Docker
# # - Docker Compose
# # - UV

export POSTGRES_PASSWORD="masterpassword"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

docker compose up -d
uv sync
uv run manage.py migrate
uv run manage.py populate_data

# Run tests
uv run coverage run manage.py test
uv run coverage report

uv run celery -A project worker -Bl info --detach
uv run manage.py runserver