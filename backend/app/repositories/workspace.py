from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.models.workspace import OrganizationAccess


class WorkspaceRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    def access(self, org: UUID, user: UUID) -> OrganizationAccess | None:
        row = self.db.execute("""SELECT m.role FROM memberships m JOIN organizations o ON o.id=m.organization_id
            JOIN users u ON u.id=m.user_id WHERE m.organization_id=%s AND m.user_id=%s
            AND m.status='active' AND o.status='active' AND u.status='active' FOR SHARE OF m,o,u""", (org,user)).fetchone()
        return OrganizationAccess(org,user,row['role']) if row else None

    def audit(self, access: OrganizationAccess, action: str, entity_type: str, entity_id: UUID) -> None:
        self.db.execute("INSERT INTO audit_events(organization_id,actor_user_id,action,entity_type,entity_id) VALUES (%s,%s,%s,%s,%s)",
                        (access.organization_id,access.user_id,action,entity_type,entity_id))

    def event(self, org: UUID, event: str, payload: dict) -> None:
        self.db.execute("INSERT INTO outbox_events(organization_id,event_type,payload) VALUES (%s,%s,%s)", (org,event,Jsonb(payload)))

    def members(self, org: UUID, search: str, role: str, status: str, page: int, limit: int) -> dict:
        where = "m.organization_id=%s AND (u.email ILIKE %s OR coalesce(m.display_name_override,u.display_name) ILIKE %s) AND (%s='' OR m.role=%s) AND (%s='' OR m.status=%s)"
        args = (org,f'%{search}%',f'%{search}%',role,role,status,status)
        total = self.db.execute(f"SELECT count(*) AS n FROM memberships m JOIN users u ON u.id=m.user_id WHERE {where}", args).fetchone()['n']
        items = self.db.execute(f"""SELECT u.id,u.email,coalesce(m.display_name_override,u.display_name) AS display_name,
            m.display_name_override,m.role,m.status,m.created_at,m.updated_at FROM memberships m JOIN users u ON u.id=m.user_id
            WHERE {where} ORDER BY m.created_at,u.id LIMIT %s OFFSET %s""", (*args,limit,(page-1)*limit)).fetchall()
        return {'items':items,'total':total,'page':page,'limit':limit}

    def member(self, org: UUID, user: UUID) -> dict | None:
        return self.db.execute("SELECT * FROM memberships WHERE organization_id=%s AND user_id=%s FOR UPDATE", (org,user)).fetchone()

    def change_member(self, org: UUID, user: UUID, role: str, name: str | None, status: str) -> dict:
        return self.db.execute("""UPDATE memberships SET role=%s,display_name_override=%s,status=%s
            WHERE organization_id=%s AND user_id=%s RETURNING *""", (role,name,status,org,user)).fetchone()

    def revoke_invitations(self, org: UUID, user: UUID) -> None:
        self.db.execute("UPDATE account_invitations SET revoked_at=now() WHERE organization_id=%s AND invited_by=%s AND accepted_at IS NULL AND revoked_at IS NULL", (org,user))
