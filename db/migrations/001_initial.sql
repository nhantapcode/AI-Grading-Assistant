BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END $$;

CREATE TABLE organizations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL CHECK (length(trim(name))>0),
 status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','archived')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email text NOT NULL UNIQUE CHECK (email=lower(email) AND length(trim(email))>0),
 display_name text NOT NULL, password_hash text, identity_provider text NOT NULL DEFAULT 'local', provider_subject text,
 status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(identity_provider,provider_subject), CHECK(identity_provider <> 'local' OR password_hash IS NOT NULL)
);
CREATE TABLE memberships (
 organization_id uuid NOT NULL REFERENCES organizations(id), user_id uuid NOT NULL REFERENCES users(id),
 role text NOT NULL CHECK(role IN ('owner','admin','trainer')),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(organization_id,user_id)
);
CREATE INDEX memberships_user_status_idx ON memberships(user_id,status);
CREATE TABLE auth_sessions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(id), refresh_token_hash text NOT NULL UNIQUE,
 expires_at timestamptz NOT NULL, revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_sessions_active_idx ON auth_sessions(user_id,expires_at) WHERE revoked_at IS NULL;

CREATE TABLE students (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 external_student_id text NOT NULL, display_name text NOT NULL, email text, user_id uuid REFERENCES users(id),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,external_student_id)
);
CREATE TABLE assignments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 title text NOT NULL, description text, created_by uuid NOT NULL,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','archived')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), FOREIGN KEY(organization_id,created_by) REFERENCES memberships(organization_id,user_id)
);
CREATE INDEX assignments_list_idx ON assignments(organization_id,status,created_at DESC);
CREATE TABLE assignment_versions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 assignment_id uuid NOT NULL, version_number integer NOT NULL CHECK(version_number>0), instructions text NOT NULL,
 max_score numeric(10,2) NOT NULL CHECK(max_score>0),
 exemplar_threshold_percent numeric(5,2) NOT NULL CHECK(exemplar_threshold_percent BETWEEN 0 AND 100),
 scoring_policy jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(scoring_policy)='object'),
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','retired')),
 published_at timestamptz, created_by uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,assignment_id,version_number),
 FOREIGN KEY(organization_id,assignment_id) REFERENCES assignments(organization_id,id),
 FOREIGN KEY(organization_id,created_by) REFERENCES memberships(organization_id,user_id),
 CHECK((status='draft' AND published_at IS NULL) OR (status IN ('published','retired') AND published_at IS NOT NULL))
);
CREATE TABLE rubric_criteria (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 assignment_version_id uuid NOT NULL, criterion_key text NOT NULL, title text NOT NULL, description text NOT NULL,
 max_points numeric(10,2) NOT NULL CHECK(max_points>0), position integer NOT NULL CHECK(position>=0),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,id,assignment_version_id),
 UNIQUE(organization_id,assignment_version_id,criterion_key), UNIQUE(organization_id,assignment_version_id,position),
 FOREIGN KEY(organization_id,assignment_version_id) REFERENCES assignment_versions(organization_id,id)
);
CREATE TABLE reference_solutions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 assignment_version_id uuid NOT NULL, title text NOT NULL, answer_text text, created_by uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,id,assignment_version_id),
 FOREIGN KEY(organization_id,assignment_version_id) REFERENCES assignment_versions(organization_id,id),
 FOREIGN KEY(organization_id,created_by) REFERENCES memberships(organization_id,user_id)
);
CREATE TABLE file_assets (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 storage_backend text NOT NULL, bucket_name text NOT NULL, object_key text NOT NULL,
 original_filename text NOT NULL, content_type text NOT NULL, size_bytes bigint NOT NULL CHECK(size_bytes>=0),
 sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), uploaded_by uuid NOT NULL,
 parent_archive_id uuid, archive_entry_path text,
 processing_status text NOT NULL DEFAULT 'uploaded' CHECK(processing_status IN ('uploaded','scanning','extracting','ready','quarantined','failed')),
 error_code text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,storage_backend,bucket_name,object_key),
 FOREIGN KEY(organization_id,uploaded_by) REFERENCES memberships(organization_id,user_id),
 FOREIGN KEY(organization_id,parent_archive_id) REFERENCES file_assets(organization_id,id),
 CHECK((parent_archive_id IS NULL)=(archive_entry_path IS NULL))
);
CREATE INDEX file_assets_hash_idx ON file_assets(organization_id,sha256);
CREATE TABLE reference_solution_files (
 organization_id uuid NOT NULL REFERENCES organizations(id), reference_solution_id uuid NOT NULL,
 file_asset_id uuid NOT NULL, position integer NOT NULL CHECK(position>=0),
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(organization_id,reference_solution_id,file_asset_id),
 UNIQUE(organization_id,reference_solution_id,position),
 FOREIGN KEY(organization_id,reference_solution_id) REFERENCES reference_solutions(organization_id,id),
 FOREIGN KEY(organization_id,file_asset_id) REFERENCES file_assets(organization_id,id)
);
CREATE INDEX reference_solution_files_asset_idx ON reference_solution_files(organization_id,file_asset_id);
CREATE TABLE submissions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 assignment_version_id uuid NOT NULL, student_id uuid NOT NULL, attempt_number integer NOT NULL CHECK(attempt_number>0),
 submitted_by uuid NOT NULL, submitted_at timestamptz,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','processing','ready','failed','withdrawn')),
 idempotency_key text NOT NULL, current_published_grade_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,id,assignment_version_id),
 UNIQUE(organization_id,assignment_version_id,student_id,attempt_number),
 UNIQUE(organization_id,submitted_by,idempotency_key),
 FOREIGN KEY(organization_id,assignment_version_id) REFERENCES assignment_versions(organization_id,id),
 FOREIGN KEY(organization_id,student_id) REFERENCES students(organization_id,id),
 FOREIGN KEY(organization_id,submitted_by) REFERENCES memberships(organization_id,user_id),
 CHECK((status='draft' AND submitted_at IS NULL) OR (status<>'draft' AND submitted_at IS NOT NULL))
);
CREATE INDEX submissions_version_idx ON submissions(organization_id,assignment_version_id,submitted_at DESC,id);
CREATE INDEX submissions_student_idx ON submissions(organization_id,student_id,submitted_at DESC,id);
CREATE TABLE submission_files (
 organization_id uuid NOT NULL REFERENCES organizations(id), submission_id uuid NOT NULL, file_asset_id uuid NOT NULL,
 position integer NOT NULL CHECK(position>=0), created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(organization_id,submission_id,file_asset_id), UNIQUE(organization_id,submission_id,position),
 FOREIGN KEY(organization_id,submission_id) REFERENCES submissions(organization_id,id),
 FOREIGN KEY(organization_id,file_asset_id) REFERENCES file_assets(organization_id,id)
);
CREATE INDEX submission_files_asset_idx ON submission_files(organization_id,file_asset_id);

CREATE TABLE embedding_profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), provider text NOT NULL, model_name text NOT NULL,
 model_revision text NOT NULL, dimensions integer NOT NULL CHECK(dimensions=1536),
 distance_metric text NOT NULL CHECK(distance_metric='cosine'), preprocessing_version text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(provider,model_name,model_revision,dimensions,distance_metric,preprocessing_version)
);
CREATE TABLE grading_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 submission_id uuid NOT NULL, assignment_version_id uuid NOT NULL,
 run_number integer NOT NULL CHECK(run_number>0),
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
 requested_by uuid NOT NULL, llm_provider text NOT NULL, llm_model text NOT NULL, model_revision text,
 prompt_template_version text NOT NULL, prompt_snapshot text NOT NULL,
 generation_parameters jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(generation_parameters)='object'),
 embedding_profile_id uuid REFERENCES embedding_profiles(id),
 retrieval_policy jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(retrieval_policy)='object'),
 idempotency_key text NOT NULL, attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
 lease_expires_at timestamptz, started_at timestamptz, completed_at timestamptz,
 error_code text, error_message text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,id,assignment_version_id),
 UNIQUE(organization_id,submission_id,run_number), UNIQUE(organization_id,idempotency_key),
 FOREIGN KEY(organization_id,submission_id,assignment_version_id) REFERENCES submissions(organization_id,id,assignment_version_id),
 FOREIGN KEY(organization_id,requested_by) REFERENCES memberships(organization_id,user_id)
);
CREATE UNIQUE INDEX grading_runs_active_idx ON grading_runs(organization_id,submission_id) WHERE status IN ('queued','running');
CREATE INDEX grading_runs_recent_idx ON grading_runs(organization_id,submission_id,created_at DESC);
CREATE TABLE ai_evaluations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 grading_run_id uuid NOT NULL, assignment_version_id uuid NOT NULL,
 total_score numeric(10,2) NOT NULL CHECK(total_score>=0), feedback text NOT NULL,
 output_schema_version text NOT NULL, raw_response jsonb NOT NULL,
 input_tokens bigint CHECK(input_tokens>=0), output_tokens bigint CHECK(output_tokens>=0),
 cost_amount numeric(18,8) CHECK(cost_amount>=0), cost_currency char(3), provider_request_id text,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,id,assignment_version_id), UNIQUE(organization_id,grading_run_id),
 FOREIGN KEY(organization_id,grading_run_id,assignment_version_id) REFERENCES grading_runs(organization_id,id,assignment_version_id)
);
CREATE TABLE ai_criterion_scores (
 organization_id uuid NOT NULL REFERENCES organizations(id), ai_evaluation_id uuid NOT NULL,
 assignment_version_id uuid NOT NULL, rubric_criterion_id uuid NOT NULL,
 score numeric(10,2) NOT NULL CHECK(score>=0), feedback text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(organization_id,ai_evaluation_id,rubric_criterion_id),
 FOREIGN KEY(organization_id,ai_evaluation_id,assignment_version_id) REFERENCES ai_evaluations(organization_id,id,assignment_version_id),
 FOREIGN KEY(organization_id,rubric_criterion_id,assignment_version_id) REFERENCES rubric_criteria(organization_id,id,assignment_version_id)
);
CREATE INDEX ai_scores_criterion_idx ON ai_criterion_scores(organization_id,rubric_criterion_id);
CREATE TABLE grade_revisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 submission_id uuid NOT NULL, assignment_version_id uuid NOT NULL,
 revision_number integer NOT NULL CHECK(revision_number>0), based_on_ai_evaluation_id uuid,
 supersedes_revision_id uuid, reviewed_by uuid NOT NULL, total_score numeric(10,2) NOT NULL CHECK(total_score>=0),
 feedback text NOT NULL, review_reason text,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')), published_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,id,assignment_version_id),
 UNIQUE(organization_id,id,submission_id,assignment_version_id), UNIQUE(organization_id,submission_id,revision_number),
 FOREIGN KEY(organization_id,submission_id,assignment_version_id) REFERENCES submissions(organization_id,id,assignment_version_id),
 FOREIGN KEY(organization_id,based_on_ai_evaluation_id,assignment_version_id) REFERENCES ai_evaluations(organization_id,id,assignment_version_id),
 FOREIGN KEY(organization_id,supersedes_revision_id,submission_id,assignment_version_id) REFERENCES grade_revisions(organization_id,id,submission_id,assignment_version_id),
 FOREIGN KEY(organization_id,reviewed_by) REFERENCES memberships(organization_id,user_id),
 CHECK((status='draft' AND published_at IS NULL) OR (status='published' AND published_at IS NOT NULL))
);
ALTER TABLE submissions ADD CONSTRAINT submissions_current_grade_fk
 FOREIGN KEY(organization_id,current_published_grade_id, id,assignment_version_id)
 REFERENCES grade_revisions(organization_id,id,submission_id,assignment_version_id) DEFERRABLE INITIALLY IMMEDIATE;
CREATE TABLE grade_criterion_scores (
 organization_id uuid NOT NULL REFERENCES organizations(id), grade_revision_id uuid NOT NULL,
 assignment_version_id uuid NOT NULL, rubric_criterion_id uuid NOT NULL,
 score numeric(10,2) NOT NULL CHECK(score>=0), feedback text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(organization_id,grade_revision_id,rubric_criterion_id),
 FOREIGN KEY(organization_id,grade_revision_id,assignment_version_id) REFERENCES grade_revisions(organization_id,id,assignment_version_id),
 FOREIGN KEY(organization_id,rubric_criterion_id,assignment_version_id) REFERENCES rubric_criteria(organization_id,id,assignment_version_id)
);
CREATE INDEX grade_scores_criterion_idx ON grade_criterion_scores(organization_id,rubric_criterion_id);
CREATE TABLE exemplars (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 grade_revision_id uuid NOT NULL, submission_id uuid NOT NULL, assignment_version_id uuid NOT NULL,
 approved_by uuid NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
 revoked_at timestamptz, revocation_reason text,
 reuse_permission_record text NOT NULL CHECK(length(trim(reuse_permission_record))>0),
 anonymization_version text NOT NULL CHECK(length(trim(anonymization_version))>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,grade_revision_id),
 FOREIGN KEY(organization_id,grade_revision_id,submission_id,assignment_version_id) REFERENCES grade_revisions(organization_id,id,submission_id,assignment_version_id),
 FOREIGN KEY(organization_id,approved_by) REFERENCES memberships(organization_id,user_id),
 CHECK((status='active' AND revoked_at IS NULL) OR (status='revoked' AND revoked_at IS NOT NULL))
);
CREATE INDEX exemplars_active_idx ON exemplars(organization_id,assignment_version_id) WHERE status='active';
CREATE TABLE documents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 file_asset_id uuid, reference_solution_id uuid, submission_id uuid, exemplar_id uuid,
 source_text text, source_content_hash char(64) NOT NULL CHECK(source_content_hash ~ '^[0-9a-f]{64}$'),
 extractor_name text NOT NULL, extractor_version text NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','ready','failed')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id),
 FOREIGN KEY(organization_id,file_asset_id) REFERENCES file_assets(organization_id,id),
 FOREIGN KEY(organization_id,reference_solution_id) REFERENCES reference_solutions(organization_id,id),
 FOREIGN KEY(organization_id,submission_id) REFERENCES submissions(organization_id,id),
 FOREIGN KEY(organization_id,exemplar_id) REFERENCES exemplars(organization_id,id),
 CHECK(num_nonnulls(reference_solution_id,submission_id,exemplar_id)=1),
 CHECK(file_asset_id IS NOT NULL OR source_text IS NOT NULL),
 CHECK(exemplar_id IS NULL OR (file_asset_id IS NULL AND source_text IS NOT NULL))
);
CREATE TABLE document_chunks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 document_id uuid NOT NULL, chunk_index integer NOT NULL CHECK(chunk_index>=0),
 content text NOT NULL, content_hash char(64) NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
 token_count integer NOT NULL CHECK(token_count>=0), locator jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(locator)='object'),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(organization_id,id),
 UNIQUE(organization_id,document_id,chunk_index),
 FOREIGN KEY(organization_id,document_id) REFERENCES documents(organization_id,id)
);
CREATE TABLE chunk_embeddings (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 document_chunk_id uuid NOT NULL, embedding_profile_id uuid NOT NULL REFERENCES embedding_profiles(id),
 embedding vector(1536) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,document_chunk_id,embedding_profile_id),
 FOREIGN KEY(organization_id,document_chunk_id) REFERENCES document_chunks(organization_id,id)
);
CREATE INDEX chunk_embeddings_profile_idx ON chunk_embeddings(embedding_profile_id);
CREATE TABLE retrieval_evidence (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 grading_run_id uuid NOT NULL, document_chunk_id uuid NOT NULL,
 embedding_profile_id uuid NOT NULL REFERENCES embedding_profiles(id),
 exemplar_id uuid, reference_solution_id uuid,
 rank integer NOT NULL CHECK(rank>0), distance double precision NOT NULL CHECK(distance>=0 AND distance<=2),
 retrieved_text_snapshot text NOT NULL,
 source_content_hash char(64) NOT NULL CHECK(source_content_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(organization_id,id),
 UNIQUE(organization_id,grading_run_id,rank),
 FOREIGN KEY(organization_id,grading_run_id) REFERENCES grading_runs(organization_id,id),
 FOREIGN KEY(organization_id,document_chunk_id) REFERENCES document_chunks(organization_id,id),
 FOREIGN KEY(organization_id,exemplar_id) REFERENCES exemplars(organization_id,id),
 FOREIGN KEY(organization_id,reference_solution_id) REFERENCES reference_solutions(organization_id,id),
 CHECK(num_nonnulls(exemplar_id,reference_solution_id)=1)
);
CREATE TABLE processing_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 job_type text NOT NULL CHECK(job_type IN ('scan','extract','embed','grade')),
 file_asset_id uuid, document_id uuid, grading_run_id uuid,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
 deduplication_key text NOT NULL, available_at timestamptz NOT NULL DEFAULT now(),
 attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
 max_attempts integer NOT NULL DEFAULT 3 CHECK(max_attempts>0),
 lease_token uuid, lease_expires_at timestamptz, last_error_code text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,id), UNIQUE(organization_id,deduplication_key),
 FOREIGN KEY(organization_id,file_asset_id) REFERENCES file_assets(organization_id,id),
 FOREIGN KEY(organization_id,document_id) REFERENCES documents(organization_id,id),
 FOREIGN KEY(organization_id,grading_run_id) REFERENCES grading_runs(organization_id,id),
 CHECK((job_type IN ('scan','extract') AND file_asset_id IS NOT NULL AND document_id IS NULL AND grading_run_id IS NULL)
    OR (job_type='embed' AND document_id IS NOT NULL AND file_asset_id IS NULL AND grading_run_id IS NULL)
    OR (job_type='grade' AND grading_run_id IS NOT NULL AND file_asset_id IS NULL AND document_id IS NULL)),
 CHECK(attempt_count<=max_attempts),
 CHECK((lease_token IS NULL)=(lease_expires_at IS NULL))
);
CREATE INDEX processing_jobs_queued_idx ON processing_jobs(available_at,id) WHERE status='queued';
CREATE INDEX processing_jobs_lease_idx ON processing_jobs(lease_expires_at) WHERE status='running';
CREATE TABLE outbox_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 event_type text NOT NULL, payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(payload)='object'),
 available_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz,
 attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(organization_id,id)
);
CREATE INDEX outbox_pending_idx ON outbox_events(available_at,id) WHERE published_at IS NULL;
CREATE TABLE audit_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id),
 actor_user_id uuid REFERENCES users(id), action text NOT NULL, entity_type text NOT NULL,
 entity_id uuid NOT NULL, request_id text, details jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(details)='object'),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(organization_id,id)
);
CREATE INDEX audit_entity_idx ON audit_events(organization_id,entity_type,entity_id,created_at DESC);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['organizations','users','memberships','students','assignments','assignment_versions','file_assets','submissions','grading_runs','grade_revisions','exemplars','documents','processing_jobs'] LOOP
  EXECUTE format('CREATE TRIGGER %I_touch BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_updated_at()',t,t);
 END LOOP;
END $$;

COMMIT;
