#!/bin/sh
# Generate Django migration files inside a throwaway container and write them into this folder.
# Run from the project root, then commit the new files under */migrations/.
set -e
docker compose run --rm --no-deps --entrypoint "" -u "$(id -u):$(id -g)" -v "$PWD:/app" web \
  python manage.py makemigrations accounts catalog sales
