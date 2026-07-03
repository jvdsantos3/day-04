"""Entry point for ``python -m mcp_servers.chroma`` (stdio transport).

This is the exact command ``MultiServerMCPClient`` spawns per design.md's
``langchain-mcp-adapters`` config.
"""

from mcp_servers.chroma.server import mcp

if __name__ == "__main__":
    mcp.run()
