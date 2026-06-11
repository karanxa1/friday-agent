from mcp.server.fastmcp import FastMCP
mcp = FastMCP('gen')
@mcp.tool()
def ping() -> str:
    return 'pong'
if __name__ == '__main__':
    mcp.run()
