from uuid import UUID

from psycopg import Connection

from app.models.workspace import OrganizationAccess


class FileRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    def get(self, org: UUID, file: UUID) -> dict | None:
        return self.db.execute('SELECT * FROM file_assets WHERE organization_id=%s AND id=%s', (org,file)).fetchone()

    def create(self, access: OrganizationAccess, assignment: UUID, purpose: str, file_id: UUID, filename: str, content_type: str, size: int, digest: str) -> dict:
        row = self.db.execute("""INSERT INTO file_assets(id,organization_id,storage_backend,bucket_name,object_key,original_filename,content_type,size_bytes,sha256,uploaded_by,purpose,target_assignment_id)
            VALUES (%s,%s,'local','private',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (file_id,access.organization_id,str(file_id),filename,content_type,size,digest,access.user_id,purpose,assignment)).fetchone()
        self.db.execute("INSERT INTO processing_jobs(organization_id,job_type,file_asset_id,deduplication_key) VALUES (%s,'extract',%s,%s)",
                        (access.organization_id,file_id,f'file:{file_id}'))
        return row

    def children(self, org: UUID, file: UUID) -> list[dict]:
        return self.db.execute("SELECT id,original_filename,archive_entry_path,processing_status,error_code,size_bytes FROM file_assets WHERE organization_id=%s AND parent_archive_id=%s ORDER BY archive_entry_path", (org,file)).fetchall()

    def attached(self, org: UUID, file: UUID) -> bool:
        return self.db.execute("""SELECT EXISTS (SELECT 1 FROM assignment_version_files WHERE organization_id=%s AND file_asset_id=%s
            UNION ALL SELECT 1 FROM reference_solution_files WHERE organization_id=%s AND file_asset_id=%s
            UNION ALL SELECT 1 FROM submission_files WHERE organization_id=%s AND file_asset_id=%s) AS attached""", (org,file,org,file,org,file)).fetchone()['attached']

    def visible_attachment(self, org: UUID, file: UUID) -> bool:
        return self.db.execute("""SELECT EXISTS (
            SELECT 1 FROM assignment_version_files af JOIN assignment_versions v ON v.organization_id=af.organization_id AND v.id=af.assignment_version_id
            WHERE af.organization_id=%s AND af.file_asset_id=%s AND v.status<>'draft'
            UNION ALL SELECT 1 FROM reference_solution_files rf JOIN reference_solutions r ON r.organization_id=rf.organization_id AND r.id=rf.reference_solution_id
            JOIN assignment_versions v ON v.organization_id=r.organization_id AND v.id=r.assignment_version_id
            WHERE rf.organization_id=%s AND rf.file_asset_id=%s AND v.status<>'draft') AS visible""", (org,file,org,file)).fetchone()['visible']

    def retry(self, org: UUID, file: UUID) -> bool:
        row = self.db.execute("""UPDATE processing_jobs SET status='queued',lease_token=NULL,lease_expires_at=NULL,available_at=now(),last_error_code=NULL
            WHERE organization_id=%s AND file_asset_id=%s AND status='failed' AND attempt_count<max_attempts RETURNING id""", (org,file)).fetchone()
        if row:
            self.db.execute("UPDATE file_assets SET processing_status='uploaded',error_code=NULL WHERE organization_id=%s AND id=%s", (org,file))
        return row is not None

    def extraction(self, org: UUID, file: UUID) -> str | None:
        row = self.db.execute('SELECT extracted_text FROM file_extractions WHERE organization_id=%s AND file_asset_id=%s', (org,file)).fetchone()
        return row['extracted_text'] if row else None
