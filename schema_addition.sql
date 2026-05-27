-- Single addition to the provided schema.
-- `kind` discriminates raw private facts from derived personality notes.
--
--   'private_fact'      → owner-only, never visible to diary or strangers
--   'personality_note'  → owner + diary visible (theme/voice, no concrete private detail)
--
-- This lets the agent's personality grow from private interactions
-- without leaking the underlying facts. See ARCHITECTURE.md §3.

ALTER TABLE living_memory
  ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'private_fact';

CREATE INDEX IF NOT EXISTS idx_living_memory_kind
  ON living_memory(agent_id, kind, created_at DESC);
