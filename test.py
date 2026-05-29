import asyncio

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


async def main():
    params = StdioServerParameters(
        command="npx", args=["mcp-remote", "https://mcp.kite.trade/mcp"]
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:

            await session.initialize()

            login_result = await session.call_tool("login", {})

            print("\nLOGIN REQUIRED\n")

            for item in login_result.content:
                print(item.text)

            print("\nWaiting for authentication...\n")

            while True:
                try:
                    profile = await session.call_tool("get_profile", {})

                    if not profile.isError:
                        print("\nLOGIN SUCCESSFUL\n")

                        for item in profile.content:
                            print(item.text)

                        break

                except Exception:
                    pass

                await asyncio.sleep(5)

            holdings = await session.call_tool("get_holdings", {})

            print("\nHOLDINGS\n")

            for item in holdings.content:
                print(item.text)

            positions = await session.call_tool("get_positions", {})

            print("\nPOSITIONS\n")

            for item in positions.content:
                print(item.text)


if __name__ == "__main__":
    asyncio.run(main())
