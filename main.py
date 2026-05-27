"""FastAPI app — the HTTP surface.

Endpoints:
  GET  /                       healthcheck
  GET  /agents                 list agents (public profiles)
  GET  /agents/{id}            public profile of one agent
  POST /agents/{id}/chat       send a message to an agent (owner OR stranger,
                               decided by Authorization header)

The trust boundary is enforced by resolve_identity() inside /chat.
The endpoint does not change shape based on caller — same URL, same body.
"""
import secrets
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db, llm, prompts
from identity import resolve_identity, Identity
from scopes import Scope

app = FastAPI(title="Agent Village")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class HistoryMessage(BaseModel):
    role: str      # 'user' or 'assistant'
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = []  # in-session turns before this message


class ChatResponse(BaseModel):
    reply: str
    identity: str  # 'OWNER' or 'STRANGER' — for transparency in the demo


class CreateAgentRequest(BaseModel):
    name: str
    bio: str
    visitor_bio: str
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# Public read endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def healthcheck():
    return {"status": "ok"}


@app.get("/agents")
def list_agents():
    """Public list — strips private fields."""
    return [_public_view(a) for a in db.list_agents()]


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    agent = db.fetch_agent(agent_id)
    if not agent:
        raise HTTPException(404, "agent not found")
    return _public_view(agent)


def _public_view(agent: dict) -> dict:
    """Strip private fields. This is the view a stranger gets via the API."""
    return {
        "id": agent["id"],
        "name": agent["name"],
        "visitor_bio": agent.get("visitor_bio") or agent.get("bio"),
        "status": agent.get("status"),
        "avatar_url": agent.get("avatar_url"),
        "accent_color": agent.get("accent_color"),
    }


# ---------------------------------------------------------------------------
# Agent lifecycle: bootstrap a new agent
# ---------------------------------------------------------------------------

@app.post("/agents")
def create_agent(req: CreateAgentRequest):
    """Spawn a new agent. Returns the api_key — show this to the owner ONCE."""
    api_key = "ak_" + secrets.token_urlsafe(24)
    client = db.get_client()
    res = client.table("living_agents").insert({
        "name": req.name,
        "bio": req.bio,
        "visitor_bio": req.visitor_bio,
        "status": req.status,
        "api_key": api_key,
    }).execute()
    agent = res.data[0]
    return {
        "id": agent["id"],
        "name": agent["name"],
        "api_key": api_key,  # Returned once. Owner must save this.
        "note": "Pass this api_key as `Authorization: Bearer <key>` to chat as the owner.",
    }


# ---------------------------------------------------------------------------
# The chat endpoint — the trust boundary in action
# ---------------------------------------------------------------------------

@app.post("/agents/{agent_id}/chat", response_model=ChatResponse)
def chat(agent_id: str, req: ChatRequest, authorization: Optional[str] = Header(None)):
    agent = db.fetch_agent(agent_id)
    if not agent:
        raise HTTPException(404, "agent not found")

    # 1. Identity — single place this decision is made.
    api_key = _strip_bearer(authorization)
    caller = resolve_identity(agent_id=agent_id, api_key=api_key)

    # 2. Identity → Scope mapping.
    scope = Scope.OWNER_CHAT if caller.identity == Identity.OWNER else Scope.STRANGER_CHAT

    # 3. Prompt assembly (Channel A — what data goes in)
    system_prompt = prompts.build_system_prompt(agent, scope)

    # 4. LLM call with scope-filtered tools (Channel B — what actions allowed)
    reply = llm.run_llm_turn(
        system_prompt=system_prompt,
        user_message=req.message,
        history=[{"role": m.role, "content": m.content} for m in req.history],
        scope=scope,
        agent_id=agent_id,
    )

    # 5. Side effects that the BACKEND (not the LLM) owns.
    if scope == Scope.OWNER_CHAT:
        # Persist this turn so the owner has continuity.
        db.insert_owner_chat_turn(agent_id, role="owner", content=req.message)
        db.insert_owner_chat_turn(agent_id, role="agent", content=reply)
    elif scope == Scope.STRANGER_CHAT:
        # Log the visit. Strangers do NOT get conversation history persisted.
        db.insert_visit_event(agent_id, content=req.message[:200])

    return ChatResponse(reply=reply, identity=caller.identity.value)


def _strip_bearer(header_val: Optional[str]) -> Optional[str]:
    if not header_val:
        return None
    if header_val.lower().startswith("bearer "):
        return header_val[7:].strip()
    return header_val.strip()
