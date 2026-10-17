from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg import Connection

from app.models.workspace import OrganizationAccess
from app.schemas.workspace import VersionInput, StudentInput, SubmissionInput


class AssignmentRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    def authors(self, access: OrganizationAccess) -> list[dict]:
        return self.db.execute("""SELECT DISTINCT u.id,coalesce(m.display_name_override,u.display_name) AS display_name
            FROM assignments a JOIN users u ON u.id=a.created_by JOIN memberships m ON m.organization_id=a.organization_id AND m.user_id=a.created_by
            WHERE a.organization_id=%s AND (%s OR a.created_by=%s OR EXISTS (SELECT 1 FROM assignment_versions v WHERE v.assignment_id=a.id AND v.status<>'draft'))
            ORDER BY display_name""", (access.organization_id,access.is_manager,access.user_id)).fetchall()

    def list(self, access: OrganizationAccess, search: str, author: UUID | None, status: str, since: datetime | None, page: int, limit: int) -> dict:
        where = """a.organization_id=%s AND a.title ILIKE %s AND (%s OR a.created_by=%s OR EXISTS
            (SELECT 1 FROM assignment_versions v WHERE v.organization_id=a.organization_id AND v.assignment_id=a.id AND v.status<>'draft'))
            AND (%s::uuid IS NULL OR a.created_by=%s) AND (%s='' OR a.status=%s) AND (%s::timestamptz IS NULL OR a.updated_at>=%s)"""
        args = (access.organization_id,f'%{search}%',access.is_manager,access.user_id,author,author,status,status,since,since)
        total = self.db.execute(f"SELECT count(*) AS n FROM assignments a WHERE {where}", args).fetchone()['n']
        items = self.db.execute(f"""SELECT a.*,coalesce(m.display_name_override,u.display_name) AS author,
            (SELECT max(version_number) FROM assignment_versions v WHERE v.assignment_id=a.id AND v.status='published') AS published_version
            FROM assignments a JOIN users u ON u.id=a.created_by JOIN memberships m ON m.user_id=a.created_by AND m.organization_id=a.organization_id
            WHERE {where} ORDER BY a.updated_at DESC,a.id LIMIT %s OFFSET %s""", (*args,limit,(page-1)*limit)).fetchall()
        return {'items':items,'total':total,'page':page,'limit':limit}

    def get(self, org: UUID, assignment: UUID, lock: bool = False) -> dict | None:
        return self.db.execute("SELECT * FROM assignments WHERE organization_id=%s AND id=%s" + (' FOR UPDATE' if lock else ''), (org,assignment)).fetchone()

    def create(self, access: OrganizationAccess, title: str, description: str) -> dict:
        return self.db.execute("""INSERT INTO assignments(organization_id,title,description,created_by)
            VALUES (%s,%s,%s,%s) RETURNING *""", (access.organization_id,title,description,access.user_id)).fetchone()

    def create_version(self, access: OrganizationAccess, assignment: UUID) -> dict:
        return self.db.execute("""INSERT INTO assignment_versions(organization_id,assignment_id,version_number,instructions,max_score,exemplar_threshold_percent,created_by)
            SELECT %s,%s,coalesce(max(version_number),0)+1,'',100,80,%s FROM assignment_versions WHERE organization_id=%s AND assignment_id=%s RETURNING *""",
            (access.organization_id,assignment,access.user_id,access.organization_id,assignment)).fetchone()

    def versions(self, org: UUID, assignment: UUID, editable: bool) -> list[dict]:
        return self.db.execute("SELECT * FROM assignment_versions WHERE organization_id=%s AND assignment_id=%s AND (%s OR status<>'draft') ORDER BY version_number DESC",
                               (org,assignment,editable)).fetchall()

    def version(self, org: UUID, assignment: UUID, version: UUID, lock: bool = False) -> dict | None:
        return self.db.execute("SELECT * FROM assignment_versions WHERE organization_id=%s AND assignment_id=%s AND id=%s" + (' FOR UPDATE' if lock else ''), (org,assignment,version)).fetchone()

    def content(self, org: UUID, version: UUID) -> dict:
        criteria = self.db.execute("SELECT * FROM rubric_criteria WHERE organization_id=%s AND assignment_version_id=%s ORDER BY position", (org,version)).fetchall()
        references = self.db.execute("SELECT * FROM reference_solutions WHERE organization_id=%s AND assignment_version_id=%s ORDER BY created_at,id", (org,version)).fetchall()
        for reference in references:
            reference['files'] = self.db.execute("""SELECT f.id,f.original_filename,f.processing_status,f.error_code FROM reference_solution_files rf
                JOIN file_assets f ON f.organization_id=rf.organization_id AND f.id=rf.file_asset_id
                WHERE rf.organization_id=%s AND rf.reference_solution_id=%s ORDER BY rf.position""", (org,reference['id'])).fetchall()
        files = self.db.execute("""SELECT f.id,f.original_filename,f.processing_status,f.error_code FROM assignment_version_files af
            JOIN file_assets f ON f.organization_id=af.organization_id AND f.id=af.file_asset_id
            WHERE af.organization_id=%s AND af.assignment_version_id=%s ORDER BY af.position""", (org,version)).fetchall()
        return {'criteria':criteria,'references':references,'files':files}

    def save(self, access: OrganizationAccess, assignment: UUID, version: UUID, body: VersionInput) -> dict:
        org = access.organization_id
        self.db.execute("UPDATE assignments SET title=%s,description=%s WHERE organization_id=%s AND id=%s", (body.title,body.description,org,assignment))
        result = self.db.execute("""UPDATE assignment_versions SET instructions=%s,max_score=%s,exemplar_threshold_percent=%s
            WHERE organization_id=%s AND id=%s RETURNING *""", (body.instructions,body.max_score,body.exemplar_threshold_percent,org,version)).fetchone()
        self.db.execute("DELETE FROM reference_solution_files WHERE organization_id=%s AND reference_solution_id IN (SELECT id FROM reference_solutions WHERE organization_id=%s AND assignment_version_id=%s)", (org,org,version))
        self.db.execute("DELETE FROM reference_solutions WHERE organization_id=%s AND assignment_version_id=%s", (org,version))
        self.db.execute("DELETE FROM rubric_criteria WHERE organization_id=%s AND assignment_version_id=%s", (org,version))
        self.db.execute("DELETE FROM assignment_version_files WHERE organization_id=%s AND assignment_version_id=%s", (org,version))
        for position, criterion in enumerate(body.criteria):
            self.db.execute("""INSERT INTO rubric_criteria(organization_id,assignment_version_id,criterion_key,title,description,max_points,position)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""", (org,version,f'criterion_{position}',criterion.title,criterion.description,criterion.max_points,position))
        for reference in body.references:
            row = self.db.execute("INSERT INTO reference_solutions(organization_id,assignment_version_id,title,answer_text,created_by) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                                  (org,version,reference.title,reference.answer_text,access.user_id)).fetchone()
            for position, file_id in enumerate(reference.file_ids):
                self.db.execute("INSERT INTO reference_solution_files(organization_id,reference_solution_id,file_asset_id,position) VALUES (%s,%s,%s,%s)", (org,row['id'],file_id,position))
        for position, file_id in enumerate(body.file_ids):
            self.db.execute("INSERT INTO assignment_version_files(organization_id,assignment_version_id,file_asset_id,position) VALUES (%s,%s,%s,%s)", (org,version,file_id,position))
        return result

    def publish(self, org: UUID, assignment: UUID, version: UUID) -> dict:
        row = self.db.execute("UPDATE assignment_versions SET status='published' WHERE organization_id=%s AND id=%s RETURNING *", (org,version)).fetchone()
        self.db.execute("UPDATE assignments SET status='active' WHERE organization_id=%s AND id=%s", (org,assignment))
        return row

    def students(self, org: UUID, search: str, page: int, limit: int) -> dict:
        args = (org,f'%{search}%',f'%{search}%')
        where = "organization_id=%s AND status='active' AND (display_name ILIKE %s OR external_student_id ILIKE %s)"
        total = self.db.execute(f"SELECT count(*) AS n FROM students WHERE {where}",args).fetchone()['n']
        items = self.db.execute(f"SELECT id,external_student_id,display_name,email FROM students WHERE {where} ORDER BY display_name,id LIMIT %s OFFSET %s", (*args,limit,(page-1)*limit)).fetchall()
        return {'items':items,'total':total,'page':page,'limit':limit}

    def create_student(self, org: UUID, body: StudentInput) -> dict | None:
        return self.db.execute("""INSERT INTO students(organization_id,external_student_id,display_name,email) VALUES (%s,%s,%s,%s)
            ON CONFLICT (organization_id,external_student_id) DO NOTHING RETURNING *""", (org,body.external_student_id,body.display_name,body.email)).fetchone()

    def lock_student(self, org: UUID, student: UUID) -> dict | None:
        return self.db.execute("SELECT * FROM students WHERE organization_id=%s AND id=%s AND status='active' FOR UPDATE", (org,student)).fetchone()

    def prior_submission(self, access: OrganizationAccess, key: str) -> dict | None:
        return self.db.execute("SELECT * FROM submissions WHERE organization_id=%s AND submitted_by=%s AND idempotency_key=%s", (access.organization_id,access.user_id,key)).fetchone()

    def create_submission(self, access: OrganizationAccess, body: SubmissionInput, digest: str) -> dict:
        org = access.organization_id
        result = self.db.execute("""INSERT INTO submissions(organization_id,assignment_version_id,student_id,attempt_number,submitted_by,idempotency_key,request_hash)
            SELECT %s,%s,%s,coalesce(max(attempt_number),0)+1,%s,%s,%s FROM submissions WHERE organization_id=%s AND assignment_version_id=%s AND student_id=%s RETURNING *""",
            (org,body.assignment_version_id,body.student_id,access.user_id,body.idempotency_key,digest,org,body.assignment_version_id,body.student_id)).fetchone()
        for position,file_id in enumerate(body.file_ids):
            self.db.execute("INSERT INTO submission_files(organization_id,submission_id,file_asset_id,position) VALUES (%s,%s,%s,%s)", (org,result['id'],file_id,position))
        return result

    def submissions(self, org: UUID, assignment: UUID, page: int, limit: int) -> dict:
        where = 's.organization_id=%s AND v.assignment_id=%s'
        joins = 'FROM submissions s JOIN assignment_versions v ON v.organization_id=s.organization_id AND v.id=s.assignment_version_id JOIN students st ON st.organization_id=s.organization_id AND st.id=s.student_id'
        total = self.db.execute(f'SELECT count(*) AS n {joins} WHERE {where}', (org,assignment)).fetchone()['n']
        items = self.db.execute(f"""SELECT s.*,st.display_name AS student,st.external_student_id,v.version_number,
            g.total_score {joins} LEFT JOIN grade_revisions g ON g.organization_id=s.organization_id AND g.id=s.current_published_grade_id
            WHERE {where} ORDER BY s.created_at DESC,s.id LIMIT %s OFFSET %s""", (org,assignment,limit,(page-1)*limit)).fetchall()
        for item in items:
            item['files'] = self.submission_files(org,item['id'])
        return {'items':items,'total':total,'page':page,'limit':limit}

    def submission(self, org: UUID, submission: UUID) -> dict | None:
        return self.db.execute("""SELECT s.*,v.assignment_id FROM submissions s JOIN assignment_versions v ON v.organization_id=s.organization_id AND v.id=s.assignment_version_id
            WHERE s.organization_id=%s AND s.id=%s FOR UPDATE OF s""", (org,submission)).fetchone()

    def submission_files(self, org: UUID, submission: UUID) -> list[dict]:
        return self.db.execute("SELECT f.id,f.original_filename,f.processing_status FROM submission_files sf JOIN file_assets f ON f.organization_id=sf.organization_id AND f.id=sf.file_asset_id WHERE sf.organization_id=%s AND sf.submission_id=%s ORDER BY sf.position", (org,submission)).fetchall()

    def finalize(self, org: UUID, submission: UUID) -> dict:
        return self.db.execute("UPDATE submissions SET status='ready',submitted_at=now() WHERE organization_id=%s AND id=%s RETURNING *", (org,submission)).fetchone()

    def idempotency_lock(self, access: OrganizationAccess, key: str) -> None:
        self.db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (f'{access.organization_id}:{access.user_id}:{key}',))
