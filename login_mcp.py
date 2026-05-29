import asyncio

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


def print_content(result):
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                print(item.text)
            else:
                print(item)
    else:
        print(result)


async def main():
    server_params = StdioServerParameters(
        command="npx", args=["mcp-remote", "https://mcp.kite.trade/mcp"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            print("\nInitializing MCP...")
            await session.initialize()

            print("\nCalling login tool...")
            login_result = await session.call_tool("login", {})

            print("\nLOGIN RESPONSE:")
            print("-" * 80)
            print_content(login_result)
            print("-" * 80)

            input(
                "\nComplete Zerodha login in your browser.\n"
                "After successful login, press ENTER..."
            )

            print("\nFetching profile...")

            profile_result = await session.call_tool("get_profile", {})

            print("\nPROFILE:")
            print("-" * 80)
            print("isError:", profile_result.isError)
            print_content(profile_result)

            print("\nFetching holdings...")

            holdings_result = await session.call_tool("get_holdings", {})

            print("\nHOLDINGS:")
            print("-" * 80)
            print("isError:", holdings_result.isError)
            print_content(holdings_result)

            print("\nFetching positions...")

            positions_result = await session.call_tool("get_positions", {})

            print("\nPOSITIONS:")
            print("-" * 80)
            print("isError:", positions_result.isError)
            print_content(positions_result)

            print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
import asyncio

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


def print_content(result):
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                print(item.text)
            else:
                print(item)
    else:
        print(result)


async def main():
    server_params = StdioServerParameters(
        command="npx", args=["mcp-remote", "https://mcp.kite.trade/mcp"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            print("\nInitializing MCP...")
            await session.initialize()

            print("\nCalling login tool...")
            login_result = await session.call_tool("login", {})

            print("\nLOGIN RESPONSE:")
            print("-" * 80)
            print_content(login_result)
            print("-" * 80)

            input(
                "\nComplete Zerodha login in your browser.\n"
                "After successful login, press ENTER..."
            )

            print("\nFetching profile...")

            profile_result = await session.call_tool("get_profile", {})

            print("\nPROFILE:")
            print("-" * 80)
            print("isError:", profile_result.isError)
            print_content(profile_result)

            print("\nFetching holdings...")

            holdings_result = await session.call_tool("get_holdings", {})

            print("\nHOLDINGS:")
            print("-" * 80)
            print("isError:", holdings_result.isError)
            print_content(holdings_result)

            print("\nFetching positions...")

            positions_result = await session.call_tool("get_positions", {})

            print("\nPOSITIONS:")
            print("-" * 80)
            print("isError:", positions_result.isError)
            print_content(positions_result)

            print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
