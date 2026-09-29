#!/usr/bin/env bash
# Compatibility entry point for GPTmoment for robot.
set -euo pipefail
exec bash "$(dirname "$0")/start_gptmoment.sh" "$@"
