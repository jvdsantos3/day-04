"""Entry point for ``python -m mcp_servers.finance`` (stdio transport).

This is the exact command ``MultiServerMCPClient`` spawns per design.md's
``langchain-mcp-adapters`` config.
"""

from mcp_servers.finance.server import mcp

if __name__ == "__main__":
    mcp.run()
