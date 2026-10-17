BEGIN;
CREATE TABLE auth_rate_limits (
 key_hash char(64) PRIMARY KEY CHECK (key_hash ~ '^[0-9a-f]{64}$'),
 request_count integer NOT NULL CHECK (request_count>0),
 expires_at timestamptz NOT NULL
);
CREATE INDEX auth_rate_limits_expiry_idx ON auth_rate_limits(expires_at);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['account_invitations','assignment_version_files','file_extractions'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (organization_id=tenant_context()) WITH CHECK (organization_id=tenant_context())',t);
 END LOOP;
END $$;
COMMIT;
