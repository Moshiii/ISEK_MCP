#!/usr/bin/env bash
# Quick reference script: one-line commands to launch each component
# Agents can be started on the same or remote machines.  Copy the desired line
# to your terminal/SSH session and execute.
#
# Usage: ./start_mcp_n_remote_agents.sh
# Press Ctrl+C to stop all processes

set -e

# Array to store background process IDs
PIDS=()

# Function to kill all background processes
cleanup() {
    echo ""
    echo "Shutting down all processes..."
    
    # Kill all tracked processes
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "Killing process $pid"
            kill "$pid" 2>/dev/null || true
        fi
    done
    
    # Also kill any processes on the ports (in case some didn't get tracked)
    echo "Cleaning up ports..."
    PORT_PIDS=$(lsof -ti:8080,9999,10020,10021 2>/dev/null || true)
    if [ -n "$PORT_PIDS" ]; then
        echo "$PORT_PIDS" | xargs kill -9 2>/dev/null || true
    fi
    
    echo "All processes stopped."
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM EXIT

# Change to script directory
cd "$(dirname "$0")"

echo "Starting ISEK MCP agents and server..."
echo "Press Ctrl+C to stop all processes"
echo ""

# OpenAI agent (port 9999)
echo "Starting OpenAI agent (port 9999)..."
python openai_agent.py &
PIDS+=($!)

# Trending agent (port 10020)
echo "Starting Trending agent (port 10020)..."
python trending_agent.py &
PIDS+=($!)

# Analyzer agent (port 10021)
echo "Starting Analyzer agent (port 10021)..."
python analyzer_agent.py &
PIDS+=($!)

# MCP server (REST API mode on :8080)
echo "Starting MCP server (port 8080)..."
python mcp_server.py --host 127.0.0.1 --port 8080 &
PIDS+=($!)

echo ""
echo "All processes started!"
echo "PIDs: ${PIDS[*]}"
echo ""
echo "Services available at:"
echo "  - MCP Server: http://127.0.0.1:8080"
echo "  - API Docs: http://127.0.0.1:8080/docs"
echo "  - OpenAI Agent: http://127.0.0.1:9999"
echo "  - Trending Agent: http://127.0.0.1:10020"
echo "  - Analyzer Agent: http://127.0.0.1:10021"
echo ""
echo "Press Ctrl+C to stop all processes..."

# Wait for all background processes
# This keeps the script running so it can catch Ctrl+C
wait