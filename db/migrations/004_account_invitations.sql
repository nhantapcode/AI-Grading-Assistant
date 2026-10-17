BEGIN;
CREATE TABLE account_invitations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id uuid NOT NULL REFERENCES organizations(id),
 email text NOT NULL CHECK (email=lower(trim(email)) AND length(email)>0),
 role text NOT NULL CHECK (role IN ('admin','trainer')),
 token_hash text NOT NULL UNIQUE,
 invited_by uuid NOT NULL REFERENCES users(id),
 expires_at timestamptz NOT NULL,
 accepted_at timestamptz,
 revoked_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (expires_at>created_at),
 CHECK (accepted_at IS NULL OR revoked_at IS NULL)
);
CREATE INDEX account_invitations_org_idx ON account_invitations(organization_id, created_at DESC);
COMMIT;
