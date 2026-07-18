begin;

create extension if not exists pgcrypto;

-- Internal identity kernel for the durable retest-probe claim. UUID-shaped
-- anchors collapse to lowercase compact hex; opaque anchors remain trimmed.
create or replace function public.canonical_luban_cycle_anchor(p_value text)
returns text
language plpgsql
immutable
security invoker
set search_path = public, pg_temp
as $$
declare
  v_value text := btrim(coalesce(p_value, ''));
begin
  if v_value = '' then
    return '';
  end if;
  begin
    return replace(lower(v_value::uuid::text), '-', '');
  exception
    when invalid_text_representation then
      return v_value;
  end;
end;
$$;

revoke all on function public.canonical_luban_cycle_anchor(text) from public;
revoke all on function public.canonical_luban_cycle_anchor(text) from anon;
revoke all on function public.canonical_luban_cycle_anchor(text) from authenticated;
grant execute on function public.canonical_luban_cycle_anchor(text) to service_role;

-- The durable ledger is the only claim authority. Before minting a canonical
-- dedupe key, recover the earliest historical winner across legacy UUID text
-- forms so a new representation can never steal an existing claim.
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
  v_user_id text := btrim(p_user_id);
  v_probe_id text := btrim(p_probe_id);
  v_cycle_anchor text;
  v_completion_id text := btrim(p_completion_id);
  v_dedupe_key text;
  v_identity_json text;
  v_event_id uuid;
  v_inserted integer := 0;
  v_equivalent_winner_count integer := 0;
  v_winner public.learner_memory_events%rowtype;
  v_winner_hash text;
  v_winner_completion text;
begin
  if nullif(v_user_id, '') is null
     or nullif(v_probe_id, '') is null
     or nullif(btrim(p_cycle_anchor), '') is null
     or nullif(v_completion_id, '') is null
     or length(v_user_id) > 512
     or length(v_probe_id) > 512
     or length(btrim(p_cycle_anchor)) > 512
     or length(v_completion_id) > 512
     or p_request_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'retest_probe_claim_invalid';
  end if;

  v_cycle_anchor := public.canonical_luban_cycle_anchor(p_cycle_anchor);

  select count(*)
    into v_equivalent_winner_count
    from public.learner_memory_events as event
   where event.user_id = v_user_id
     and event.source_id = v_probe_id
     and event.source_feature = 'luban_retest_claim'
     and event.memory_kind = 'retest_control_claim'
     and event.payload_json->>'event_type' = 'retest_probe_claim'
     and public.canonical_luban_cycle_anchor(
       event.payload_json->>'cycle_anchor'
     ) = v_cycle_anchor;

  select event.*
    into v_winner
    from public.learner_memory_events as event
   where event.user_id = v_user_id
     and event.source_id = v_probe_id
     and event.source_feature = 'luban_retest_claim'
     and event.memory_kind = 'retest_control_claim'
     and event.payload_json->>'event_type' = 'retest_probe_claim'
     and public.canonical_luban_cycle_anchor(
       event.payload_json->>'cycle_anchor'
     ) = v_cycle_anchor
   order by event.created_at asc, event.event_id asc
   limit 1;

  if found then
    if v_equivalent_winner_count > 1 then
      raise warning 'multiple equivalent retest probe claim winners: user_id=%, probe_id=%, cycle_anchor=%, count=%',
        v_user_id, v_probe_id, v_cycle_anchor, v_equivalent_winner_count;
    end if;
    v_winner_hash := v_winner.payload_json->>'request_hash';
    v_winner_completion := v_winner.payload_json->>'completion_id';
    return jsonb_build_object(
      'status', case
        when v_winner_hash is distinct from p_request_hash then 'conflict'
        when v_winner_completion = v_completion_id then 'acquired'
        else 'replay'
      end,
      'completion_id', v_winner_completion,
      'request_hash', v_winner_hash,
      'claim_event_id', v_winner.event_id::text
    );
  end if;

  v_identity_json := jsonb_build_array(
    v_user_id, v_probe_id, v_cycle_anchor
  )::text;
  v_dedupe_key := concat(
    'luban_retest_probe_claim:v3:',
    encode(digest(v_identity_json, 'sha256'), 'hex')
  );
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
    v_user_id,
    'luban_retest_claim',
    v_probe_id,
    null,
    'retest_control_claim',
    jsonb_build_object(
      'event_type', 'retest_probe_claim',
      'probe_id', v_probe_id,
      'cycle_anchor', v_cycle_anchor,
      'completion_id', v_completion_id,
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
      when v_winner_hash is distinct from p_request_hash then 'conflict'
      when v_winner_completion = v_completion_id then 'acquired'
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

commit;
