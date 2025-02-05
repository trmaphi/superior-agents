#!/bin/bash

# Set default port or use PORT environment variable if provided
PORT=${PORT:-4999}

# Create a new session and store the response
echo "Creating new session..."
RESPONSE=$(curl -s -X POST http://localhost:$PORT/sessions)

# Extract the sessionId from the response using grep and cut
SESSION_ID=$(echo $RESPONSE | grep -o '"sessionId":"[^"]*"' | cut -d'"' -f4)

echo "Session ID: $SESSION_ID"

# Wait for 1 second
sleep 1

# Check the session status
echo "Checking session status..."
curl -s "http://localhost:$PORT/sessions/$SESSION_ID" | json_pp

# Start monitoring session events
echo -e "\nMonitoring session events..."
curl -N "http://localhost:$PORT/sessions/$SESSION_ID/events"