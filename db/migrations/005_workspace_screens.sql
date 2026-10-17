BEGIN;
ALTER TABLE memberships ADD COLUMN display_name_override text CHECK (display_name_override IS NULL OR length(trim(display_name_override)) BETWEEN 1 AND 120);
ALTER TABLE file_assets ADD COLUMN purpose text CHECK (purpose IN ('assignment','reference','submission'));
ALTER TABLE file_assets ADD COLUMN target_assignment_id uuid;
ALTER TABLE file_assets ADD CONSTRAINT file_assignment_fk FOREIGN KEY (organization_id,target_assignment_id) REFERENCES assignments(organization_id,id);
ALTER TABLE submissions ADD COLUMN request_hash char(64);
CREATE TABLE assignment_version_files (
 organization_id uuid NOT NULL,
 assignment_version_id uuid NOT NULL,
 file_asset_id uuid NOT NULL,
 position integer NOT NULL CHECK (position>=0),
 PRIMARY KEY (organization_id,assignment_version_id,file_asset_id),
 UNIQUE (organization_id,assignment_version_id,position),
 FOREIGN KEY (organization_id,assignment_version_id) REFERENCES assignment_versions(organization_id,id),
 FOREIGN KEY (organization_id,file_asset_id) REFERENCES file_assets(organization_id,id)
);
CREATE TRIGGER assignment_files_version_guard BEFORE INSERT OR UPDATE OR DELETE ON assignment_version_files
 FOR EACH ROW EXECUTE FUNCTION guard_version_child();
CREATE TABLE file_extractions (
 organization_id uuid NOT NULL,
 file_asset_id uuid NOT NULL,
 extracted_text text NOT NULL,
 extractor_version text NOT NULL DEFAULT 'v1',
 PRIMARY KEY (organization_id,file_asset_id),
 FOREIGN KEY (organization_id,file_asset_id) REFERENCES file_assets(organization_id,id)
);
CREATE FUNCTION guard_publish_files() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.status='published' AND OLD.status='draft' THEN
  IF EXISTS (
   SELECT 1 FROM file_assets f WHERE f.organization_id=NEW.organization_id AND f.processing_status<>'ready'
    AND (EXISTS (SELECT 1 FROM assignment_version_files af WHERE af.organization_id=f.organization_id AND af.file_asset_id=f.id AND af.assignment_version_id=NEW.id)
     OR EXISTS (SELECT 1 FROM reference_solution_files rf JOIN reference_solutions r ON r.organization_id=rf.organization_id AND r.id=rf.reference_solution_id
       WHERE rf.organization_id=f.organization_id AND rf.file_asset_id=f.id AND r.assignment_version_id=NEW.id))
  ) THEN RAISE EXCEPTION 'All assignment and answer key files must be ready'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER assignment_publish_files_guard BEFORE UPDATE ON assignment_versions FOR EACH ROW EXECUTE FUNCTION guard_publish_files();
CREATE INDEX file_assets_assignment_idx ON file_assets(organization_id,target_assignment_id);
COMMIT;
