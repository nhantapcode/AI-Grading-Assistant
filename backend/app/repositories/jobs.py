from uuid import UUID, uuid4

from psycopg import Connection


class JobRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    def claim(self, file_id: UUID | None = None) -> dict | None:
        # Exhausted/crashed jobs must not remain running forever.
        exhausted = self.db.execute("""UPDATE processing_jobs SET status='failed',lease_token=NULL,lease_expires_at=NULL,last_error_code='Processing retry limit reached'
            WHERE job_type='extract' AND status='running' AND lease_expires_at<now() AND attempt_count>=max_attempts RETURNING organization_id,file_asset_id""").fetchall()
        for row in exhausted:
            self.db.execute("UPDATE file_assets SET processing_status='failed',error_code='Processing retry limit reached' WHERE organization_id=%s AND id=%s", (row['organization_id'],row['file_asset_id']))
        row = self.db.execute("""SELECT j.id FROM processing_jobs j WHERE job_type='extract' AND attempt_count<max_attempts
            AND ((status='queued' AND available_at<=now()) OR (status='running' AND lease_expires_at<now()))
            AND (%s::uuid IS NULL OR file_asset_id=%s)
            ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1""", (file_id,file_id)).fetchone()
        if not row:
            return None
        job = self.db.execute("""UPDATE processing_jobs SET status='running',attempt_count=attempt_count+1,lease_token=%s,lease_expires_at=now()+interval '5 minutes'
            WHERE id=%s RETURNING *""", (uuid4(),row['id'])).fetchone()
        self.db.execute("UPDATE file_assets SET processing_status='scanning',error_code=NULL WHERE organization_id=%s AND id=%s", (job['organization_id'],job['file_asset_id']))
        return job

    def asset(self, job: dict) -> dict:
        return self.db.execute('SELECT * FROM file_assets WHERE organization_id=%s AND id=%s', (job['organization_id'],job['file_asset_id'])).fetchone()

    def owned(self, job: dict) -> bool:
        return self.db.execute("SELECT id FROM processing_jobs WHERE id=%s AND status='running' AND lease_token=%s AND lease_expires_at>now() FOR UPDATE", (job['id'],job['lease_token'])).fetchone() is not None

    def stage(self, job: dict) -> None:
        if self.owned(job):
            self.db.execute("UPDATE file_assets SET processing_status='extracting' WHERE organization_id=%s AND id=%s", (job['organization_id'],job['file_asset_id']))

    def complete(self, job: dict, asset: dict, text: str, children: list[dict]) -> bool:
        if not self.owned(job):
            return False
        org,file = job['organization_id'],job['file_asset_id']
        for child in children:
            self.db.execute("""INSERT INTO file_assets(id,organization_id,storage_backend,bucket_name,object_key,original_filename,content_type,size_bytes,sha256,uploaded_by,
                parent_archive_id,archive_entry_path,processing_status,purpose,target_assignment_id)
                VALUES (%s,%s,'local','private',%s,%s,%s,%s,%s,%s,%s,%s,'ready',%s,%s)""",
                (child['id'],org,str(child['id']),child['name'],child['content_type'],child['size'],child['digest'],asset['uploaded_by'],file,child['name'],asset['purpose'],asset['target_assignment_id']))
            self.db.execute('INSERT INTO file_extractions(organization_id,file_asset_id,extracted_text) VALUES (%s,%s,%s)', (org,child['id'],child['text']))
        self.db.execute('INSERT INTO file_extractions(organization_id,file_asset_id,extracted_text) VALUES (%s,%s,%s) ON CONFLICT (organization_id,file_asset_id) DO UPDATE SET extracted_text=excluded.extracted_text', (org,file,text))
        self.db.execute("UPDATE file_assets SET processing_status='ready',error_code=NULL WHERE organization_id=%s AND id=%s", (org,file))
        self.db.execute("UPDATE processing_jobs SET status='succeeded',lease_token=NULL,lease_expires_at=NULL,last_error_code=NULL WHERE id=%s", (job['id'],))
        return True

    def fail(self, job: dict, message: str, quarantined: bool) -> None:
        if not self.owned(job):
            return
        message = message.replace('\x00','')[:300]
        self.db.execute("UPDATE file_assets SET processing_status=%s,error_code=%s WHERE organization_id=%s AND id=%s",
                        ('quarantined' if quarantined else 'failed',message,job['organization_id'],job['file_asset_id']))
        self.db.execute("UPDATE processing_jobs SET status='failed',lease_token=NULL,lease_expires_at=NULL,last_error_code=%s WHERE id=%s", (message,job['id']))

    def object_keys(self) -> set[str]:
        return {row['object_key'] for row in self.db.execute("SELECT object_key FROM file_assets WHERE storage_backend='local'").fetchall()}
