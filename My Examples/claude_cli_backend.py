"""
claude_cli_backend.py
---------------------
Drop-in replacement for the `anthropic` package that routes calls through the
local `claude` CLI instead of the paid API.

Why: the Claude API bills separately from a Claude Pro subscription. The CLI
uses your Pro plan, so running a notebook through this module costs nothing
extra.

Requirements:
  1. The `claude` CLI installed and on your PATH
  2. `claude login` run once (uses your Pro account)

Usage in a notebook:

    import claude_cli_backend as ccb
    ccb.install()                    # registers a fake `anthropic` module
    from anthropic import Anthropic  # now resolves to the shim
    client = Anthropic()

Supported surface (the parts the teaching notebooks actually use):
    client.messages.create(model=..., max_tokens=..., messages=[...],
                           system=..., temperature=..., stop_sequences=[...])
    response.content[0].text
    response.usage.input_tokens / .output_tokens

Not supported: tool use, images, real token-by-token streaming, prompt caching.
"""

import json
import os
import shutil
import subprocess
import sys
import types

DEFAULT_TIMEOUT = 180

# The CLI takes short aliases. Map the API model IDs the notebooks use onto them
# so you can leave the notebook's model constants alone.
_MODEL_ALIASES = {
    "opus": "opus",
    "sonnet": "sonnet",
    "haiku": "haiku",
}


class ClaudeCLIError(RuntimeError):
    """Raised when the CLI is missing, not logged in, or returns an error."""


def find_cli():
    """Locate the claude executable. Handles Windows .cmd/.exe shims."""
    for name in ("claude", "claude.cmd", "claude.exe", "claude.ps1"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _model_to_alias(model):
    """Turn 'claude-haiku-4-5-20251001' into 'haiku', etc."""
    if not model:
        return "sonnet"
    lowered = str(model).lower()
    for key, alias in _MODEL_ALIASES.items():
        if key in lowered:
            return alias
    return "sonnet"


def _block_to_text(block):
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        return block.get("text", "")
    return str(block)


def _content_to_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_block_to_text(b) for b in content)
    return str(content)


def _flatten(messages):
    """
    The CLI is stateless per invocation, so a multi-turn conversation has to be
    collapsed into one prompt. Role labels keep the turns distinguishable.
    """
    messages = messages or []
    if len(messages) == 1 and messages[0].get("role") == "user":
        return _content_to_text(messages[0].get("content", ""))

    parts = []
    for m in messages:
        role = m.get("role", "user")
        text = _content_to_text(m.get("content", ""))
        label = "Human" if role == "user" else "Assistant"
        parts.append(f"{label}: {text}")
    parts.append("Assistant:")
    return "\n\n".join(parts)


def _apply_stop_sequences(text, stop_sequences):
    """The CLI has no --stop-sequences, so trim client-side to match API behaviour."""
    if not stop_sequences:
        return text
    cut = len(text)
    for s in stop_sequences:
        if s and s in text:
            cut = min(cut, text.index(s))
    return text[:cut]


class _Usage:
    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def __repr__(self):
        return f"Usage(input_tokens={self.input_tokens}, output_tokens={self.output_tokens})"


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text

    def __repr__(self):
        return f"TextBlock(text={self.text[:60]!r}...)"


class _Message:
    def __init__(self, text, model, usage, stop_reason="end_turn"):
        self.id = "msg_cli"
        self.type = "message"
        self.role = "assistant"
        self.model = model
        self.content = [_TextBlock(text)]
        self.usage = usage
        self.stop_reason = stop_reason

    @property
    def text(self):
        return self.content[0].text

    def __repr__(self):
        return f"Message(model={self.model!r}, text={self.content[0].text[:60]!r}...)"


def call_cli(prompt, system=None, model=None, timeout=DEFAULT_TIMEOUT):
    """Run one `claude -p` invocation and return (text, usage_dict)."""
    cli = find_cli()
    if cli is None:
        raise ClaudeCLIError(
            "`claude` CLI not found on PATH.\n"
            "Install it, then run `claude login` once.\n"
            "If you just installed it, restart Jupyter so it picks up the new PATH."
        )

    cmd = [cli, "-p", prompt, "--output-format", "json"]
    alias = _model_to_alias(model)
    if alias:
        cmd += ["--model", alias]
    if system:
        cmd += ["--append-system-prompt", system]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,  # stops the CLI waiting on stdin
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise ClaudeCLIError(f"claude CLI timed out after {timeout}s.")

    raw = (proc.stdout or "").strip()
    if not raw:
        raise ClaudeCLIError(
            f"claude CLI returned nothing (exit {proc.returncode}).\n"
            f"stderr: {(proc.stderr or '').strip()[:400]}"
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Older CLI versions may ignore --output-format and print plain text.
        return raw, {}

    text = payload.get("result", "")
    usage = payload.get("usage", {}) or {}

    if payload.get("is_error"):
        if "not logged in" in str(text).lower():
            raise ClaudeCLIError(
                "claude CLI is not logged in. Run `claude login` in a terminal, "
                "then restart the Jupyter kernel."
            )
        raise ClaudeCLIError(f"claude CLI error: {text}")

    return text, usage


class _Messages:
    def create(self, *, model=None, max_tokens=1024, messages=None, system=None,
               temperature=None, stop_sequences=None, stream=False, **kwargs):
        prompt = _flatten(messages)
        text, usage = call_cli(prompt, system=system, model=model)
        text = _apply_stop_sequences(text, stop_sequences)

        usage_obj = _Usage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
        message = _Message(text, model, usage_obj)

        if stream:
            return iter([message])
        return message

    def stream(self, **kwargs):
        raise ClaudeCLIError(
            "Real streaming is not available through the CLI backend. "
            "Use client.messages.create(...) instead."
        )


class Anthropic:
    """Mimics anthropic.Anthropic, backed by the claude CLI."""

    def __init__(self, api_key=None, **kwargs):
        # api_key is accepted and ignored: the CLI uses your logged-in session.
        self.api_key = api_key
        self.messages = _Messages()


def install(verbose=True):
    """Register this module as `anthropic` so later imports pick up the shim."""
    module = types.ModuleType("anthropic")
    module.Anthropic = Anthropic
    module.APIError = ClaudeCLIError
    sys.modules["anthropic"] = module

    if verbose:
        cli = find_cli()
        if cli:
            print(f"Backend: claude_cli -> {cli}")
            print("Billing: your Claude Pro plan. No API credits used.")
        else:
            print("Backend: claude_cli -> WARNING: `claude` not found on PATH.")
            print("Install the CLI and run `claude login`, then restart the kernel.")
    return module


def selftest():
    """Quick check that the CLI is installed, logged in, and responding."""
    cli = find_cli()
    print("CLI path :", cli or "NOT FOUND")
    if not cli:
        print("Result   : FAIL. Install the claude CLI and restart Jupyter.")
        return False
    try:
        text, usage = call_cli("Reply with exactly: OK", model="haiku", timeout=90)
    except ClaudeCLIError as e:
        print("Result   : FAIL")
        print(e)
        return False
    print("Reply    :", text.strip()[:120])
    print("Usage    :", usage.get("input_tokens", "?"), "in /",
          usage.get("output_tokens", "?"), "out")
    print("Result   : PASS. No API credits were used.")
    return True


if __name__ == "__main__":
    selftest()
