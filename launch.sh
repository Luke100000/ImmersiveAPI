#!/bin/bash

# Default values
WORKER_COUNT_DEFAULT=4
PRIMARY_PROCESS_WORKER_PORT_DEFAULT=8000
SINGLE_PROCESS_WORKER_PORT_DEFAULT=8001

# Parse arguments
while [[ $# -gt 0 ]]
do
    key="$1"
    case $key in
        --workers)
        WORKER_COUNT="$2"
        shift
        ;;
        --port)
        PRIMARY_PROCESS_WORKER_PORT="$2"
        shift
        ;;
        --secondary-port)
        SINGLE_PROCESS_WORKER_PORT="$2"
        shift
        ;;
        *)
        echo "Unknown option: $1"
        exit 1
        ;;
    esac
    shift
done

# Set defaults if not provided
export WORKER_COUNT=${WORKER_COUNT:-$WORKER_COUNT_DEFAULT}
export PRIMARY_PROCESS_WORKER_PORT=${PRIMARY_PROCESS_WORKER_PORT:-$PRIMARY_PROCESS_WORKER_PORT_DEFAULT}
export SINGLE_PROCESS_WORKER_PORT=${SINGLE_PROCESS_WORKER_PORT:-$SINGLE_PROCESS_WORKER_PORT_DEFAULT}

# Launch single process worker (if primary isn't already a single process worker)
if [ "$WORKER_COUNT" -ne 1 ]; then
    uvicorn main:app --port "$SINGLE_PROCESS_WORKER_PORT" --workers 1 &
fi

# Launch primary process worker
uvicorn main:app --port "$PRIMARY_PROCESS_WORKER_PORT" --workers "$WORKER_COUNT"
