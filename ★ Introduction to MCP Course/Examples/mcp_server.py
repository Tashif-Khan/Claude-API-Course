# =============================================================================
# mcp_server.py - A minimal MCP server for working with a set of documents.
#
# WHAT AN MCP SERVER IS
#   An MCP server doesn't do anything on its own. It's a program that sits and
#   waits for an MCP *client* (Claude Desktop, the MCP Inspector, mcp_client.py)
#   to connect and ask it for things. Think of it as a vending machine: it has
#   stock on the shelves, but nothing happens until a customer walks up.
#
# WHAT THIS SERVER EXPOSES
#   MCP has three kinds of things a server can offer, and this file has all three:
#
#   1. TOOLS      - Actions the AI can choose to run on its own.
#                     * read_doc_contents - returns a document's text
#                     * edit_document     - find-and-replace inside a document
#
#   2. RESOURCES  - Read-only data the client fetches by URI, like a GET request.
#                   The AI doesn't pick these; the client asks for them.
#                     * docs://documents          - list every document id
#                     * docs://documents/{doc_id} - one document's contents
#
#   3. PROMPTS    - Pre-written instructions a user deliberately triggers,
#                   usually from a slash-command menu in the client.
#                     * format    - rewrite a document as Markdown
#                     * summarize - condense a document
#
#   The rough split: tools are for the AI, resources are for the client,
#   prompts are for the human.
#
# WHERE THE DATA LIVES
#   In the `docs` dictionary below - plain in-memory Python. Edits last only as
#   long as the process runs, and everything resets on restart. A real server
#   would read from a database or the file system here.
#
# HOW TO RUN IT
#   From this Examples/ folder (the one holding pyproject.toml):
#
#     uv run mcp dev mcp_server.py    <- runs it WITH the Inspector web UI
#     uv run mcp run mcp_server.py    <- runs it bare, no UI
#
#   Running it bare looks like nothing happens: no output, no prompt returning.
#   That is correct. The last line uses transport="stdio", meaning the server
#   talks over standard input/output, so it just waits silently for a client.
#   Use `mcp dev` when you want something to actually look at.
# =============================================================================

from mcp.server.fastmcp import FastMCP

# This is a simple example of an MCP SERVER that can read and edit documents. It defines a few tools and resources that can be used by an MCP client to interact with the server. The server uses the FastMCP framework to handle requests and responses.
mcp = FastMCP("DocumentMCP", log_level="ERROR")

# Some test documents that can be read and edited by the MCP server. In a real application, these would be stored in a database or file system.
docs = {
    "deposition.md": "This deposition covers the testimony of Angela Smith, P.E.",
    "report.pdf": "The report details the state of a 20m condenser tower.",
    "financials.docx": "These financials outline the project's budget and expenditures.",
    "outlook.pdf": "This document presents the projected future performance of the system.",
    "plan.md": "The plan outlines the steps for the project's implementation.",
    "spec.txt": "These specifications define the technical requirements for the equipment.",
}

from pydantic import Field
from mcp.server.fastmcp.prompts import base


# TODO completed
# MCP tool that looks up a document by id and returns its raw contents.
@mcp.tool(
    name="read_doc_contents",
    description="Read the contents of a document and return it as a string.",
)
def read_document(
    doc_id: str = Field(description="Id of the document to read"),
):
    if doc_id not in docs:
        raise ValueError(f"Doc with id {doc_id} not found")

    return docs[doc_id]


# MCP tool that finds an exact substring in a document and replaces it with new text.
@mcp.tool(
    name="edit_document",
    description="Edit a document by replacing a string in the documents content with a new string",
)
def edit_document(
    doc_id: str = Field(description="Id of the document that will be edited"),
    old_str: str = Field(
        description="The text to replace. Must match exactly, including whitespace"
    ),
    new_str: str = Field(
        description="The new text to insert in place of the old text"
    ),
):
    if doc_id not in docs:
        raise ValueError(f"Doc with id {doc_id} not found")

    docs[doc_id] = docs[doc_id].replace(old_str, new_str)
    


# TODO completed
# MCP resource that lists the ids of every document available on this server.
@mcp.resource("docs://documents", mime_type="application/json")
def list_docs() -> list[str]:
    return list(docs.keys())


# TODO completed
# MCP resource that returns the contents of a single document, addressed by id in the URI.
@mcp.resource("docs://documents/{doc_id}", mime_type="text/plain")
def fetch_doc(doc_id: str) -> str:
    if doc_id not in docs:
        raise ValueError(f"Doc with id {doc_id} not found")
    return docs[doc_id]


# TODO completed
# Builds a prompt asking Claude to rewrite the given document using Markdown formatting.
@mcp.prompt(
    name="format",
    description="Rewrites the contents of the document in Markdown format.",
)
def format_document(
    doc_id: str = Field(description="Id of the document to format"),
) -> list[base.Message]:
    prompt = f"""
    Your goal is to reformat a document to be written with markdown syntax.

    The id of the document you need to reformat is:
    <document_id>
    {doc_id}
    </document_id>

    Add in headers, bullet points, tables, etc as necessary. Feel free to add in extra text, but don't change the meaning of the report.
    Use the 'edit_document' tool to edit the document. After the document has been edited, respond with the final version of the doc. Don't explain your changes.
    """

    return [base.UserMessage(prompt)]


# TODO completed
# Builds a prompt asking Claude to produce a concise summary of the given document.
@mcp.prompt(
    name="summarize",
    description="Summarizes the contents of the document.",
)
def summarize_document(
    doc_id: str = Field(description="Id of the document to summarize"),
) -> list[base.Message]:
    prompt = f"""
    Your goal is to summarize the contents of a document.

    The id of the document you need to summarize is:
    <document_id>
    {doc_id}
    </document_id>

    Use the 'read_doc_contents' tool to fetch the document's contents before summarizing.
    Keep the summary concise and don't change the meaning of the original document.
    """

    return [base.UserMessage(prompt)]


if __name__ == "__main__":
    mcp.run(transport="stdio")
    
