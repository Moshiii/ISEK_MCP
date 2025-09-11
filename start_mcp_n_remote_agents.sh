#!/usr/bin/env bash
# Quick reference script: one-line commands to launch each component
# Agents can be started on the same or remote machines.  Copy the desired line
# to your terminal/SSH session and execute.

# OpenAI agent (port 9999)
python openai_agent.py &

# Trending agent (port 10020)
python trending_agent.py &

# Analyzer agent (port 10021)
python analyzer_agent.py &

# MCP server (SSE transport on :8080)
python mcp_server.py --host 127.0.0.1 --port 8080 --transport sse &

# kill port 8080, 9999, 10020, 10021 in one command
# kill $(lsof -t -i:8080,9999,10020,10021)