"""Groq API wrapper with tool-use loop.

Single function: run_llm_turn(). Given a system prompt, a user message,
the agent_id, and the scope, it:

  1. Calls the LLM with the scope-filtered tool list (OpenAI/Groq format).
  2. If the model asks to use a tool, executes it (with permission checks),
     feeds the result back, and loops.
  3. Returns the final text reply when the model is done.

The scope is closed over inside this function — the LLM has no way to
influence the scope used by the tool dispatcher.
"""
import json
from typing import Optional

from groq import Groq

import config, tools
from scopes import Scope

_client: Optional[Groq] = None

MAX_TOOL_ROUNDS = 6


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def _to_groq_tool(schema: dict) -> dict:
    """Convert Anthropic-style tool schema → OpenAI/Groq format."""
    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema.get("description", ""),
            "parameters": schema["input_schema"],
        },
    }


def run_llm_turn(
    *,
    system_prompt: str,
    user_message: str,
    scope: Scope,
    agent_id: str,
    history: list[dict] | None = None,
) -> str:
    """Run a single user→assistant turn, handling any tool calls.

    Returns the final text the assistant produced after all tool calls
    have been resolved.
    """
    tool_schemas = tools.schemas_for_scope(scope)
    groq_tools = [_to_groq_tool(s) for s in tool_schemas] if tool_schemas else None

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ROUNDS):
        kwargs: dict = {
            "model": config.LLM_MODEL,
            "max_tokens": config.LLM_MAX_TOKENS,
            "messages": messages,
        }
        if groq_tools:
            kwargs["tools"] = groq_tools

        response = get_client().chat.completions.create(**kwargs)
        msg = response.choices[0].message

        if response.choices[0].finish_reason != "tool_calls" or not msg.tool_calls:
            return msg.content or ""

        # Append assistant turn with tool calls (serialised for the next request).
        tool_calls_data = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": tool_calls_data,
        })

        # Execute each tool and append results.
        for tc in msg.tool_calls:
            result = tools.execute_tool(
                name=tc.function.name,
                scope=scope,
                agent_id=agent_id,
                args=json.loads(tc.function.arguments),
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return msg.content or "(the agent went quiet)"
