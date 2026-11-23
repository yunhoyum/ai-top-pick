-- 공고 :src를 복제한다 (청크·임베딩 포함). 원본 실험 공고(3479·8452)는 그대로 두고 복사본으로만 측정한다.
-- psql -v src=<공고 ID> -v label=<조건 이름> -f clone_posting.sql  → 'NEW_POSTING_ID=<id>' 를 NOTICE로 출력한다
SELECT set_config('timing.src', :'src', false), set_config('timing.label', :'label', false);
DO $$
DECLARE
  src bigint := current_setting('timing.src')::bigint;
  new_id bigint;
  t text;
  cols text;
BEGIN
  SELECT string_agg(quote_ident(column_name), ',' ORDER BY ordinal_position) INTO cols
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'job_posting' AND is_identity = 'NO';
  EXECUTE format('INSERT INTO job_posting (%s) SELECT %s FROM job_posting WHERE posting_id = $1 RETURNING posting_id', cols, cols)
    INTO new_id USING src;
  FOREACH t IN ARRAY ARRAY['company_question', 'doc_chunk', 'essay_topic', 'posting_basic_item', 'posting_document',
                           'posting_eval_ratio', 'required_skill'] LOOP
    SELECT string_agg(quote_ident(column_name), ',' ORDER BY ordinal_position) INTO cols
      FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = t AND is_identity = 'NO' AND column_name <> 'posting_id';
    EXECUTE format('INSERT INTO %I (posting_id, %s) SELECT $2, %s FROM %I WHERE posting_id = $1', t, cols, cols, t)
      USING src, new_id;
  END LOOP;
  -- 접수 중으로 연다. 생각 시간은 측정에 필요 없어 줄인다
  UPDATE job_posting
     SET position_name = position_name || ' [시간측정 ' || current_setting('timing.label') || ' ← ' || src || ']',
         progress_status = '서류 접수 중', think_time_sec = 5, answer_time_sec = 60,
         doc_start_at = now() - interval '1 hour', doc_end_at = now() + interval '1 day',
         doc_result_at = now() + interval '2 days', interview_start_at = now() + interval '3 days',
         interview_end_at = now() + interval '4 days', interview_result_at = now() + interval '5 days'
   WHERE posting_id = new_id;
  RAISE NOTICE 'NEW_POSTING_ID=%', new_id;
END $$;
