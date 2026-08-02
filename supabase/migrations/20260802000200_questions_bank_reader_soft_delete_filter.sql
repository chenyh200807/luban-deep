-- questions_bank 库内读者软删收权（task#31 Part B）
-- 设计依据: docs/原始数据/数据盘点/2026-08-02-questions_bank软删版本化读者测绘与设计.md §1.2/§2.3
-- 审批单: docs/原始数据/数据盘点/extractions/supply_soft_delete_20260802/APPROVAL_SHEET.md
--
-- ⚠️ 本文件尚未在任何库执行。前置：20260802000100（Part A 加列）必须先 apply，
--    否则本文件全部函数编译失败（引用不存在的列）。
--
-- 内容：对 live 实测的全部 9 个库内读者（8 函数 + 1 视图）CREATE OR REPLACE，
-- 唯一改动 = 在 questions_bank 的 FROM/WHERE 上追加 `retired_at IS NULL` 谓词
--（refresh_syllabus_stats 另含 NOT EXISTS 子查询同步收权）。签名/返回列逐字不变，
-- 客户端零改动即生效——RPC 通道（supabase.py S3/S4/S5）的收权全靠这里。
--
-- 基线：每个对象的执行前原文 = live pg_get_functiondef 抓取件
--（extractions/supply_soft_delete_20260802/live_function_defs.json，2026-08-02）。
-- 回滚：extractions/supply_soft_delete_20260802/rollback_20260802000200.sql（原文原样回放）。
--
-- 本文件也是这 9 个对象**首次进仓版本化**（此前 SQL 只活在已部署项目里）。

-- ============================================================================
-- 1/9 search_questions_bank_vector — 生产 RAG 向量主通道（supabase.py:2438,:2503）
-- ============================================================================
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
      AND qb.retired_at IS NULL
      AND (1 - (qb.embedding <=> query_embedding)) > match_threshold
      AND (filter_question_type IS NULL OR qb.question_type = filter_question_type)
      AND (filter_source_type IS NULL OR qb.source_type = filter_source_type)
    ORDER BY qb.embedding <=> query_embedding
    LIMIT match_count;
END;
$function$;

-- ============================================================================
-- 2/9 search_questions_bank_text — 生产 RAG 全文通道（supabase.py:2360）
-- ============================================================================
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
WHERE qb.retired_at IS NULL
  AND coalesce(search_text, '') <> ''
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

-- ============================================================================
-- 3/9 search_questions_bank_text_ranked — 遗留（仓内零调用者，仍是可达面）
-- ============================================================================
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
    WHERE qb.retired_at IS NULL
      AND p.q_raw <> ''
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

-- ============================================================================
-- 4/9 search_questions — 遗留向量+年份（仓内零调用者，仍是可达面）
-- ============================================================================
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
  WHERE q.retired_at IS NULL
    AND (year_filter IS NULL OR q.exam_year = year_filter)
    AND (match_threshold < 0 OR 1 - (q.embedding <=> query_embedding) > match_threshold)
  ORDER BY q.embedding <=> query_embedding
  LIMIT match_count;
$function$;

-- ============================================================================
-- 5/9 search_questions_by_keywords — 遗留 trigram（SECURITY DEFINER，仓内零调用者）
-- ============================================================================
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
        where q.retired_at is null
          and (coalesce(q.question_stem, '') % search_query
           or coalesce(q.stem, '') % search_query)
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

-- ============================================================================
-- 6/9 match_questions — 遗留向量（SECURITY DEFINER，仓内零调用者）
-- ============================================================================
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
          AND retired_at IS NULL
    )
    SELECT * FROM ranked
    WHERE similarity >= match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
$function$;

-- ============================================================================
-- 7/9 get_questions_quality_stats_v2 — 质量统计（口径裁决：只算在服行，§2.5）
-- ============================================================================
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
    WHERE q.retired_at IS NULL
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

-- ============================================================================
-- 8/9 refresh_syllabus_stats — 考纲树计数（口径裁决：只算在服行，§2.5；
--     NOT EXISTS 子查询同步收权，使"只剩 retired 题"的节点归零）
-- ============================================================================
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
        WHERE retired_at IS NULL
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
          AND qb.retired_at IS NULL
    );
END;
$function$;

-- ============================================================================
-- 9/9 v_retrieval_questions — 视图（仓内零调用者，仍是可达面；列清单逐字保持，
--     含原定义中 id 的重复投影）
-- ============================================================================
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
  WHERE embedding IS NOT NULL
    AND retired_at IS NULL;
