begin;

create extension if not exists pgcrypto;

-- B3: one durable winner for a user's due review probe/cycle.  Reuse the
-- canonical learner_memory_events ledger and its unique dedupe_key; do not
-- create a second lifecycle table.  This function intentionally performs an
-- immutable INSERT ... ON CONFLICT DO NOTHING followed by reading the winner.
-- A merge-upsert would let a loser replace the winning completion/hash.
create or replace function public.claim_luban_retest_probe(
  p_user_id text,
  p_probe_id text,
  p_cycle_anchor text,
  p_completion_id text,
  p_request_hash text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_dedupe_key text;
  v_identity_json text;
  v_event_id uuid;
  v_inserted integer := 0;
  v_winner public.learner_memory_events%rowtype;
  v_winner_hash text;
  v_winner_completion text;
begin
  if nullif(btrim(p_user_id), '') is null
     or nullif(btrim(p_probe_id), '') is null
     or nullif(btrim(p_cycle_anchor), '') is null
     or nullif(btrim(p_completion_id), '') is null
     or length(btrim(p_user_id)) > 512
     or length(btrim(p_probe_id)) > 512
     or length(btrim(p_cycle_anchor)) > 512
     or length(btrim(p_completion_id)) > 512
     or p_request_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'retest_probe_claim_invalid';
  end if;

  -- Hash a canonical JSON tuple instead of joining untrusted components with
  -- delimiters (``[a:b,c]`` must not collide with ``[a,b:c]``).
  v_identity_json := jsonb_build_array(
    btrim(p_user_id), btrim(p_probe_id), btrim(p_cycle_anchor)
  )::text;
  v_dedupe_key := concat(
    'luban_retest_probe_claim:v3:',
    encode(digest(v_identity_json, 'sha256'), 'hex')
  );
  -- Keep the PK independent from the business unique key.  If both racers used
  -- the same deterministic UUID, PostgreSQL could raise a PK conflict before
  -- the targeted dedupe_key conflict handler arbitrates the loser.
  v_event_id := gen_random_uuid();

  insert into public.learner_memory_events (
    event_id,
    user_id,
    source_feature,
    source_id,
    source_bot_id,
    memory_kind,
    payload_json,
    dedupe_key
  ) values (
    v_event_id,
    btrim(p_user_id),
    'luban_retest_claim',
    btrim(p_probe_id),
    null,
    'retest_control_claim',
    jsonb_build_object(
      'event_type', 'retest_probe_claim',
      'probe_id', btrim(p_probe_id),
      'cycle_anchor', btrim(p_cycle_anchor),
      'completion_id', btrim(p_completion_id),
      'request_hash', p_request_hash,
      'request_hash_version', 3
    ),
    v_dedupe_key
  )
  on conflict (dedupe_key) do nothing;
  get diagnostics v_inserted = row_count;

  select *
    into v_winner
    from public.learner_memory_events
   where dedupe_key = v_dedupe_key;

  if not found then
    raise exception 'retest_probe_claim_missing_after_insert';
  end if;
  v_winner_hash := v_winner.payload_json->>'request_hash';
  v_winner_completion := v_winner.payload_json->>'completion_id';

  return jsonb_build_object(
    'status', case
      when v_inserted = 1 then 'acquired'
      when v_winner_hash <> p_request_hash then 'conflict'
      -- A crash after claim but before terminal must be recoverable.  Only the
      -- durable winner completion may resume; a different completion with the
      -- same semantic request stays replay/pending and can never steal.
      when v_winner_completion = btrim(p_completion_id) then 'acquired'
      else 'replay'
    end,
    'completion_id', v_winner_completion,
    'request_hash', v_winner_hash,
    'claim_event_id', v_winner.event_id::text
  );
end;
$$;

revoke all on function public.claim_luban_retest_probe(text, text, text, text, text) from public;
revoke all on function public.claim_luban_retest_probe(text, text, text, text, text) from anon;
revoke all on function public.claim_luban_retest_probe(text, text, text, text, text) from authenticated;
grant execute on function public.claim_luban_retest_probe(text, text, text, text, text) to service_role;

-- Replay readers use this narrow direct RPC after claim arbitration.  It
-- bypasses the application service's general 20-second event cache, so a
-- loser can observe the winner terminal as soon as the durable event exists.
create or replace function public.read_luban_retest_completion_events(
  p_user_id text,
  p_completion_id text
)
returns setof public.learner_memory_events
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select event.*
    from public.learner_memory_events as event
   where event.user_id = btrim(p_user_id)
     and event.memory_kind = 'learning_evidence'
     and length(btrim(p_user_id)) between 1 and 512
     and length(btrim(p_completion_id)) between 1 and 512
     and (
       event.payload_json->>'retest_completion_id' = btrim(p_completion_id)
       or event.payload_json->>'completion_id' = btrim(p_completion_id)
     )
   order by event.created_at asc, event.event_id asc;
$$;

revoke all on function public.read_luban_retest_completion_events(text, text) from public;
revoke all on function public.read_luban_retest_completion_events(text, text) from anon;
revoke all on function public.read_luban_retest_completion_events(text, text) from authenticated;
grant execute on function public.read_luban_retest_completion_events(text, text) to service_role;

commit;
