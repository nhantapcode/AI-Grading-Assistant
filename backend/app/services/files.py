import mimetypes
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from app.core.config import settings
from app.models.workspace import OrganizationAccess
from app.models.upload import UploadSource
from app.repositories.assignments import AssignmentRepository
from app.repositories.files import FileRepository
from app.services.errors import WorkspaceError
from app.storage.local import LocalStorage

SUPPORTED = {'.zip','.pdf','.docx','.txt','.md','.py','.js','.ts','.java','.sql','.html','.css','.json'}


class FileService:
    def __init__(self, repository: FileRepository, assignments: AssignmentRepository, storage: LocalStorage, access: OrganizationAccess) -> None:
        self.repository = repository
        self.assignments = assignments
        self.storage = storage
        self.access = access

    def upload(self, assignment: UUID, purpose: str, uploads: list[UploadSource]) -> list[dict]:
        row = self.assignments.get(self.access.organization_id,assignment,True)
        if not row or row['status']=='archived' or not (self.access.is_manager or row['created_by']==self.access.user_id):
            raise WorkspaceError(403,'You cannot upload files to this assignment')
        if not 1 <= len(uploads) <= settings.max_upload_files:
            raise WorkspaceError(422,f'Choose 1–{settings.max_upload_files} files')
        created = []
        try:
            for upload in uploads:
                filename = PurePosixPath((upload.filename or '').replace('\\','/')).name
                suffix = PurePosixPath(filename).suffix.lower()
                if suffix not in SUPPORTED or len(filename)>255:
                    raise WorkspaceError(422,'Unsupported file type or filename')
                key = uuid4()
                size,digest = self.storage.write(str(key),upload.file,settings.max_file_bytes)
                created.append(str(key))
                content_type = mimetypes.guess_type(filename)[0] or 'text/plain'
                if suffix == '.zip':
                    content_type = 'application/zip'
                asset = self.repository.create(self.access,assignment,purpose,key,filename,content_type,size,digest)
                asset.pop('object_key',None)
                created[-1] = str(key)
            return [self.metadata(UUID(key)) for key in created]
        except BaseException:
            for key in created:
                self.storage.delete(key)
            raise

    def authorize(self, file: UUID) -> dict:
        row = self.repository.get(self.access.organization_id,file)
        if not row:
            raise WorkspaceError(404,'File not found')
        root = self.repository.get(self.access.organization_id,row['parent_archive_id']) if row['parent_archive_id'] else row
        if not root:
            raise WorkspaceError(404,'File not found')
        if self.access.is_manager or root['uploaded_by']==self.access.user_id:
            return row
        assignment = self.assignments.get(self.access.organization_id,root['target_assignment_id'])
        if not assignment:
            raise WorkspaceError(404,'File not found')
        # Owning trainers can manage files attached to their own assignment.
        if assignment['created_by']==self.access.user_id and self.repository.attached(self.access.organization_id,root['id']):
            return row
        if root['purpose'] != 'submission' and self.repository.visible_attachment(self.access.organization_id,root['id']):
            return row
        raise WorkspaceError(403,'You cannot access this file')

    def metadata(self, file: UUID) -> dict:
        row = self.authorize(file)
        return {key:row[key] for key in ('id','original_filename','content_type','size_bytes','processing_status','error_code','purpose','created_at')} | {
            'children':self.repository.children(self.access.organization_id,file)}

    def text(self, file: UUID) -> dict:
        row = self.authorize(file)
        if row['processing_status'] != 'ready':
            raise WorkspaceError(409,'File text is not ready')
        text = self.repository.extraction(self.access.organization_id,file)
        if text is None:
            raise WorkspaceError(404,'Extracted text is unavailable')
        return {'text':text[:200000],'truncated':len(text)>200000}

    def validate_attachments(self, assignment: UUID, purpose: str, files: list[UUID], ready: bool = False) -> None:
        if len(files)>settings.max_upload_files:
            raise WorkspaceError(422,f'Attach up to {settings.max_upload_files} files per group')
        if len(set(files)) != len(files):
            raise WorkspaceError(422,'Duplicate file attachments are not allowed')
        for file in files:
            row = self.authorize(file)
            if row['parent_archive_id'] or row['target_assignment_id'] != assignment or row['purpose'] != purpose:
                raise WorkspaceError(422,'File belongs to a different assignment or upload category')
            if ready and row['processing_status'] != 'ready':
                raise WorkspaceError(422,'All files must finish processing successfully')

    def retry(self, file: UUID) -> dict:
        row = self.authorize(file)
        assignment = self.assignments.get(self.access.organization_id,row['target_assignment_id'])
        if row['parent_archive_id'] or row['processing_status'] != 'failed' or not (self.access.is_manager or assignment['created_by']==self.access.user_id):
            raise WorkspaceError(409,'This file cannot be retried; replace invalid files instead')
        if not self.repository.retry(self.access.organization_id,file):
            raise WorkspaceError(409,'Retry limit reached. Upload a replacement file')
        return self.metadata(file)
