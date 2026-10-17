from uuid import UUID

from psycopg import Connection


class MembershipRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    def organizations(self, user_id: UUID) -> list[dict]:
        return self.db.execute("""SELECT o.id, o.name, m.role FROM memberships m
            JOIN organizations o ON o.id=m.organization_id
            WHERE m.user_id=%s AND m.status='active' AND o.status='active' ORDER BY o.name""", (user_id,)).fetchall()

    def manager_role(self, organization_id: UUID, user_id: UUID) -> str | None:
        # Locks prevent membership revocation racing with invitation creation/acceptance.
        row = self.db.execute("""SELECT m.role FROM memberships m JOIN organizations o ON o.id=m.organization_id
            JOIN users u ON u.id=m.user_id
            WHERE m.organization_id=%s AND m.user_id=%s AND m.status='active' AND o.status='active' AND u.status='active'
            FOR SHARE OF m,o,u""", (organization_id, user_id)).fetchone()
        return row["role"] if row else None

    def members(self, organization_id: UUID) -> list[dict]:
        return self.db.execute("""SELECT u.id,u.email,coalesce(m.display_name_override,u.display_name) AS display_name,m.role,m.status FROM memberships m
            JOIN users u ON u.id=m.user_id WHERE m.organization_id=%s ORDER BY u.display_name""", (organization_id,)).fetchall()

    def add(self, organization_id: UUID, user_id: UUID, role: str) -> bool:
        return self.db.execute("""INSERT INTO memberships(organization_id,user_id,role) VALUES (%s,%s,%s)
            ON CONFLICT (organization_id,user_id) DO NOTHING RETURNING user_id""", (organization_id,user_id,role)).fetchone() is not None
