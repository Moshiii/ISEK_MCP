#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Demo launcher
# ---------------------------------------------------------------------------
# Starts all local demo agents, the MCP server, runs a query via the client, and
# finally cleans everything up.
#
# Usage: ./run_demo.sh "<your query here>"
# ---------------------------------------------------------------------------

set -euo pipefail

# QUERY=${1:-"explain what an image-classifier agent can do?"}
QUERY=${1:-"show me the trending topic for last week"}

# Helper to start a command in the background and log its output.
start_bg() {
  local cmd="$1"   # Command to run
  local log="$2"   # Logfile

  echo "➜ Starting: $cmd (logs → $log)"
  # shellcheck disable=SC2086 # we want word-splitting of $cmd
  nohup $cmd > "$log" 2>&1 &
  local pid=$!
  echo "    PID: $pid"
  echo $pid
}

PIDS=()

# ---------------------------------------------------------------------------
# 1. Spin up the three demo agents
# ---------------------------------------------------------------------------
PIDS+=( "$(start_bg "python openai_agent.py" "openai_agent.log")" )
PIDS+=( "$(start_bg "python trending_agent.py" "trending_agent.log")" )
PIDS+=( "$(start_bg "python analyzer_agent.py" "analyzer_agent.log")" )
# PIDS+=( "$(start_bg "python mcp_server.py" "mcp_server.log")" )

# run this command: 
# python mcp_server.py --host 127.0.0.1 --port 8080 --transport sse

# PIDS+=( "$(start_bg "python mcp_server.py --host 127.0.0.1 --port 8080 --transport sse" "mcp_server.log")" )

echo "Waiting 5 seconds for agents to start …"
sleep 5

# ---------------------------------------------------------------------------
# 2. Start the MCP server (SSE transport)
# ---------------------------------------------------------------------------
# SERVER_PID=$(start_bg "python mcp_server.py --host 127.0.0.1 --port 8080 --transport sse" "mcp_server.log")
# PIDS+=( "$SERVER_PID" )

# echo "Waiting 5 seconds for MCP server to start …"
# sleep 5

# ---------------------------------------------------------------------------
# 3. Run the client query
# ---------------------------------------------------------------------------
echo "Running client query: $QUERY"
python mcp_client.py "$QUERY"

# ---------------------------------------------------------------------------
# 4. Cleanup
# ---------------------------------------------------------------------------
echo "Stopping background processes …"
kill "${PIDS[@]}" || true
echo "Done." 