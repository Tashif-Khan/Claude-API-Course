import sys
import asyncio
from typing import Optional, Any
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

import json
from pydantic import AnyUrl


class MCPClient:
    # Stores how to launch the server, but doesn't start anything yet. The actual
    # connection happens in connect(), so creating this object is always cheap and safe.
    def __init__(
        self,
        command: str,
        args: list[str],
        env: Optional[dict] = None,
    ):
        # The command line used to spawn the server, e.g. "uv" + ["run", "mcp_server.py"].
        self._command = command
        self._args = args
        self._env = env
        # Set once connect() succeeds; every request below goes through it.
        self._session: Optional[ClientSession] = None
        # Tracks the subprocess and the session so cleanup() can close both, in the
        # right order, even if an error is raised partway through.
        self._exit_stack: AsyncExitStack = AsyncExitStack()

    # Launches the MCP server as a child process and completes the MCP handshake.
    async def connect(self):
        # Describes the process to spawn. Nothing runs until stdio_client uses this.
        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env,
        )
        # Actually starts the server process and hands back its stdin/stdout pipes.
        # stdio transport = we talk to the server by writing to the pipes between us.
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        _stdio, _write = stdio_transport
        # Wraps those raw pipes in a session that speaks MCP (JSON-RPC) for us.
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(_stdio, _write)
        )
        # The handshake: agree on protocol version and exchange capabilities.
        # Nothing else below will work until this has run.
        await self._session.initialize()

    # Returns the live session, failing loudly if connect() was never awaited.
    def session(self) -> ClientSession:
        if self._session is None:
            raise ConnectionError(
                "Client session not initialized or cache not populated. Call connect_to_server first."
            )
        return self._session

    # TODO completed
    # Asks the server which tools it offers. Each Tool carries a name, description,
    # and JSON schema, which is exactly what Claude needs to decide when to call it.
    async def list_tools(self) -> list[types.Tool]:
        result = await self.session().list_tools()
        return result.tools

    # TODO completed
    # Runs one tool on the server by name and hands back its raw result.
    # tool_input is a plain dict matching that tool's input schema.
    async def call_tool(
        self, tool_name: str, tool_input
    ) -> types.CallToolResult | None:
        return await self.session().call_tool(tool_name, tool_input)

    # TODO completed
    # Asks the server which prompts it offers. These are the pre-written templates a
    # user picks deliberately, typically surfaced as slash commands in the UI.
    async def list_prompts(self) -> list[types.Prompt]:
        result = await self.session().list_prompts()
        return result.prompts

    # TODO completed
    # Fills in one prompt template with the given args and returns the resulting
    # messages, ready to be sent straight into a conversation with Claude.
    async def get_prompt(self, prompt_name, args: dict[str, str]):
        result = await self.session().get_prompt(prompt_name, args)
        return result.messages

    # TODO completed
    # Fetches a resource by URI and unwraps it into an ordinary Python value.
    # Resources are read-only data the client asks for, unlike tools the model calls.
    async def read_resource(self, uri: str) -> Any:
        # AnyUrl validates the string is a real URI, e.g. "docs://documents".
        result = await self.session().read_resource(AnyUrl(uri))
        # A resource can technically return several parts; we only use the first.
        resource = result.contents[0]

        # Skip anything binary; we only know how to handle text here.
        if isinstance(resource, types.TextResourceContents):
            # The server labels its own content type, so trust it and decode JSON
            # into a real list/dict instead of returning a string that looks like JSON.
            if resource.mimeType == "application/json":
                return json.loads(resource.text)

            return resource.text

    # Shuts down the session and kills the server subprocess.
    async def cleanup(self):
        # Unwinds everything registered on the stack in reverse order.
        await self._exit_stack.aclose()
        self._session = None

    # These two make the class usable with 'async with', so the server is always
    # started on entry and always shut down on exit, even if the body raises.
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()


# For testing
# Spins up mcp_server.py as a subprocess and connects to it. The body is empty, so
# right now this only proves the connection and handshake work; add calls to
# _client.list_tools(), call_tool(), read_resource(), etc. to actually exercise it.
async def main():
    async with MCPClient(
        # If using Python without UV, update command to 'python' and remove "run" from args.
        command="uv",
        args=["run", "mcp_server.py"],
    ) as _client:
        result = await _client.list_tools()
        print("\n Here are your tools: \n" + "\n".join([f"  - {tool.name}: {tool.description}" for tool in result]))


if __name__ == "__main__":
    # Windows needs the Proactor event loop for asyncio to manage subprocess pipes,
    # which is exactly what the stdio transport depends on. Without this, connect() fails.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
