import hashlib
from uuid import UUID

from app.models.workspace import OrganizationAccess
from app.repositories.assignments import AssignmentRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.errors import WorkspaceError
from app.services.files import FileService
from app.schemas.workspace import AssignmentInput, VersionInput, SubmissionInput


class AssignmentService:
    def __init__(self, repository: AssignmentRepository, workspace: WorkspaceRepository, files: FileService, access: OrganizationAccess) -> None:
        self.repository = repository
        self.workspace = workspace
        self.files = files
        self.access = access

    def assignment(self, assignment: UUID, write: bool = False) -> dict:
        row = self.repository.get(self.access.organization_id,assignment,lock=write)
        if not row:
            raise WorkspaceError(404,'Assignment not found')
        editable = self.access.is_manager or row['created_by'] == self.access.user_id
        if write and (not editable or row['status'] == 'archived'):
            raise WorkspaceError(403,'You cannot change this assignment')
        versions = self.repository.versions(self.access.organization_id,assignment,editable)
        if not editable and not versions:
            raise WorkspaceError(404,'Assignment not found')
        return {**row,'can_edit':editable and row['status'] != 'archived','versions':versions}

    def detail(self, assignment: UUID) -> dict:
        row = self.assignment(assignment)
        for version in row['versions']:
            version.update(self.repository.content(self.access.organization_id,version['id']))
        return row

    def create(self, body: AssignmentInput) -> dict:
        row = self.repository.create(self.access,body.title,body.description)
        version = self.repository.create_version(self.access,row['id'])
        self.workspace.audit(self.access,'assignment.created','assignment',row['id'])
        return {**row,'version':version}

    def new_version(self, assignment: UUID) -> dict:
        row = self.assignment(assignment,True)
        existing = next((v for v in row['versions'] if v['status']=='draft'),None)
        if existing:
            raise WorkspaceError(409,'Edit the existing draft before creating another version')
        return self.repository.create_version(self.access,assignment)

    def draft(self, assignment: UUID, version: UUID) -> dict:
        self.assignment(assignment,True)
        row = self.repository.version(self.access.organization_id,assignment,version,True)
        if not row:
            raise WorkspaceError(404,'Version not found')
        if row['status'] != 'draft':
            raise WorkspaceError(409,'Published content is immutable. Create a new version')
        return row

    def save(self, assignment: UUID, version: UUID, body: VersionInput) -> dict:
        row = self.draft(assignment,version)
        if row['updated_at'] != body.updated_at:
            raise WorkspaceError(409,'This draft changed. Refresh before editing')
        self.files.validate_attachments(assignment,'assignment',body.file_ids)
        for reference in body.references:
            self.files.validate_attachments(assignment,'reference',reference.file_ids)
        return self.repository.save(self.access,assignment,version,body)

    def publish(self, assignment: UUID, version: UUID) -> dict:
        row = self.draft(assignment,version)
        content = self.repository.content(self.access.organization_id,version)
        if not row['instructions'].strip():
            raise WorkspaceError(422,'Instructions are required. Describe the task or refer to its attached files')
        if not content['criteria'] or sum(c['max_points'] for c in content['criteria']) != row['max_score']:
            raise WorkspaceError(422,'Rubric points must equal the maximum score')
        if not any(r['answer_text'] and r['answer_text'].strip() or r['files'] for r in content['references']):
            raise WorkspaceError(422,'At least one usable answer key is required')
        self.files.validate_attachments(assignment,'assignment',[f['id'] for f in content['files']],ready=True)
        for reference in content['references']:
            self.files.validate_attachments(assignment,'reference',[f['id'] for f in reference['files']],ready=True)
        result = self.repository.publish(self.access.organization_id,assignment,version)
        self.workspace.audit(self.access,'assignment.published','assignment_version',version)
        self.workspace.event(self.access.organization_id,'assignment.published',{'version_id':str(version)})
        return result

    def create_submission(self, assignment: UUID, body: SubmissionInput) -> dict:
        # Serialize retries before locking assignment/student rows.
        self.repository.idempotency_lock(self.access,body.idempotency_key)
        self.assignment(assignment,True)
        digest = hashlib.sha256(body.model_dump_json(exclude={'idempotency_key'}).encode()).hexdigest()
        prior = self.repository.prior_submission(self.access,body.idempotency_key)
        if prior:
            if prior['request_hash'] != digest:
                raise WorkspaceError(409,'This request key was already used with different data')
            return prior
        version = self.repository.version(self.access.organization_id,assignment,body.assignment_version_id)
        if not version or version['status'] != 'published':
            raise WorkspaceError(422,'Choose a published version that accepts submissions')
        if not self.repository.lock_student(self.access.organization_id,body.student_id):
            raise WorkspaceError(404,'Active student not found')
        self.files.validate_attachments(assignment,'submission',body.file_ids)
        return self.repository.create_submission(self.access,body,digest)

    def finalize(self, submission: UUID) -> dict:
        row = self.repository.submission(self.access.organization_id,submission)
        if not row:
            raise WorkspaceError(404,'Submission not found')
        self.assignment(row['assignment_id'],True)
        if row['status'] == 'ready':
            return row
        if row['status'] != 'draft':
            raise WorkspaceError(409,'This submission cannot be finalized')
        attached = self.repository.submission_files(self.access.organization_id,submission)
        if not attached:
            raise WorkspaceError(422,'Attach at least one file')
        self.files.validate_attachments(row['assignment_id'],'submission',[f['id'] for f in attached],ready=True)
        version = self.repository.version(self.access.organization_id,row['assignment_id'],row['assignment_version_id'],True)
        if version['status'] != 'published' or not self.repository.lock_student(self.access.organization_id,row['student_id']):
            raise WorkspaceError(409,'Version or student no longer accepts submissions')
        result = self.repository.finalize(self.access.organization_id,submission)
        self.workspace.audit(self.access,'submission.finalized','submission',submission)
        self.workspace.event(self.access.organization_id,'submission.ready',{'submission_id':str(submission)})
        return result
