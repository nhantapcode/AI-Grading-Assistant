BEGIN;
CREATE OR REPLACE FUNCTION validate_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_doc record; run_version uuid; run_profile uuid; source_version uuid;
BEGIN
 SELECT docs.* INTO source_doc FROM documents docs
  JOIN document_chunks c ON c.organization_id=docs.organization_id AND c.document_id=docs.id
  WHERE c.organization_id=NEW.organization_id AND c.id=NEW.document_chunk_id;
 SELECT assignment_version_id,embedding_profile_id INTO run_version,run_profile FROM grading_runs
  WHERE organization_id=NEW.organization_id AND id=NEW.grading_run_id;
 IF NEW.exemplar_id IS NOT NULL THEN
  SELECT assignment_version_id INTO source_version FROM exemplars WHERE organization_id=NEW.organization_id
   AND id=NEW.exemplar_id AND status='active';
  IF source_doc.exemplar_id IS DISTINCT FROM NEW.exemplar_id THEN RAISE EXCEPTION 'evidence source mismatch'; END IF;
 ELSE
  SELECT assignment_version_id INTO source_version FROM reference_solutions WHERE organization_id=NEW.organization_id
   AND id=NEW.reference_solution_id;
  IF source_doc.reference_solution_id IS DISTINCT FROM NEW.reference_solution_id THEN RAISE EXCEPTION 'evidence source mismatch'; END IF;
 END IF;
 IF source_version IS DISTINCT FROM run_version OR source_doc.status<>'ready' THEN
  RAISE EXCEPTION 'evidence must be ready and from evaluated version'; END IF;
 IF run_profile IS DISTINCT FROM NEW.embedding_profile_id OR NOT EXISTS (
  SELECT 1 FROM chunk_embeddings WHERE organization_id=NEW.organization_id
   AND document_chunk_id=NEW.document_chunk_id AND embedding_profile_id=NEW.embedding_profile_id
 ) THEN RAISE EXCEPTION 'evidence embedding profile mismatch'; END IF;
 RETURN NEW;
END $$;
COMMIT;
