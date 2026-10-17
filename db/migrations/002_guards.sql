BEGIN;

CREATE FUNCTION reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is immutable', TG_TABLE_NAME; END $$;
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_change();
CREATE TRIGGER ai_evaluations_immutable BEFORE UPDATE OR DELETE ON ai_evaluations FOR EACH ROW EXECUTE FUNCTION reject_change();
CREATE TRIGGER ai_scores_immutable BEFORE UPDATE OR DELETE ON ai_criterion_scores FOR EACH ROW EXECUTE FUNCTION reject_change();
CREATE TRIGGER evidence_immutable BEFORE UPDATE OR DELETE ON retrieval_evidence FOR EACH ROW EXECUTE FUNCTION reject_change();

CREATE FUNCTION guard_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n integer; total numeric(10,2);
BEGIN
 IF TG_OP='DELETE' THEN
  IF OLD.status<>'draft' THEN RAISE EXCEPTION 'published assignment version is immutable'; END IF;
  RETURN OLD;
 END IF;
 IF OLD.status<>'draft' THEN
  IF NEW.status='retired' AND OLD.status='published' AND
    (to_jsonb(NEW)-'status'-'updated_at')=(to_jsonb(OLD)-'status'-'updated_at') THEN RETURN NEW; END IF;
  RAISE EXCEPTION 'published assignment version is immutable';
 END IF;
 IF NEW.status='retired' THEN RAISE EXCEPTION 'draft version cannot be retired'; END IF;
 IF NEW.status='published' THEN
  IF length(trim(NEW.instructions))=0 THEN RAISE EXCEPTION 'instructions required'; END IF;
  SELECT count(*),coalesce(sum(max_points),0) INTO n,total FROM rubric_criteria
   WHERE organization_id=NEW.organization_id AND assignment_version_id=NEW.id;
  IF n=0 OR total<>NEW.max_score THEN RAISE EXCEPTION 'rubric must cover max score'; END IF;
  IF NOT EXISTS (
   SELECT 1 FROM reference_solutions r WHERE r.organization_id=NEW.organization_id
    AND r.assignment_version_id=NEW.id AND
    (length(trim(coalesce(r.answer_text,'')))>0 OR EXISTS (
      SELECT 1 FROM reference_solution_files rf JOIN file_assets f
       ON f.organization_id=rf.organization_id AND f.id=rf.file_asset_id
      WHERE rf.organization_id=r.organization_id AND rf.reference_solution_id=r.id
       AND f.processing_status='ready'))
  ) THEN RAISE EXCEPTION 'usable reference solution required'; END IF;
  NEW.published_at:=now();
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER assignment_version_guard BEFORE UPDATE OR DELETE ON assignment_versions
 FOR EACH ROW EXECUTE FUNCTION guard_version();

CREATE FUNCTION guard_version_child() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE version_id uuid; tenant_id uuid; current_status text;
BEGIN
 IF TG_TABLE_NAME='reference_solution_files' THEN
  SELECT r.assignment_version_id INTO version_id FROM reference_solutions r
   WHERE r.organization_id=coalesce(NEW.organization_id,OLD.organization_id)
    AND r.id=coalesce(NEW.reference_solution_id,OLD.reference_solution_id);
 ELSE
  version_id:=coalesce(NEW.assignment_version_id,OLD.assignment_version_id);
 END IF;
 tenant_id:=coalesce(NEW.organization_id,OLD.organization_id);
 SELECT status INTO current_status FROM assignment_versions
  WHERE organization_id=tenant_id AND id=version_id FOR UPDATE;
 IF current_status<>'draft' THEN RAISE EXCEPTION 'published version content is immutable'; END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER rubric_version_guard BEFORE INSERT OR UPDATE OR DELETE ON rubric_criteria FOR EACH ROW EXECUTE FUNCTION guard_version_child();
CREATE TRIGGER reference_version_guard BEFORE INSERT OR UPDATE OR DELETE ON reference_solutions FOR EACH ROW EXECUTE FUNCTION guard_version_child();
CREATE TRIGGER reference_files_version_guard BEFORE INSERT OR UPDATE OR DELETE ON reference_solution_files FOR EACH ROW EXECUTE FUNCTION guard_version_child();

CREATE FUNCTION validate_document_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.file_asset_id IS NOT NULL AND NEW.reference_solution_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM reference_solution_files WHERE organization_id=NEW.organization_id
   AND reference_solution_id=NEW.reference_solution_id AND file_asset_id=NEW.file_asset_id
 ) THEN RAISE EXCEPTION 'document file is not attached to reference'; END IF;
 IF NEW.file_asset_id IS NOT NULL AND NEW.submission_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM submission_files WHERE organization_id=NEW.organization_id
   AND submission_id=NEW.submission_id AND file_asset_id=NEW.file_asset_id
 ) THEN RAISE EXCEPTION 'document file is not attached to submission'; END IF;
 IF TG_OP='UPDATE' AND OLD.status='ready' THEN RAISE EXCEPTION 'ready document is immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER document_source_guard BEFORE INSERT OR UPDATE ON documents FOR EACH ROW EXECUTE FUNCTION validate_document_source();
CREATE TRIGGER document_no_delete BEFORE DELETE ON documents FOR EACH ROW
 WHEN (OLD.status='ready') EXECUTE FUNCTION reject_change();

CREATE FUNCTION guard_submission_files() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s text;
BEGIN
 SELECT status INTO s FROM submissions WHERE organization_id=coalesce(NEW.organization_id,OLD.organization_id)
  AND id=coalesce(NEW.submission_id,OLD.submission_id) FOR UPDATE;
 IF s<>'draft' THEN RAISE EXCEPTION 'finalized submission attachments are immutable'; END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER submission_files_guard BEFORE INSERT OR UPDATE OR DELETE ON submission_files
 FOR EACH ROW EXECUTE FUNCTION guard_submission_files();
CREATE FUNCTION guard_submission() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE version_status text;
BEGIN
 IF OLD.status='draft' AND NEW.status<>'draft' THEN
  SELECT status INTO version_status FROM assignment_versions
   WHERE organization_id=NEW.organization_id AND id=NEW.assignment_version_id FOR UPDATE;
  IF version_status<>'published' THEN RAISE EXCEPTION 'version does not accept submissions'; END IF;
  IF EXISTS (SELECT 1 FROM submission_files sf JOIN file_assets f
    ON f.organization_id=sf.organization_id AND f.id=sf.file_asset_id
    WHERE sf.organization_id=NEW.organization_id AND sf.submission_id=NEW.id
      AND f.processing_status<>'ready') AND NEW.status='ready' THEN
    RAISE EXCEPTION 'submission files must be ready'; END IF;
  NEW.submitted_at:=coalesce(NEW.submitted_at,now());
 END IF;
 IF OLD.status<>'draft' AND (NEW.assignment_version_id,NEW.student_id,NEW.attempt_number,NEW.submitted_by,NEW.idempotency_key,NEW.submitted_at)
  IS DISTINCT FROM (OLD.assignment_version_id,OLD.student_id,OLD.attempt_number,OLD.submitted_by,OLD.idempotency_key,OLD.submitted_at)
  THEN RAISE EXCEPTION 'finalized submission identity is immutable'; END IF;
 IF NEW.current_published_grade_id IS DISTINCT FROM OLD.current_published_grade_id AND NEW.current_published_grade_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM grade_revisions g WHERE g.organization_id=NEW.organization_id
    AND g.id=NEW.current_published_grade_id AND g.submission_id=NEW.id AND g.status='published')
  THEN RAISE EXCEPTION 'current grade must be published for this submission'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER submission_guard BEFORE UPDATE ON submissions FOR EACH ROW EXECUTE FUNCTION guard_submission();

CREATE FUNCTION validate_scores(kind text, tenant uuid, parent_id uuid, version_id uuid, expected numeric)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE n integer; total numeric;
BEGIN
 IF kind='ai' THEN
  SELECT count(*),coalesce(sum(s.score),0) INTO n,total FROM ai_criterion_scores s
   JOIN rubric_criteria c ON c.organization_id=s.organization_id AND c.id=s.rubric_criterion_id
   WHERE s.organization_id=tenant AND s.ai_evaluation_id=parent_id AND s.assignment_version_id=version_id
    AND s.score<=c.max_points;
 ELSE
  SELECT count(*),coalesce(sum(s.score),0) INTO n,total FROM grade_criterion_scores s
   JOIN rubric_criteria c ON c.organization_id=s.organization_id AND c.id=s.rubric_criterion_id
   WHERE s.organization_id=tenant AND s.grade_revision_id=parent_id AND s.assignment_version_id=version_id
    AND s.score<=c.max_points;
 END IF;
 IF n<>(SELECT count(*) FROM rubric_criteria WHERE organization_id=tenant AND assignment_version_id=version_id)
  OR total<>expected THEN RAISE EXCEPTION 'criterion scores must cover rubric and match total'; END IF;
 IF expected>(SELECT max_score FROM assignment_versions WHERE organization_id=tenant AND id=version_id)
  THEN RAISE EXCEPTION 'total score exceeds maximum'; END IF;
END $$;

CREATE FUNCTION guard_run() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e record;
BEGIN
 IF NEW.status='succeeded' AND OLD.status<>'succeeded' THEN
  SELECT * INTO e FROM ai_evaluations WHERE organization_id=NEW.organization_id AND grading_run_id=NEW.id;
  IF NOT FOUND THEN RAISE EXCEPTION 'successful run requires evaluation'; END IF;
  PERFORM validate_scores('ai',NEW.organization_id,e.id,NEW.assignment_version_id,e.total_score);
  NEW.completed_at:=coalesce(NEW.completed_at,now());
 END IF;
 IF OLD.status='succeeded' THEN RAISE EXCEPTION 'successful run is immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grading_run_guard BEFORE UPDATE ON grading_runs FOR EACH ROW EXECUTE FUNCTION guard_run();

CREATE FUNCTION guard_grade() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ai_score numeric; old_grade uuid;
BEGIN
 IF TG_OP='DELETE' THEN
  IF OLD.status='published' THEN RAISE EXCEPTION 'published grade is immutable'; END IF;
  RETURN OLD;
 END IF;
 IF OLD.status='published' THEN RAISE EXCEPTION 'published grade is immutable'; END IF;
 IF NEW.status='published' THEN
  PERFORM validate_scores('grade',NEW.organization_id,NEW.id,NEW.assignment_version_id,NEW.total_score);
  SELECT current_published_grade_id INTO old_grade FROM submissions
   WHERE organization_id=NEW.organization_id AND id=NEW.submission_id FOR UPDATE;
  IF old_grade IS DISTINCT FROM NEW.supersedes_revision_id THEN
   RAISE EXCEPTION 'stale grade revision'; END IF;
  IF NEW.based_on_ai_evaluation_id IS NOT NULL THEN
   SELECT e.total_score INTO ai_score FROM ai_evaluations e JOIN grading_runs r
    ON r.organization_id=e.organization_id AND r.id=e.grading_run_id
    WHERE e.organization_id=NEW.organization_id AND e.id=NEW.based_on_ai_evaluation_id
     AND r.submission_id=NEW.submission_id;
   IF NOT FOUND THEN RAISE EXCEPTION 'AI evaluation belongs to another submission'; END IF;
  END IF;
  IF (old_grade IS NOT NULL OR (ai_score IS NOT NULL AND ai_score<>NEW.total_score))
   AND length(trim(coalesce(NEW.review_reason,'')))=0 THEN RAISE EXCEPTION 'review reason required'; END IF;
  NEW.published_at:=now();
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grade_guard BEFORE UPDATE OR DELETE ON grade_revisions FOR EACH ROW EXECUTE FUNCTION guard_grade();
CREATE FUNCTION guard_grade_score() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s text;
BEGIN
 SELECT status INTO s FROM grade_revisions WHERE organization_id=coalesce(NEW.organization_id,OLD.organization_id)
  AND id=coalesce(NEW.grade_revision_id,OLD.grade_revision_id) FOR UPDATE;
 IF s='published' THEN RAISE EXCEPTION 'published grade scores are immutable'; END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER grade_score_guard BEFORE INSERT OR UPDATE OR DELETE ON grade_criterion_scores FOR EACH ROW EXECUTE FUNCTION guard_grade_score();

CREATE FUNCTION publish_grade_side_effects() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.status='published' AND OLD.status='draft' THEN
  UPDATE submissions SET current_published_grade_id=NEW.id
   WHERE organization_id=NEW.organization_id AND id=NEW.submission_id;
  UPDATE exemplars SET status='revoked',revoked_at=now(),revocation_reason='grade superseded'
   WHERE organization_id=NEW.organization_id AND submission_id=NEW.submission_id AND status='active';
  INSERT INTO audit_events(organization_id,actor_user_id,action,entity_type,entity_id)
   VALUES(NEW.organization_id,NEW.reviewed_by,'grade.published','grade_revision',NEW.id);
  INSERT INTO outbox_events(organization_id,event_type,payload)
   VALUES(NEW.organization_id,'grade.published',jsonb_build_object('grade_revision_id',NEW.id));
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grade_publish_effects AFTER UPDATE ON grade_revisions FOR EACH ROW EXECUTE FUNCTION publish_grade_side_effects();

CREATE FUNCTION guard_exemplar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE g record; threshold numeric; doc_ready boolean;
BEGIN
 IF TG_OP='INSERT' THEN
  SELECT * INTO g FROM grade_revisions WHERE organization_id=NEW.organization_id AND id=NEW.grade_revision_id;
  SELECT v.max_score*v.exemplar_threshold_percent/100 INTO threshold FROM assignment_versions v
   WHERE v.organization_id=NEW.organization_id AND v.id=NEW.assignment_version_id;
  IF g.status<>'published' OR g.total_score<threshold OR NOT EXISTS (
    SELECT 1 FROM submissions s WHERE s.organization_id=NEW.organization_id AND s.id=NEW.submission_id
     AND s.current_published_grade_id=NEW.grade_revision_id) THEN
   RAISE EXCEPTION 'exemplar requires eligible current published grade'; END IF;
 ELSIF OLD.status='revoked' OR NEW.status<>'revoked' OR
   (to_jsonb(NEW)-'status'-'revoked_at'-'revocation_reason'-'updated_at')
   <> (to_jsonb(OLD)-'status'-'revoked_at'-'revocation_reason'-'updated_at') THEN
  RAISE EXCEPTION 'exemplar may only be revoked';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER exemplar_guard BEFORE INSERT OR UPDATE ON exemplars FOR EACH ROW EXECUTE FUNCTION guard_exemplar();

CREATE FUNCTION validate_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d record; run_version uuid; source_version uuid;
BEGIN
 SELECT d.* INTO d FROM documents d JOIN document_chunks c ON c.organization_id=d.organization_id AND c.document_id=d.id
  WHERE c.organization_id=NEW.organization_id AND c.id=NEW.document_chunk_id;
 SELECT assignment_version_id INTO run_version FROM grading_runs
  WHERE organization_id=NEW.organization_id AND id=NEW.grading_run_id;
 IF NEW.exemplar_id IS NOT NULL THEN
  SELECT assignment_version_id INTO source_version FROM exemplars WHERE organization_id=NEW.organization_id
   AND id=NEW.exemplar_id AND status='active';
  IF d.exemplar_id IS DISTINCT FROM NEW.exemplar_id THEN RAISE EXCEPTION 'evidence source mismatch'; END IF;
 ELSE
  SELECT assignment_version_id INTO source_version FROM reference_solutions WHERE organization_id=NEW.organization_id
   AND id=NEW.reference_solution_id;
  IF d.reference_solution_id IS DISTINCT FROM NEW.reference_solution_id THEN RAISE EXCEPTION 'evidence source mismatch'; END IF;
 END IF;
 IF source_version IS DISTINCT FROM run_version OR d.status<>'ready' THEN
  RAISE EXCEPTION 'evidence must be ready and from evaluated version'; END IF;
 IF NOT EXISTS (SELECT 1 FROM chunk_embeddings WHERE organization_id=NEW.organization_id
  AND document_chunk_id=NEW.document_chunk_id AND embedding_profile_id=NEW.embedding_profile_id) THEN
  RAISE EXCEPTION 'evidence embedding profile mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER evidence_guard BEFORE INSERT ON retrieval_evidence FOR EACH ROW EXECUTE FUNCTION validate_evidence();

CREATE FUNCTION tenant_context() RETURNS uuid LANGUAGE sql STABLE AS $$
 SELECT nullif(current_setting('app.organization_id',true),'')::uuid
$$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['memberships','students','assignments','assignment_versions','rubric_criteria',
  'reference_solutions','reference_solution_files','file_assets','submissions','submission_files','grading_runs',
  'ai_evaluations','ai_criterion_scores','grade_revisions','grade_criterion_scores','exemplars','documents',
  'document_chunks','chunk_embeddings','retrieval_evidence','processing_jobs','outbox_events','audit_events'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (organization_id=tenant_context()) WITH CHECK (organization_id=tenant_context())',t);
 END LOOP;
END $$;

COMMIT;
