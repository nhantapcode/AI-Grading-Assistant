from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from psycopg import Connection

from app.api.dependencies import protect_mutation, get_organization_access, require_role
from app.db.connection import get_db
from app.models.workspace import OrganizationAccess
from app.models.upload import UploadSource
from app.repositories.assignments import AssignmentRepository
from app.repositories.files import FileRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import AssignmentInput, MemberChange, StudentInput, SubmissionInput, VersionInput
from app.services.assignments import AssignmentService
from app.services.errors import WorkspaceError
from app.services.files import FileService
from app.services.workspace import AccountService
from app.storage.local import LocalStorage
from app.core.config import settings

router = APIRouter(prefix='/organizations/{organization_id}',tags=['Workspace'])


access = get_organization_access


def file_service(context: OrganizationAccess = Depends(access), db: Connection = Depends(get_db)) -> FileService:
    return FileService(FileRepository(db),AssignmentRepository(db),LocalStorage(),context)


def assignment_service(context: OrganizationAccess = Depends(access), db: Connection = Depends(get_db), files: FileService = Depends(file_service)) -> AssignmentService:
    return AssignmentService(AssignmentRepository(db),WorkspaceRepository(db),files,context)


def account_service(context: OrganizationAccess = Depends(require_role('owner')), db: Connection = Depends(get_db)) -> AccountService:
    return AccountService(WorkspaceRepository(db),context)


@router.patch('/members/{user_id}',dependencies=[Depends(protect_mutation)])
def edit_member(user_id: UUID, body: MemberChange, service: AccountService = Depends(account_service)) -> dict:
    return service.change(user_id,body,'edit')


@router.post('/members/{user_id}/revoke',dependencies=[Depends(protect_mutation)])
def revoke_member(user_id: UUID, body: MemberChange, service: AccountService = Depends(account_service)) -> dict:
    return service.change(user_id,body,'revoke')


@router.post('/members/{user_id}/restore',dependencies=[Depends(protect_mutation)])
def restore_member(user_id: UUID, body: MemberChange, service: AccountService = Depends(account_service)) -> dict:
    return service.change(user_id,body,'restore')


@router.get('/assignments')
def assignments(search: str = Query('',max_length=200), author: UUID | None = None,
                status: Literal['','draft','active','archived'] = '', updated_since: datetime | None = None,
                page: int = Query(1,ge=1), limit: int = Query(20,ge=1,le=100), service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.repository.list(service.access,search,author,status,updated_since,page,limit)


@router.get('/assignment-authors')
def authors(service: AssignmentService = Depends(assignment_service)) -> list[dict]:
    return service.repository.authors(service.access)


@router.get('/upload-policy')
def upload_policy(context: OrganizationAccess = Depends(access)) -> dict:
    return {key:getattr(settings,key) for key in ('max_file_bytes','max_upload_files','max_archive_entries','max_extracted_bytes')}


@router.post('/assignments',status_code=201,dependencies=[Depends(protect_mutation)])
def create_assignment(body: AssignmentInput, service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.create(body)


@router.get('/assignments/{assignment_id}')
def detail(assignment_id: UUID, service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.detail(assignment_id)


@router.post('/assignments/{assignment_id}/versions',status_code=201,dependencies=[Depends(protect_mutation)])
def create_version(assignment_id: UUID, service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.new_version(assignment_id)


@router.patch('/assignments/{assignment_id}/versions/{version_id}',dependencies=[Depends(protect_mutation)])
def save_version(assignment_id: UUID, version_id: UUID, body: VersionInput, service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.save(assignment_id,version_id,body)


@router.post('/assignments/{assignment_id}/versions/{version_id}/publish',dependencies=[Depends(protect_mutation)])
def publish_version(assignment_id: UUID, version_id: UUID, service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.publish(assignment_id,version_id)


@router.post('/files',status_code=201,dependencies=[Depends(protect_mutation)])
def upload(files: list[UploadFile] = File(), assignment_id: UUID = Form(),
           purpose: Literal['assignment','reference','submission'] = Form(), service: FileService = Depends(file_service)) -> list[dict]:
    return service.upload(assignment_id,purpose,[UploadSource(file.filename or '',file.file) for file in files])


@router.get('/files/{file_id}')
def file_status(file_id: UUID, service: FileService = Depends(file_service)) -> dict:
    return service.metadata(file_id)


@router.get('/files/{file_id}/download')
def download(file_id: UUID, service: FileService = Depends(file_service)) -> FileResponse:
    row = service.authorize(file_id)
    if row['processing_status'] != 'ready':
        raise WorkspaceError(409,'File is not ready for download')
    path = service.storage.path(row['object_key'])
    if not path.is_file():
        raise WorkspaceError(404,'Stored file is unavailable')
    return FileResponse(path,media_type='application/octet-stream',filename=row['original_filename'],headers={'X-Content-Type-Options':'nosniff'})


@router.get('/files/{file_id}/text')
def extracted_text(file_id: UUID, service: FileService = Depends(file_service)) -> dict:
    return service.text(file_id)


@router.post('/files/{file_id}/retry',dependencies=[Depends(protect_mutation)])
def retry_file(file_id: UUID, service: FileService = Depends(file_service)) -> dict:
    return service.retry(file_id)


@router.get('/students')
def students(search: str = Query('',max_length=120), page: int = Query(1,ge=1), limit: int = Query(100,ge=1,le=100),
             service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.repository.students(service.access.organization_id,search,page,limit)


@router.post('/students',status_code=201,dependencies=[Depends(protect_mutation)])
def create_student(body: StudentInput, service: AssignmentService = Depends(assignment_service)) -> dict:
    row = service.repository.create_student(service.access.organization_id,body)
    if not row:
        raise WorkspaceError(409,'This student ID already exists')
    service.workspace.audit(service.access,'student.created','student',row['id'])
    return row


@router.get('/assignments/{assignment_id}/submissions')
def submissions(assignment_id: UUID, page: int = Query(1,ge=1), limit: int = Query(20,ge=1,le=100), service: AssignmentService = Depends(assignment_service)) -> dict:
    row = service.assignment(assignment_id)
    if not service.access.is_manager and row['created_by'] != service.access.user_id:
        raise WorkspaceError(403,'You cannot view submissions for another trainer')
    return service.repository.submissions(service.access.organization_id,assignment_id,page,limit)


@router.post('/assignments/{assignment_id}/submissions',status_code=201,dependencies=[Depends(protect_mutation)])
def create_submission(assignment_id: UUID, body: SubmissionInput, service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.create_submission(assignment_id,body)


@router.post('/submissions/{submission_id}/finalize',dependencies=[Depends(protect_mutation)])
def finalize_submission(submission_id: UUID, service: AssignmentService = Depends(assignment_service)) -> dict:
    return service.finalize(submission_id)
