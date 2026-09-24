#!/bin/sh
# Migrations are an explicit one-shot service, never an API/worker startup side effect.
set -eu
umask 077
exec "$@"
