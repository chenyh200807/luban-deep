-- 回滚 20260802000200_questions_bank_reader_soft_delete_filter.sql
-- 内容：9 个库内读者恢复为 2026-08-02 live `pg_get_functiondef` / `pg_get_viewdef`
-- 抓取原文（live_function_defs.json / live_schema_evidence.json），逐字回放。
-- ⚠️ 仅回滚读侧收权（Part B）。Part A 加列回滚见 APPROVAL_SHEET.md A-R。

-- ---- restore get_questions_quality_stats_v2() ----
CREATE OR REPLACE FUNCTION public.get_questions_quality_stats_v2()
 RETURNS TABLE(source_type text, objective_total bigint, invalid_objective bigint, invalid_options bigint, missing_answer bigint)
 LANGUAGE sql
 STABLE
AS $function$
WITH norm AS (
    SELECT
        upper(coalesce(q.source_type, 'UNKNOWN')) AS src,
        CASE
            WHEN lower(coalesce(q.question_type, '')) = 'multiple_choice' THEN 'multi_choice'
            WHEN lower(coalesce(q.question_type, '')) = 'true_false' THEN 'judgment'
            ELSE lower(coalesce(q.question_type, ''))
        END AS qtype,
        q.options,
        q.correct_answer
    FROM public.questions_bank q
),
obj AS (
    SELECT *
    FROM norm
    WHERE qtype IN ('single_choice', 'multi_choice', 'judgment')
)
SELECT
    src AS source_type,
    COUNT(*) AS objective_total,
    SUM(CASE WHEN NOT public.qb_is_valid_objective_row(qtype, options, correct_answer) THEN 1 ELSE 0 END) AS invalid_objective,
    SUM(CASE WHEN options IS NULL OR jsonb_typeof(options) <> 'array' OR jsonb_array_length(options) < 2 THEN 1 ELSE 0 END) AS invalid_options,
    SUM(CASE WHEN trim(both '"' FROM coalesce(correct_answer::text, '')) IN ('', 'null', 'NULL') THEN 1 ELSE 0 END) AS missing_answer
FROM obj
GROUP BY src
ORDER BY objective_total DESC;
$function$;

-- ---- restore match_questions(vector,double precision,integer) ----
CREATE OR REPLACE FUNCTION public.match_questions(query_embedding vector, match_threshold double precision DEFAULT 0.5, match_count integer DEFAULT 3)
 RETURNS TABLE(question text, answer text, metadata jsonb, similarity real)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    WITH ranked AS (
        SELECT
            COALESCE(question_stem, stem, '') AS question,
            COALESCE(analysis, background_context, '') AS answer,
            jsonb_build_object(
                'original_id', original_id,
                'question_type', question_type,
                'node_code', node_code,
                'difficulty', difficulty
            ) AS metadata,
            1 - (embedding <=> query_embedding)::float4 AS similarity
        FROM public.questions_bank
        WHERE embedding IS NOT NULL
    )
    SELECT * FROM ranked
    WHERE similarity >= match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
$function$;

-- ---- restore refresh_syllabus_stats() ----
CREATE OR REPLACE FUNCTION public.refresh_syllabus_stats()
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
    WITH kc_stats AS (
        SELECT 
            node_code,
            COUNT(*) AS chunk_count,
            AVG(
                CASE difficulty 
                    WHEN '简单' THEN 1 
                    WHEN '困难' THEN 3 
                    ELSE 2 
                END
            )::FLOAT AS avg_difficulty,
            SUM(COALESCE(jsonb_array_length(key_parameters), 0)) AS total_key_params,
            BOOL_OR(COALESCE(exam_matrix->>'trap_alert', '') <> '') AS has_traps
        FROM knowledge_cards
        GROUP BY node_code
    ),
    qb_stats AS (
        SELECT 
            node_code,
            COUNT(*) AS question_count
        FROM questions_bank
        GROUP BY node_code
    ),
    combined AS (
        SELECT 
            COALESCE(kc.node_code, qb.node_code) AS node_code,
            kc.chunk_count,
            qb.question_count,
            kc.avg_difficulty,
            kc.total_key_params,
            kc.has_traps
        FROM kc_stats kc
        FULL OUTER JOIN qb_stats qb ON kc.node_code = qb.node_code
    )
    UPDATE syllabus_tree st
    SET 
        chunk_count = COALESCE(c.chunk_count, 0),
        question_count = COALESCE(c.question_count, 0),
        avg_difficulty = c.avg_difficulty,
        total_key_params = COALESCE(c.total_key_params, 0),
        has_traps = COALESCE(c.has_traps, FALSE)
    FROM combined c
    WHERE st.node_code = c.node_code;

    -- 对没有任何数据的节点重置为默认值
    UPDATE syllabus_tree st
    SET 
        chunk_count = 0,
        question_count = 0,
        avg_difficulty = NULL,
        total_key_params = 0,
        has_traps = FALSE
    WHERE NOT EXISTS (
        SELECT 1 FROM knowledge_cards kc 
        WHERE kc.node_code = st.node_code
    )
    AND NOT EXISTS (
        SELECT 1 FROM questions_bank qb 
        WHERE qb.node_code = st.node_code
    );
END;
$function$;

-- ---- restore search_questions(vector,double precision,integer,integer) ----
CREATE OR REPLACE FUNCTION public.search_questions(query_embedding vector, match_threshold double precision DEFAULT 0.3, match_count integer DEFAULT 20, year_filter integer DEFAULT NULL::integer)
 RETURNS TABLE(id bigint, original_id text, question_stem text, analysis text, node_code text, question_type text, exam_year integer, testing_focus text, trap_type text, similarity double precision)
 LANGUAGE sql
 STABLE
 SET search_path TO 'public'
AS $function$
  SELECT
    q.id,
    q.original_id,
    q.stem as question_stem,
    q.analysis,
    q.node_code,
    q.question_type,
    q.exam_year,
    q.testing_focus,
    q.trap_type,
    1 - (q.embedding <=> query_embedding) as similarity
  FROM questions_bank q
  WHERE (year_filter IS NULL OR q.exam_year = year_filter)
    AND (match_threshold < 0 OR 1 - (q.embedding <=> query_embedding) > match_threshold)
  ORDER BY q.embedding <=> query_embedding
  LIMIT match_count;
$function$;

-- ---- restore search_questions_bank_text(text,integer,text,text) ----
CREATE OR REPLACE FUNCTION public.search_questions_bank_text(search_text text, limit_count integer DEFAULT 10, filter_source_type text DEFAULT NULL::text, filter_question_type text DEFAULT NULL::text)
 RETURNS TABLE(id bigint, question_type text, stem text, question_stem text, options jsonb, correct_answer jsonb, analysis text, option_reasoning jsonb, grading_rubric jsonb, background_context text, logic_rule jsonb, structured_rules jsonb, image_url text, related_image_path text, node_code text, source_type text, exam_year integer, difficulty double precision, error_rate double precision, text_score real)
 LANGUAGE sql
 STABLE
AS $function$
SELECT
    qb.id,
    qb.question_type,
    qb.stem,
    qb.question_stem,
    qb.options,
    qb.correct_answer,
    qb.analysis,
    qb.option_reasoning,
    qb.grading_rubric,
    qb.background_context,
    qb.logic_rule,
    qb.structured_rules,
    qb.image_url,
    qb.related_image_path,
    qb.node_code,
    qb.source_type,
    qb.exam_year,
    qb.difficulty,
    qb.error_rate,
    0.0::real AS text_score
FROM public.questions_bank qb
WHERE coalesce(search_text, '') <> ''
  AND (
      qb.question_stem ILIKE '%' || search_text || '%'
      OR qb.stem ILIKE '%' || search_text || '%'
      OR qb.analysis ILIKE '%' || search_text || '%'
      OR qb.node_code ILIKE '%' || search_text || '%'
  )
  AND (filter_source_type IS NULL OR qb.source_type = filter_source_type)
  AND (filter_question_type IS NULL OR qb.question_type = filter_question_type)
LIMIT GREATEST(coalesce(limit_count, 10), 1);
$function$;

-- ---- restore search_questions_bank_text_ranked(text,integer,text,text) ----
CREATE OR REPLACE FUNCTION public.search_questions_bank_text_ranked(search_text text, limit_count integer DEFAULT 10, filter_source_type text DEFAULT NULL::text, filter_question_type text DEFAULT NULL::text)
 RETURNS TABLE(id bigint, question_type text, stem text, question_stem text, options jsonb, correct_answer jsonb, analysis text, option_reasoning jsonb, grading_rubric jsonb, background_context text, logic_rule jsonb, structured_rules jsonb, image_url text, related_image_path text, node_code text, source_type text, exam_year integer, difficulty double precision, error_rate double precision, text_score real)
 LANGUAGE sql
 STABLE
AS $function$
WITH params AS (
    SELECT
        coalesce(search_text, '') AS q_raw,
        regexp_replace(coalesce(search_text, ''), '([%_\\])', '\\\1', 'g') AS q_esc,
        GREATEST(coalesce(limit_count, 10), 1) AS k,
        LEAST(GREATEST(coalesce(limit_count, 10), 1) * 20, 300) AS probe_k
), candidates AS (
    SELECT
        qb.id,
        qb.question_type,
        qb.stem,
        qb.question_stem,
        qb.options,
        qb.correct_answer,
        qb.analysis,
        qb.option_reasoning,
        qb.grading_rubric,
        qb.background_context,
        qb.logic_rule,
        qb.structured_rules,
        qb.image_url,
        qb.related_image_path,
        qb.node_code,
        qb.source_type,
        qb.exam_year,
        qb.difficulty,
        qb.error_rate
    FROM public.questions_bank qb
    CROSS JOIN params p
    WHERE p.q_raw <> ''
      AND (
          qb.question_stem ILIKE '%' || p.q_esc || '%' ESCAPE E'\\'
          OR qb.stem ILIKE '%' || p.q_esc || '%' ESCAPE E'\\'
          OR qb.analysis ILIKE '%' || p.q_esc || '%' ESCAPE E'\\'
          OR qb.node_code ILIKE '%' || p.q_esc || '%' ESCAPE E'\\'
      )
      AND (filter_source_type IS NULL OR qb.source_type = filter_source_type)
      AND (filter_question_type IS NULL OR qb.question_type = filter_question_type)
    ORDER BY qb.id DESC
    LIMIT (SELECT probe_k FROM params)
)
SELECT
    c.id,
    c.question_type,
    c.stem,
    c.question_stem,
    c.options,
    c.correct_answer,
    c.analysis,
    c.option_reasoning,
    c.grading_rubric,
    c.background_context,
    c.logic_rule,
    c.structured_rules,
    c.image_url,
    c.related_image_path,
    c.node_code,
    c.source_type,
    c.exam_year,
    c.difficulty,
    c.error_rate,
    GREATEST(
        similarity(coalesce(c.question_stem, ''), p.q_raw),
        similarity(coalesce(c.stem, ''), p.q_raw),
        similarity(coalesce(c.analysis, ''), p.q_raw),
        similarity(coalesce(c.node_code, ''), p.q_raw)
    )::real AS text_score
FROM candidates c
CROSS JOIN params p
ORDER BY text_score DESC, c.error_rate DESC NULLS LAST, c.id DESC
LIMIT (SELECT k FROM params);
$function$;

-- ---- restore search_questions_bank_vector(vector,real,integer,text,text) ----
CREATE OR REPLACE FUNCTION public.search_questions_bank_vector(query_embedding vector, match_threshold real DEFAULT 0.35, match_count integer DEFAULT 10, filter_question_type text DEFAULT NULL::text, filter_source_type text DEFAULT NULL::text)
 RETURNS TABLE(id bigint, question_type text, stem text, question_stem text, options jsonb, correct_answer jsonb, analysis text, grading_keywords jsonb, grading_rubric jsonb, option_reasoning jsonb, similarity real, node_code text, exam_year integer, source_type text, difficulty double precision)
 LANGUAGE plpgsql
AS $function$
BEGIN
    SET LOCAL hnsw.ef_search = 100;
    RETURN QUERY
    SELECT
        qb.id,
        qb.question_type,
        qb.stem,
        qb.question_stem,
        qb.options,
        qb.correct_answer,
        qb.analysis,
        qb.grading_keywords,
        qb.grading_rubric,
        qb.option_reasoning,
        (1 - (qb.embedding <=> query_embedding))::REAL AS similarity,
        qb.node_code,
        qb.exam_year,
        qb.source_type,
        qb.difficulty
    FROM questions_bank qb
    WHERE qb.embedding IS NOT NULL
      AND (1 - (qb.embedding <=> query_embedding)) > match_threshold
      AND (filter_question_type IS NULL OR qb.question_type = filter_question_type)
      AND (filter_source_type IS NULL OR qb.source_type = filter_source_type)
    ORDER BY qb.embedding <=> query_embedding
    LIMIT match_count;
END;
$function$;

-- ---- restore search_questions_by_keywords(text,integer) ----
CREATE OR REPLACE FUNCTION public.search_questions_by_keywords(search_query text, limit_count integer DEFAULT 5)
 RETURNS TABLE(id bigint, question_stem text, stem text, correct_answer jsonb, option_reasoning jsonb, question_type text, similarity real)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    with scored as (
        select
            q.id,
            q.question_stem,
            q.stem,
            q.correct_answer,
            q.option_reasoning,
            q.question_type,
            greatest(
                similarity(coalesce(q.question_stem, ''), search_query),
                similarity(coalesce(q.stem, ''), search_query)
            ) as sim
        from public.questions_bank q
        where coalesce(q.question_stem, '') % search_query
           or coalesce(q.stem, '') % search_query
    )
    select
        id,
        question_stem,
        stem,
        correct_answer,
        option_reasoning,
        question_type,
        sim::float4 as similarity
    from scored
    where sim >= 0.1  -- 较低的阈值，确保召回
    order by sim desc
    limit limit_count;
$function$;

-- ---- restore view v_retrieval_questions ----
CREATE OR REPLACE VIEW public.v_retrieval_questions AS
 SELECT id AS question_id,
    node_code,
    question_stem,
    options,
    correct_answer,
    analysis,
    exam_year,
    based_on_version,
    embedding,
    id,
    original_id,
    question_type,
    stem,
    grading_keywords,
    source_type
   FROM questions_bank qb
  WHERE embedding IS NOT NULL;