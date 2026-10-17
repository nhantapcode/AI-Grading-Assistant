from uuid import UUID

from psycopg import Connection

from app.models.invitation import Invitation

FIELDS = "id,organization_id,email,role,expires_at,accepted_at,revoked_at,created_at,invited_by"


class InvitationRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    def create(self, organization_id: UUID, email: str, role: str, digest: str, invited_by: UUID) -> Invitation:
        row = self.db.execute(f"""INSERT INTO account_invitations(organization_id,email,role,token_hash,invited_by,expires_at)
            VALUES (%s,%s,%s,%s,%s,now()+interval '48 hours') RETURNING {FIELDS}""",
            (organization_id,email,role,digest,invited_by)).fetchone()
        return Invitation(**row)

    def list(self, organization_id: UUID) -> list[Invitation]:
        rows = self.db.execute(f"SELECT {FIELDS} FROM account_invitations WHERE organization_id=%s ORDER BY created_at DESC", (organization_id,)).fetchall()
        for row in rows:
            actor = self.db.execute('SELECT display_name FROM users WHERE id=%s', (row['invited_by'],)).fetchone()
            row['invited_by_name'] = actor['display_name'] if actor else 'Unknown'
        return [Invitation(**row) for row in rows]

    def lock_token(self, digest: str) -> tuple[Invitation, UUID, str] | None:
        row = self.db.execute(f"SELECT {FIELDS},invited_by FROM account_invitations WHERE token_hash=%s FOR UPDATE", (digest,)).fetchone()
        if not row:
            return None
        invited_by = row.pop("invited_by")
        org = self.db.execute("SELECT name FROM organizations WHERE id=%s", (row["organization_id"],)).fetchone()
        return Invitation(**row), invited_by, org["name"]

    def accept(self, invitation_id: UUID) -> None:
        self.db.execute("UPDATE account_invitations SET accepted_at=now() WHERE id=%s", (invitation_id,))

    def revoke(self, organization_id: UUID, invitation_id: UUID) -> bool:
        return self.db.execute("""UPDATE account_invitations SET revoked_at=now()
            WHERE id=%s AND organization_id=%s AND accepted_at IS NULL AND revoked_at IS NULL RETURNING id""",
            (invitation_id,organization_id)).fetchone() is not None

    def find_user(self, email: str) -> dict | None:
        return self.db.execute("SELECT id,status FROM users WHERE email=%s", (email,)).fetchone()

    def create_user(self, email: str, name: str, encoded_password: str) -> UUID | None:
        row = self.db.execute("""INSERT INTO users(email,display_name,password_hash) VALUES (%s,%s,%s)
            ON CONFLICT (email) DO NOTHING RETURNING id""", (email,name,encoded_password)).fetchone()
        return row["id"] if row else None
