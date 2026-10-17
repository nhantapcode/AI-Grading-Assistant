-- Development-only, repeatable sample records. No real student data or storage objects.
\set ON_ERROR_STOP on
BEGIN;
SELECT NOT EXISTS (SELECT 1 FROM organizations WHERE id='10000000-0000-0000-0000-000000000001') AS seed_needed \gset
\if :seed_needed

INSERT INTO organizations(id,name)
VALUES ('10000000-0000-0000-0000-000000000001','Demo Training Center')
ON CONFLICT (id) DO NOTHING;

INSERT INTO users(id,email,display_name,password_hash)
VALUES ('10000000-0000-0000-0000-000000000002','trainer@demo.example','Alex Trainer','DEMO_ACCOUNT_NO_LOGIN')
ON CONFLICT (id) DO NOTHING;

INSERT INTO memberships(organization_id,user_id,role)
VALUES ('10000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002','trainer')
ON CONFLICT (organization_id,user_id) DO NOTHING;

INSERT INTO students(id,organization_id,external_student_id,display_name,email)
VALUES
 ('10000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000001','DEMO-001','Sam Nguyen','sam@demo.example'),
 ('10000000-0000-0000-0000-000000000004','10000000-0000-0000-0000-000000000001','DEMO-002','Taylor Tran',NULL)
ON CONFLICT (id) DO NOTHING;

INSERT INTO assignments(id,organization_id,title,description,created_by,status)
VALUES ('10000000-0000-0000-0000-000000000005','10000000-0000-0000-0000-000000000001',
 'Explain database indexes','Short written exercise about PostgreSQL indexes.',
 '10000000-0000-0000-0000-000000000002','active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO assignment_versions(id,organization_id,assignment_id,version_number,instructions,max_score,
 exemplar_threshold_percent,scoring_policy,created_by)
VALUES ('10000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000005',1,
 'Explain when a PostgreSQL B-tree index helps and name one trade-off.',20,80,
 '{"rounding":"two_decimal_places","partial_credit":true}'::jsonb,
 '10000000-0000-0000-0000-000000000002')
ON CONFLICT (id) DO NOTHING;

INSERT INTO rubric_criteria(id,organization_id,assignment_version_id,criterion_key,title,description,max_points,position)
VALUES
 ('10000000-0000-0000-0000-000000000007','10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000006','use_case','Index use case',
  'Describes how a B-tree index helps selective equality or range queries.',10,0),
 ('10000000-0000-0000-0000-000000000008','10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000006','tradeoff','Index trade-off',
  'Mentions write overhead or extra storage.',10,1)
ON CONFLICT (id) DO NOTHING;

INSERT INTO reference_solutions(id,organization_id,assignment_version_id,title,answer_text,created_by)
VALUES ('10000000-0000-0000-0000-000000000009','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000006','Trainer answer key',
 'A B-tree index speeds selective equality and range lookups by avoiding a full table scan. It uses disk space and adds maintenance work to inserts, updates, and deletes.',
 '10000000-0000-0000-0000-000000000002')
ON CONFLICT (id) DO NOTHING;

UPDATE assignment_versions SET status='published'
WHERE id='10000000-0000-0000-0000-000000000006' AND status='draft';

INSERT INTO submissions(id,organization_id,assignment_version_id,student_id,attempt_number,submitted_by,
 idempotency_key,status,submitted_at)
VALUES
 ('10000000-0000-0000-0000-000000000010','10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000003',1,
  '10000000-0000-0000-0000-000000000002','demo-submission-1','ready',now()),
 ('10000000-0000-0000-0000-000000000011','10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000004',1,
  '10000000-0000-0000-0000-000000000002','demo-submission-2','ready',now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO embedding_profiles(id,provider,model_name,model_revision,dimensions,distance_metric,preprocessing_version)
VALUES ('10000000-0000-0000-0000-000000000012','demo','deterministic-demo-vector','v1',1536,'cosine','v1')
ON CONFLICT (id) DO NOTHING;

INSERT INTO documents(id,organization_id,reference_solution_id,source_text,source_content_hash,
 extractor_name,extractor_version,status)
VALUES ('10000000-0000-0000-0000-000000000013','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000009',
 'A B-tree index helps selective lookups but adds write and storage overhead.',
 encode(digest('A B-tree index helps selective lookups but adds write and storage overhead.','sha256'),'hex'),
 'demo-inline','v1','ready')
ON CONFLICT (id) DO NOTHING;

INSERT INTO document_chunks(id,organization_id,document_id,chunk_index,content,content_hash,token_count,locator)
VALUES ('10000000-0000-0000-0000-000000000014','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000013',0,
 'A B-tree index helps selective lookups but adds write and storage overhead.',
 encode(digest('A B-tree index helps selective lookups but adds write and storage overhead.','sha256'),'hex'),
 15,'{"section":"answer key"}'::jsonb)
ON CONFLICT (id) DO NOTHING;

INSERT INTO chunk_embeddings(id,organization_id,document_chunk_id,embedding_profile_id,embedding)
VALUES ('10000000-0000-0000-0000-000000000015','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000014','10000000-0000-0000-0000-000000000012',
 ('[1,' || repeat('0,',1534) || '0]')::vector(1536))
ON CONFLICT (id) DO NOTHING;

INSERT INTO grading_runs(id,organization_id,submission_id,assignment_version_id,run_number,status,
 requested_by,llm_provider,llm_model,prompt_template_version,prompt_snapshot,generation_parameters,
 embedding_profile_id,retrieval_policy,idempotency_key,attempt_count,started_at)
VALUES ('10000000-0000-0000-0000-000000000016','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000010','10000000-0000-0000-0000-000000000006',1,'running',
 '10000000-0000-0000-0000-000000000002','demo','sample-only','v1',
 'Synthetic demo prompt; no external model was called.','{"temperature":0}'::jsonb,
 '10000000-0000-0000-0000-000000000012','{"top_k":1,"source":"reference"}'::jsonb,
 'demo-run-1',1,now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO retrieval_evidence(id,organization_id,grading_run_id,document_chunk_id,embedding_profile_id,
 reference_solution_id,rank,distance,retrieved_text_snapshot,source_content_hash)
VALUES ('10000000-0000-0000-0000-000000000017','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000016','10000000-0000-0000-0000-000000000014',
 '10000000-0000-0000-0000-000000000012','10000000-0000-0000-0000-000000000009',1,0.1,
 'A B-tree index helps selective lookups but adds write and storage overhead.',
 encode(digest('A B-tree index helps selective lookups but adds write and storage overhead.','sha256'),'hex'))
ON CONFLICT (id) DO NOTHING;

INSERT INTO ai_evaluations(id,organization_id,grading_run_id,assignment_version_id,total_score,feedback,
 output_schema_version,raw_response,input_tokens,output_tokens)
VALUES ('10000000-0000-0000-0000-000000000018','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000016','10000000-0000-0000-0000-000000000006',17,
 'Good explanation of the use case; expand the write-cost discussion.','demo-v1',
 '{"note":"synthetic example; no model call"}'::jsonb,120,45)
ON CONFLICT (id) DO NOTHING;

INSERT INTO ai_criterion_scores(organization_id,ai_evaluation_id,assignment_version_id,rubric_criterion_id,score,feedback)
VALUES
 ('10000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000018',
  '10000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000007',9,'Correct selective-query example.'),
 ('10000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000018',
  '10000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000008',8,'Mentions write overhead.')
ON CONFLICT (organization_id,ai_evaluation_id,rubric_criterion_id) DO NOTHING;

UPDATE grading_runs SET status='succeeded' WHERE id='10000000-0000-0000-0000-000000000016' AND status='running';

INSERT INTO grade_revisions(id,organization_id,submission_id,assignment_version_id,revision_number,
 based_on_ai_evaluation_id,reviewed_by,total_score,feedback,review_reason)
VALUES ('10000000-0000-0000-0000-000000000019','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000010','10000000-0000-0000-0000-000000000006',1,
 '10000000-0000-0000-0000-000000000018','10000000-0000-0000-0000-000000000002',18,
 'Clear answer. The index trade-off is explained correctly.',
 'Trainer credited the specific explanation of insert overhead.')
ON CONFLICT (id) DO NOTHING;

INSERT INTO grade_criterion_scores(organization_id,grade_revision_id,assignment_version_id,rubric_criterion_id,score,feedback)
VALUES
 ('10000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000019',
  '10000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000007',10,'Accurate example.'),
 ('10000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000019',
  '10000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000008',8,'Correct trade-off.')
ON CONFLICT (organization_id,grade_revision_id,rubric_criterion_id) DO NOTHING;

UPDATE grade_revisions SET status='published'
WHERE id='10000000-0000-0000-0000-000000000019' AND status='draft';

INSERT INTO exemplars(id,organization_id,grade_revision_id,submission_id,assignment_version_id,
 approved_by,reuse_permission_record,anonymization_version)
VALUES ('10000000-0000-0000-0000-000000000020','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000019','10000000-0000-0000-0000-000000000010',
 '10000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000002',
 'Synthetic demo content approved for reuse.','demo-v1')
ON CONFLICT (id) DO NOTHING;

INSERT INTO documents(id,organization_id,exemplar_id,source_text,source_content_hash,
 extractor_name,extractor_version,status)
VALUES ('10000000-0000-0000-0000-000000000021','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000020',
 'A B-tree index can speed a selective WHERE lookup. It costs space and makes inserts slower.',
 encode(digest('A B-tree index can speed a selective WHERE lookup. It costs space and makes inserts slower.','sha256'),'hex'),
 'demo-anonymizer','v1','ready')
ON CONFLICT (id) DO NOTHING;

INSERT INTO document_chunks(id,organization_id,document_id,chunk_index,content,content_hash,token_count,locator)
VALUES ('10000000-0000-0000-0000-000000000022','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000021',0,
 'A B-tree index can speed a selective WHERE lookup. It costs space and makes inserts slower.',
 encode(digest('A B-tree index can speed a selective WHERE lookup. It costs space and makes inserts slower.','sha256'),'hex'),
 18,'{"section":"approved exemplar"}'::jsonb)
ON CONFLICT (id) DO NOTHING;

INSERT INTO chunk_embeddings(id,organization_id,document_chunk_id,embedding_profile_id,embedding)
VALUES ('10000000-0000-0000-0000-000000000023','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000022','10000000-0000-0000-0000-000000000012',
 ('[1,' || repeat('0,',1534) || '0]')::vector(1536))
ON CONFLICT (id) DO NOTHING;

\endif
COMMIT;
