
#!/bin/sh
set -e

# This script is only for evaluation containers
# It expects ENV_ID and SCRIPT_PATH to be set

if [ -z "$ENV_ID" ]; then
  echo "ERROR: ENV_ID is not set"
  exit 1
fi

if [ -z "$SCRIPT_PATH" ]; then
  echo "ERROR: SCRIPT_PATH is not set"
  exit 1
fi

if [ ! -f "$SCRIPT_PATH" ]; then
  echo "ERROR: Script file not found: $SCRIPT_PATH"
  exit 1
fi

# Run the script
exec python "$SCRIPT_PATH" "$ENV_ID"


chmod +x scripts/entrypoint.sh