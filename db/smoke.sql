\set ON_ERROR_STOP on
BEGIN;
INSERT INTO organizations(id,name) VALUES('00000000-0000-0000-0000-000000000001','Smoke');
INSERT INTO users(id,email,display_name,password_hash) VALUES('00000000-0000-0000-0000-000000000002','trainer@example.test','Trainer','test-hash');
INSERT INTO memberships(organization_id,user_id,role) VALUES('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','trainer');
INSERT INTO students(id,organization_id,external_student_id,display_name)
 VALUES('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000001','S1','Student');
INSERT INTO assignments(id,organization_id,title,created_by)
 VALUES('00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000001','Essay','00000000-0000-0000-0000-000000000002');
INSERT INTO assignment_versions(id,organization_id,assignment_id,version_number,instructions,max_score,exemplar_threshold_percent,created_by)
 VALUES('00000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000004',1,'Write an essay',10,80,'00000000-0000-0000-0000-000000000002');
INSERT INTO rubric_criteria(id,organization_id,assignment_version_id,criterion_key,title,description,max_points,position)
 VALUES('00000000-0000-0000-0000-000000000006','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000005','quality','Quality','Quality of answer',10,0);
INSERT INTO reference_solutions(organization_id,assignment_version_id,title,answer_text,created_by)
 VALUES('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000005','Example','A good answer','00000000-0000-0000-0000-000000000002');
UPDATE assignment_versions SET status='published' WHERE id='00000000-0000-0000-0000-000000000005';
INSERT INTO submissions(id,organization_id,assignment_version_id,student_id,attempt_number,submitted_by,idempotency_key)
 VALUES('00000000-0000-0000-0000-000000000007','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000003',1,'00000000-0000-0000-0000-000000000002','smoke-1');
UPDATE submissions SET status='ready' WHERE id='00000000-0000-0000-0000-000000000007';
INSERT INTO grade_revisions(id,organization_id,submission_id,assignment_version_id,revision_number,reviewed_by,total_score,feedback)
 VALUES('00000000-0000-0000-0000-000000000008','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000007','00000000-0000-0000-0000-000000000005',1,'00000000-0000-0000-0000-000000000002',9,'Good work');
INSERT INTO grade_criterion_scores(organization_id,grade_revision_id,assignment_version_id,rubric_criterion_id,score,feedback)
 VALUES('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000008','00000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000006',9,'Good work');
UPDATE grade_revisions SET status='published' WHERE id='00000000-0000-0000-0000-000000000008';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM submissions WHERE id='00000000-0000-0000-0000-000000000007' AND current_published_grade_id='00000000-0000-0000-0000-000000000008')
 THEN RAISE EXCEPTION 'published grade pointer missing'; END IF; END $$;
INSERT INTO account_invitations(id,organization_id,email,role,token_hash,invited_by,expires_at)
 VALUES('00000000-0000-0000-0000-000000000009','00000000-0000-0000-0000-000000000001','invitee@example.test','trainer',
 encode(digest('smoke-invitation','sha256'),'hex'),'00000000-0000-0000-0000-000000000002',now()+interval '48 hours');
DO $$ BEGIN
 BEGIN
  INSERT INTO account_invitations(organization_id,email,role,token_hash,invited_by,expires_at)
   VALUES('00000000-0000-0000-0000-000000000001','duplicate@example.test','trainer',encode(digest('smoke-invitation','sha256'),'hex'),
    '00000000-0000-0000-0000-000000000002',now()+interval '48 hours');
  RAISE EXCEPTION 'duplicate invitation token was accepted';
 EXCEPTION WHEN unique_violation THEN NULL; END;
 BEGIN
  UPDATE account_invitations SET accepted_at=now(),revoked_at=now() WHERE id='00000000-0000-0000-0000-000000000009';
  RAISE EXCEPTION 'accepted and revoked markers were both accepted';
 EXCEPTION WHEN check_violation THEN NULL; END;
END $$;
UPDATE account_invitations SET revoked_at=now() WHERE id='00000000-0000-0000-0000-000000000009';
ROLLBACK;
