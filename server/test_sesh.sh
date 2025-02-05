#!/bin/bash

# Set default port or use PORT environment variable if provided
PORT=${PORT:-4999}

# Create a new session and store the response
echo "Creating new session..."
RESPONSE=$(curl -s -X POST http://localhost:$PORT/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "aegnt nae",
    "model": "claude",
    "research_tools": ["CoinGecko", "Twitter", "CoinMarketCap"],
    "system_prompt": "system prompt",
    "agent_id": "8c065b88-8858-4459-acc4-d7df38f44f08"
  }')

# Extract the sessionId from the response using grep and cut
SESSION_ID=$(echo $RESPONSE | grep -o '"sessionId":"[^"]*"' | cut -d'"' -f4)

echo "Session ID: $SESSION_ID"

# Wait for 1 second
sleep 1

# Check the session status
echo "Checking session status..."
curl -s "http://localhost:$PORT/sessions/$SESSION_ID" | json_pp

# Wait for 1 second
sleep 5

# Start monitoring session events
echo -e "\nMonitoring logs ..."
curl -N "http://localhost:$PORT/sessions/$SESSION_ID/logs"

# Start monitoring session events
echo -e "\nMonitoring session events..."
curl -N "http://localhost:$PORT/sessions/$SESSION_ID/events"