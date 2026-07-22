---
name: claude-cli-notebook-backend
description: Route a Python notebook or script through the local `claude` CLI instead of the paid Claude API, so it runs on a Claude Pro/Max subscription and consumes no API credits. Use when a notebook fails with a 401 or authentication error from api.anthropic.com, when the user has a Pro plan but zero API credits, when the user asks to run notebook examples "without paying" or "without an API key", or when a teaching notebook needs real Claude answers on an existing subscription. Also covers installing and logging into the claude CLI on Windows. Do NOT use when the user specifically wants to learn the HTTP API itself, needs tool use, needs images, or needs real token-by-token streaming.
---

# Claude CLI notebook backend

## What this solves

Claude Pro/Max subscriptions and the Claude API are **billed separately**. A Pro
plan covers the chat apps only. Notebook code calling `api.anthropic.com` needs
prepaid API credits, and fails with `401 Unauthorized` when the credit balance
is zero.

This skill swaps the `anthropic` package for a shim that shells out to the local
`claude` CLI. The CLI authenticates with the Pro login, so the notebook gets real
Claude answers at no extra cost.

## Scope

Supported: `messages.create()` with `model`, `system`, `stop_sequences`,
`temperature`; `response.content[0].text`; `response.usage.input_tokens` and
`.output_tokens`; multi-turn message lists.

Not supported: tool use, images, prompt caching, real streaming. If the notebook
needs any of these, say so directly and recommend the real API instead. Do not
try to fake them.

## Procedure

### Step 1: Confirm this is the right fix

Check the notebook actually calls the Anthropic SDK (`from anthropic import
Anthropic`). Then confirm the diagnosis rather than assuming:

- Ask the user to check **Console > Settings > API keys** at
  platform.claude.com. A **Last used** of `—` means no call ever succeeded.
- A **Credits** balance of `$0.00` or a plan badge of **Evaluation access**
  confirms the billing cause.

A 401 can also mean a mistyped key. Both point here, but say which one you think
it is and on what evidence.

### Step 2: Check for a mock backend already in the notebook

Some teaching notebooks ship a fake `anthropic` module that returns placeholder
text. Search the notebook's code cells for `sys.modules["anthropic"]`,
`_MockAnthropic`, or a `BACKEND = "mock"` style flag.

If found, tell the user their previous runs were never hitting the network. Do
not layer this shim on top of an active mock. Remove or disable the mock first.

**Verify edits actually landed.** Jupyter edits live in the browser until saved.
Compare the file's mtime against the current time before trusting that a cell
was changed:

```bash
date; stat -c '%y  %n' "notebook.ipynb"
```

If the mtime is older than the user's message, their edits are unsaved. Ask them
to press Ctrl+S, then re-check. Do not proceed on an assumption here.

### Step 3: Install the CLI (Windows)

If `claude --version` reports "not recognized", the CLI is missing. `claude
login` cannot run before it exists.

The installer needs **PowerShell**, not cmd. In VS Code's terminal panel, the
active shell is labelled in the top right; click the **dropdown arrow (˅) next
to the + button** and pick **PowerShell**.

```powershell
irm https://claude.ai/install.ps1 | iex
```

Then close the terminal (trash can icon) and open a new one so PATH refreshes.
Verify with `claude --version`. If it still fails, restart VS Code entirely.

npm alternative, for Node.js 22+: `npm install -g @anthropic-ai/claude-code`.
Never prefix with sudo or run elevated, it causes permission problems later.

Finally: `claude login`, which opens a browser.

### Step 4: Install the shim

Copy `claude_cli_backend.py` (bundled alongside this file) into the notebook's
directory.

Insert a new code cell **before** the cell that constructs the client:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath("claude_cli_backend.py")))

import claude_cli_backend as ccb
ccb.install()      # makes `from anthropic import Anthropic` use the CLI
ccb.selftest()     # confirms CLI installed, logged in, responding
```

Then change the client construction to drop the key:

```python
client = Anthropic()          # was: Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```

Order matters. `ccb.install()` must run before any `from anthropic import ...`.
A `%pip install anthropic` cell earlier in the notebook is harmless, since the
shim overrides `sys.modules` afterward.

Back up the notebook first: `cp nb.ipynb nb.ipynb.bak`.

### Step 5: Verify honestly

Run `ccb.selftest()`. It prints the CLI path, a reply, token counts, and
PASS/FAIL.

**If you are running in a sandbox separate from the user's machine, you cannot
verify the live call.** The CLI must be installed and logged in on *their*
system. Unit-test what you can (model alias mapping, message flattening, stop
sequences, client construction) and state plainly that the end-to-end path is
untested and why. Do not report success you did not observe.

## Known rough edge

Cells that ask for strict JSON and immediately `json.loads` the result can break,
because the CLI is sometimes chattier than the raw API. If that happens, tighten
the prompt or strip markdown fences before parsing.

## Security note

If the project has a `.env`, check it is gitignored and untracked before doing
anything else:

```bash
git ls-files --error-unmatch .env    # any output means the key is tracked
```

If tracked: `git rm --cached .env`, add `.env` to `.gitignore`, and tell the
user. Never print a key value, paste one into chat, or commit one. If a real key
was already committed, say so clearly and tell the user to revoke it in the
Console. That is theirs to do, not yours.
