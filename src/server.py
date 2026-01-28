# server.py
from mcp.server.fastmcp import FastMCP
import asyncio
import httpx

# Initialize the MCP server
mcp = FastMCP("ecfr_mcp")

# Constants
BASE_URL = "https://www.ecfr.gov/api"
TIMEOUT = 30.0

TEST_TITLE = 1  

# Helper Functions
async def make_api_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make an HTTP request to the eCFR API."""
    url = f"{BASE_URL}/{endpoint}"
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Resource not found: {endpoint}")
            elif e.response.status_code == 429:
                raise ValueError("Rate limit exceeded. Please wait before making more requests.")
            elif e.response.status_code == 405:
                raise ValueError("Invalid input.")
            else:
                raise ValueError(f"API request failed with status {e.response.status_code}")
        except httpx.TimeoutException:
            raise ValueError("Request timed out. Please try again.")
        except Exception as e:
            raise ValueError(f"Unexpected error: {str(e)}")
        
# MCP Tools
@mcp.tool()
async def get_latest_version(params: TEST_TITLE) -> str:
    """Get the latest published version information for a CFR title or specific part.
    
    Returns current version metadata including the publication date, amendment status,
    and currency information - essential for compliance verification.
    
    Args:
        params (GetLatestVersionInput): Parameters containing:
            - title: CFR title number (1-50)
            - part: Optional specific part number
            - response_format: Output format (markdown or json)
    
    Returns:
        str: Latest version information in requested format
    """
    try:
        data = await make_api_request(f"versioner/v1/versions/title-{TEST_TITLE}")
        
        # Find the requested title
        title_info = None
        for title in data.get('content_versions', []):
            if title.get('title') == params.title:
                title_info = title
                break
        
        if not title_info:
            return f"Error: Title {params.title} not found"
 
        return title_info
    
    except Exception as e:
        return f"Error retrieving latest version: {str(e)}"
    
# Main execution block - this is required to run the server
if __name__ == "__main__":
    # Run with stdio transport (default for local MCP servers)
    mcp.run()