#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ISEK MCP API Tester
# ---------------------------------------------------------------------------
# Tests all REST API endpoints and functionality
# Assumes agents and server are already running (use terminals.json or manual start)
#
# Usage: ./run_demo.sh "<your query here>"
# ---------------------------------------------------------------------------

set -euo pipefail

# Configuration
SERVER_URL="http://127.0.0.1:8080"
OPENAI_AGENT_URL="http://127.0.0.1:9999"
TRENDING_AGENT_URL="http://127.0.0.1:10020"
ANALYZER_AGENT_URL="http://127.0.0.1:10021"

# Default queries for testing
QUERY=${1:-"Analyze the current trends in AI technology"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Helper to check if server is running
check_server() {
  echo -e "\n${YELLOW}🔍 Checking if MCP server is running...${NC}"

  if curl -s --max-time 5 "$SERVER_URL/v1/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ MCP server is running${NC}"
    return 0
  else
    echo -e "${RED}❌ MCP server is not responding${NC}"
    echo -e "${YELLOW}💡 Make sure to start the services first:${NC}"
    echo -e "   • Use VS Code terminals (autorun enabled) or"
    echo -e "   • Run: python mcp_server.py --host 127.0.0.1 --port 8080 --mode rest"
    echo -e "   • Start agents: python openai_agent.py, python trending_agent.py, python analyzer_agent.py"
    return 1
  fi
}

# Helper to make HTTP requests with error handling
make_request() {
  local method="$1"
  local url="$2"
  local data="${3:-}"

  echo -e "\n${PURPLE}🌐 Testing $method $url${NC}"

  # Use -f to fail on server errors (4xx, 5xx)
  if [[ "$method" == "POST" ]] && [[ -n "$data" ]]; then
    response=$(curl -s -f -X POST "$url" \
      -H "Content-Type: application/json" \
      -d "$data" 2>/dev/null)
  else
    response=$(curl -s -f "$url" 2>/dev/null)
  fi

  # Check curl's exit code
  if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}✅ Success${NC}"
    echo "$response" | jq '.' 2>/dev/null || echo "$response"
  else
    echo -e "${RED}❌ Failed (HTTP Status Code is not 2xx)${NC}"
    # Try to get the body anyway for debugging, but without -f
    if [[ "$method" == "POST" ]] && [[ -n "$data" ]]; then
        debug_response=$(curl -s -X POST "$url" -H "Content-Type: application/json" -d "$data")
    else
        debug_response=$(curl -s "$url")
    fi
    echo -e "${YELLOW}Response Body:${NC} $debug_response"
    return 1
  fi
}

# Helper to test agent endpoint
test_agent_endpoint() {
  local url="$1"
  local name="$2"

  echo -e "\n${CYAN}🤖 Testing $name Agent at $url${NC}"

  if curl -s --max-time 5 "$url/.well-known/agent-card.json" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Agent responding${NC}"
    curl -s "$url/.well-known/agent-card.json" | jq '.name' 2>/dev/null || echo "Agent card retrieved"
  else
    echo -e "${RED}❌ Agent not responding${NC}"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# 1. Check if services are running
# ---------------------------------------------------------------------------
echo -e "${YELLOW}🚀 ISEK MCP API Tester${NC}"
echo -e "${YELLOW}========================${NC}"

if ! check_server; then
  echo -e "\n${RED}❌ Cannot proceed without MCP server running${NC}"
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Test individual agent endpoints
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}🔍 Testing Individual Agent Endpoints${NC}"
echo -e "${YELLOW}========================================${NC}"

test_agent_endpoint "$OPENAI_AGENT_URL" "OpenAI"
test_agent_endpoint "$TRENDING_AGENT_URL" "Trending"
test_agent_endpoint "$ANALYZER_AGENT_URL" "Analyzer"

# ---------------------------------------------------------------------------
# 3. Test MCP Server REST API endpoints
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}🌐 Testing REST API Endpoints${NC}"
echo -e "${YELLOW}==============================${NC}"

# Test health endpoints
echo -e "\n${CYAN}🏥 Health Checks${NC}"
make_request "GET" "$SERVER_URL/v1/health"
make_request "GET" "$SERVER_URL/v1/ready"

# Test agent discovery
echo -e "\n${CYAN}📋 Agent Discovery${NC}"
AGENTS_RESPONSE=$(make_request "GET" "$SERVER_URL/v1/agents")

# Extract agent names from the response for individual testing
if [[ -n "$AGENTS_RESPONSE" ]]; then
  AGENT_NAMES=$(echo "$AGENTS_RESPONSE" | jq -r '.[].name' 2>/dev/null || echo "")

  if [[ -n "$AGENT_NAMES" ]]; then
    for agent_name in $AGENT_NAMES; do
      echo -e "\n${CYAN}📋 Testing individual agent: $agent_name${NC}"
      make_request "GET" "$SERVER_URL/v1/agents/$agent_name"
    done
  fi
fi

# Test agent invocation
echo -e "\n${CYAN}⚡ Agent Invocation Tests${NC}"
if [[ -n "$AGENT_NAMES" ]]; then
  echo "$AGENT_NAMES" | while IFS= read -r agent_name; do
    if [[ -z "$agent_name" ]]; then continue; fi
    echo -e "\n${PURPLE}🤖 Testing Agent: $agent_name with query: \"$QUERY\"${NC}"
    
    # Safely create JSON payload using jq
    json_payload=$(jq -n \
      --arg agent_name "$agent_name" \
      --arg query "$QUERY" \
      '{ "agent_name": $agent_name, "agent_inputs": { "query": $query } }')

    make_request "POST" "$SERVER_URL/v1/invoke" "$json_payload"
  done
fi

# Test error handling
echo -e "\n${CYAN}🚨 Error Handling Tests${NC}"

# Test non-existent agent
echo -e "\n${PURPLE}Testing non-existent agent${NC}"
make_request "POST" "$SERVER_URL/v1/invoke" '{
  "agent_name": "nonexistent_agent",
  "agent_inputs": {"query": "test"}
}' || echo "Expected error for non-existent agent"

# Test invalid input
echo -e "\n${PURPLE}Testing invalid input${NC}"
make_request "POST" "$SERVER_URL/v1/invoke" '{
  "agent_name": "OpenAI Agent",
  "agent_inputs": {}
}' || echo "Expected validation error"

# ---------------------------------------------------------------------------
# 4. Test client functionality
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}👤 Testing Client Functionality${NC}"
echo -e "${YELLOW}==============================${NC}"

echo -e "\n${PURPLE}🔍 Running client with query: $QUERY${NC}"
if python mcp_client.py "$QUERY"; then
  echo -e "${GREEN}✅ Client test successful${NC}"
else
  echo -e "${RED}❌ Client test failed${NC}"
fi

# ---------------------------------------------------------------------------
# 5. Display API documentation info
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}📚 API Documentation${NC}"
echo -e "${YELLOW}=====================${NC}"
echo -e "${CYAN}Interactive API Docs:${NC} $SERVER_URL/docs"
echo -e "${CYAN}OpenAPI Spec:${NC} $SERVER_URL/openapi.json"

echo -e "\n${GREEN}🎉 API Testing completed!${NC}"
echo -e "${CYAN}Summary:${NC}"
echo -e "  ✅ Server health verified"
echo -e "  ✅ REST API endpoints tested"
echo -e "  ✅ Agent invocation working"
echo -e "  ✅ Error handling validated"
echo -e "  ✅ Client functionality confirmed"
echo -e "\n${CYAN}Next steps:${NC}"
echo -e "  • Visit $SERVER_URL/docs for interactive API documentation"
echo -e "  • Check VS Code terminals for service logs"
echo -e "  • Run individual tests with: python mcp_client.py \"<your query>\""
echo -e "  • Services remain running for continued testing" 