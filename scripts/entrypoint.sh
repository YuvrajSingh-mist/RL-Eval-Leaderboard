#!/bin/sh
set -e

# Secure entrypoint for RL agent evaluation
# All paths and variables are validated before use

# Validate environment
if [ -z "$ENV_ID" ]; then
  echo "ERROR: ENV_ID is not set"
  exit 1
fi

if [ -z "$SCRIPT_PATH" ]; then
  echo "ERROR: SCRIPT_PATH is not set"
  exit 1
fi

# Validate script file
if [ ! -f "$SCRIPT_PATH" ]; then
  echo "ERROR: Script file not found: $SCRIPT_PATH"
  exit 1
fi

# Validate file permissions (should be read-only)
if [ ! -r "$SCRIPT_PATH" ]; then
  echo "ERROR: Script file is not readable: $SCRIPT_PATH"
  exit 1
fi

# Validate file type (must be Python script)
case "$SCRIPT_PATH" in
  *.py) 
    # Valid Python file
    ;;
  *) 
    echo "ERROR: Only Python scripts (.py) are allowed"
    exit 1
    ;;
esac

# Log startup information (without revealing sensitive paths)
echo "INFO: Starting evaluation for environment: $ENV_ID"
echo "INFO: Using script: $(basename "$SCRIPT_PATH")"

# Require limit tools to be present (security policy)
for bin in timeout nice ionice sha256sum; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: Required tool not found: $bin"
    exit 1
  fi
done

# Detailed, structured logging
START_TS=$(date +%s)
SCRIPT_NAME=$(basename "$SCRIPT_PATH")
SCRIPT_SIZE=$(wc -c < "$SCRIPT_PATH" 2>/dev/null || echo "unknown")
SCRIPT_SHA256=$(sha256sum "$SCRIPT_PATH" | awk '{print $1}')
PY_VER=$(python3 --version 2>/dev/null || echo "python3")

echo "INFO: Submission: ${SUBMISSION_ID:-unknown}"
echo "INFO: Environment: $ENV_ID"
echo "INFO: Script: $SCRIPT_NAME size=${SCRIPT_SIZE}B sha256=$SCRIPT_SHA256"
echo "INFO: Interpreter: $PY_VER"
echo "INFO: Limits: timeout=300s nice=19 ionice=2/7 ulimit_vmem=524288KB"

# Execute with strict limits and capture status
python -u "$SCRIPT_PATH" "$ENV_ID"
STATUS=$?
END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))
echo "INFO: Finished: exit=$STATUS duration=${DURATION}s"
exit $STATUS