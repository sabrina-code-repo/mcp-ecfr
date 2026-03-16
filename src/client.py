#!/usr/bin/env python3
"""
Clean MCP Client for the local eCFR MCP server, with a direct tool call mode.

Features:
- Connect to a local MCP stdio server and initialize the session.
- List tools and run a small demo when no explicit tool call is requested.
- Call a specific tool with --call and --args; prints the full tool output.

Argument contract:
- Server tool schemas require a top-level "params" object.
- The --args flag supplies the inner params payload; the client wraps it as {"params": <args>}.

Examples:
- python client.py --server server.py
- python client.py --server server.py --call ecfr_list_titles --args "{}"
- python client.py --server server.py --call ecfr_search --args '{"query":"informed consent","per_page":3,"page":1}'
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

# Configure logging for visibility into connection and tool calls
logging.basicConfig(level=logging.INFO)
# Create module logger for consistent structured logs
logger = logging.getLogger(__name__)


def _extract_text_from_tool_result(result: Any) -> Optional[str]:
    # Return None when tool result is missing
    if result is None:
        # Indicate no text could be extracted
        return None
    # Return None when content is missing
    if not getattr(result, "content", None):
        # Indicate no text could be extracted
        return None
    # Find the first TextContent block in the tool result content list
    text_block = next((c for c in result.content if isinstance(c, TextContent)), None)
    # Return None when no TextContent block exists
    if text_block is None:
        # Indicate no text could be extracted
        return None
    # Return the text payload
    return text_block.text


def _load_agent_prompt(agent_prompt_path: Path) -> str:
    # Return empty string when file does not exist
    if not agent_prompt_path.exists():
        # Provide empty prompt content
        return ""
    # Read markdown as UTF-8 text
    return agent_prompt_path.read_text(encoding="utf-8")


async def _list_tools(session: ClientSession) -> Dict[str, Any]:
    # Request the server tool list
    tools = await session.list_tools()
    # Convert to JSON-serializable dict form when possible
    tools_dict = tools.model_dump() if hasattr(tools, "model_dump") else json.loads(tools.json())
    # Return the tool list as dict
    return tools_dict


async def _call_tool_raw(session: ClientSession, name: str, params_payload: Dict[str, Any]) -> Any:
    # Wrap the inner params payload to match server input schema
    arguments = {"params": params_payload}
    # Call the tool with the expected argument envelope
    result = await session.call_tool(name, arguments=arguments)
    # Return the raw tool result object
    return result


async def _call_tool_json(session: ClientSession, name: str, params_payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    # Call the tool and get the raw result
    result = await _call_tool_raw(session, name, params_payload)
    # Extract the first text block, expected to be JSON
    text = _extract_text_from_tool_result(result)
    # Return error string when no text was returned
    if text is None:
        # Provide a helpful error payload
        return None, f"Tool '{name}' returned no TextContent"
    # Attempt to parse tool text as JSON
    try:
        # Parse JSON text into a dict
        payload = json.loads(text)
    except Exception as exc:
        # Return parsing failure as error with a small preview for debugging
        preview = text[:200]
        # Return error details
        return None, f"Tool '{name}' returned non-JSON text: {exc}; preview={preview!r}"
    # Return parsed payload and no error
    return payload, None


async def _run_demo(session: ClientSession, agent_prompt_path: Path) -> None:
    # Load the agent prompt file for demonstration
    agent_prompt = _load_agent_prompt(agent_prompt_path)
    # Log the agent prompt size for quick verification
    logger.info("Loaded AGENT_PROMPT.md characters=%s", len(agent_prompt))

    # List tools for capability discovery
    logger.info("Listing tools")
    tools = await _list_tools(session)
    # Print tools to stdout in readable form
    print("\nAvailable tools:\n" + json.dumps(tools, indent=2, ensure_ascii=False))

    # Collect tool names from the tool list payload
    tool_names = [t.get("name") for t in tools.get("tools", []) if isinstance(t, dict)]

    # Call ecfr_list_titles if present
    if "ecfr_list_titles" in tool_names:
        # Log the planned test call
        logger.info("Testing tool ecfr_list_titles")
        # Call the tool with an empty params payload
        titles_payload, err = await _call_tool_json(session, "ecfr_list_titles", {})
        # Print error when call failed
        if err:
            # Surface the tool failure
            print("\necfr_list_titles error:", err)
        else:
            # Extract titles list when present
            titles = titles_payload.get("titles") if isinstance(titles_payload, dict) else None
            # Display count when available
            if isinstance(titles, list):
                # Print titles count
                print(f"\necfr_list_titles: {len(titles)} titles returned")
            else:
                # Print raw payload when shape differs
                print("\necfr_list_titles payload:\n" + json.dumps(titles_payload, indent=2, ensure_ascii=False))
    else:
        # Explain missing tool in output
        print("\nTool ecfr_list_titles not found; skipping demo call")

    # Call ecfr_search if present
    if "ecfr_search" in tool_names:
        # Log the planned test call
        logger.info("Testing tool ecfr_search")
        # Build a small search request
        search_params = {"query": "informed consent", "per_page": 3, "page": 1}
        # Call search tool and parse JSON
        search_payload, err = await _call_tool_json(session, "ecfr_search", search_params)
        # Print error when call failed
        if err:
            # Surface the tool failure
            print("\necfr_search error:", err)
        else:
            # Compute a compact summary when possible
            results = search_payload.get("results") if isinstance(search_payload, dict) else None
            # Print results count when available
            if isinstance(results, list):
                # Print result count
                print(f"\necfr_search: {len(results)} results returned for query='informed consent'")
            else:
                # Print raw payload when shape differs
                print("\necfr_search payload:\n" + json.dumps(search_payload, indent=2, ensure_ascii=False))
    else:
        # Explain missing tool in output
        print("\nTool ecfr_search not found; skipping demo call")


async def _run_single_tool_call(session: ClientSession, tool_name: str, args_json: str) -> int:
    # Parse the args JSON string into a dict
    try:
        # Parse args JSON to params payload
        params_payload = json.loads(args_json)
    except Exception as exc:
        # Print a clear parse error message
        print(f"Failed to parse --args JSON: {exc}")
        # Return non-zero exit code
        return 2

    # Ensure params payload is an object
    if not isinstance(params_payload, dict):
        # Print a clear type error message
        print("The --args value must decode to a JSON object")
        # Return non-zero exit code
        return 2

    # Call the tool and parse JSON when possible
    payload, err = await _call_tool_json(session, tool_name, params_payload)
    # Print error when tool call failed
    if err:
        # Print a structured error object
        print(json.dumps({"tool": tool_name, "error": err}, indent=2, ensure_ascii=False))
        # Return non-zero exit code
        return 1

    # Print full JSON payload
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    # Return success exit code
    return 0


async def _connect(server_command: str, server_args: Sequence[str]) -> Tuple[Any, Any, ClientSession]:
    # Build stdio server parameters for MCP
    server_params = StdioServerParameters(command=server_command, args=list(server_args))
    # Open stdio pipes to the server process
    cm_stdio = stdio_client(server_params)
    # Enter the stdio context manager
    reader, writer = await cm_stdio.__aenter__()
    # Create an MCP client session over the pipes
    cm_session = ClientSession(reader, writer)
    # Enter the session context manager
    session = await cm_session.__aenter__()
    # Initialize the MCP session
    await session.initialize()
    # Return context managers and session for controlled teardown
    return cm_stdio, cm_session, session


async def _disconnect(cm_stdio: Any, cm_session: Any) -> None:
    # Exit the session context manager
    await cm_session.__aexit__(None, None, None)
    # Exit the stdio context manager
    await cm_stdio.__aexit__(None, None, None)


def _build_parser() -> argparse.ArgumentParser:
    # Create CLI parser
    parser = argparse.ArgumentParser(prog="client.py", description="Clean MCP stdio client for the local eCFR MCP server")
    # Add server file path argument
    parser.add_argument("--server", default="server.py", help="Path to MCP server Python file")
    # Add agent prompt path argument
    parser.add_argument("--agent-prompt", default="AGENT_PROMPT.md", help="Path to agent prompt markdown file")
    # Add optional override for python executable
    parser.add_argument("--python", default=sys.executable, help="Python executable to run the server with")
    # Add tool call name option
    parser.add_argument("--call", default=None, help="Tool name to call; prints full JSON output")
    # Add JSON args option for tool call
    parser.add_argument("--args", default="{}", help="JSON string for tool params payload")
    # Return parser
    return parser


async def main() -> None:
    # Build argument parser
    parser = _build_parser()
    # Parse arguments
    args = parser.parse_args()

    # Resolve server path
    server_path = Path(args.server).resolve()
    # Resolve agent prompt path
    agent_prompt_path = Path(args.agent_prompt).resolve()

    # Fail fast when server file is missing
    if not server_path.exists():
        # Raise a file error with a clear message
        raise FileNotFoundError(f"Server file not found: {server_path}")

    # Build args for python server invocation
    server_args = [str(server_path)]

    # Log connection attempt
    logger.info("Connecting to server via stdio: %s %s", args.python, server_args)

    # Wrap the whole run in an exception boundary for clean logs
    try:
        # Establish MCP session
        cm_stdio, cm_session, session = await _connect(args.python, server_args)

        # Ensure teardown always happens
        try:
            # Run a single tool call when requested
            if args.call:
                # Run the direct tool call path and exit
                code = await _run_single_tool_call(session, args.call, args.args)
                # Exit with the tool call status code
                raise SystemExit(code)

            # Run demo behavior when no tool call is specified
            await _run_demo(session, agent_prompt_path)
        finally:
            # Disconnect session and stdio pipes
            await _disconnect(cm_stdio, cm_session)

    except SystemExit:
        # Re-raise clean exits
        raise
    except Exception:
        # Log full stack trace for debugging
        logger.exception("Client run failed")
        # Exit with non-zero code to signal failure in CI or scripts
        raise SystemExit(1)


if __name__ == "__main__":
    # Run the async main entrypoint
    asyncio.run(main())
