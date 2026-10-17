import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from uuid import UUID
from contextlib import contextmanager

import pytest
import psycopg
from psycopg import sql

from app.core.security import password_hash
from app.repositories.jobs import JobRepository
from app.services.extraction import InvalidFile, extract, text_content
from app.storage.local import LocalStorage
from test_auth import HEADERS, PASSWORD, setup, sign_in
from test_invitations import organization


def post(client, path, data=None):
    return client.post(f'/api/{path}',json=data,headers=HEADERS)


def trainer(db, org):
    uid = uuid4()
    email = f'trainer-{uid}@example.com'
    db.execute("INSERT INTO users(id,email,display_name,password_hash) VALUES (%s,%s,'Trainer',%s)", (uid,email,password_hash.hash(PASSWORD)))
    db.execute("INSERT INTO memberships(organization_id,user_id,role) VALUES (%s,%s,'trainer')", (org,uid))
    return uid,email


def create(client, org):
    response = post(client,f'organizations/{org}/assignments',{'title':'Index exercise','description':'Write a short explanation'})
    assert response.status_code==201,response.text
    return response.json()


def save(client, org, assignment, **changes):
    version = assignment['version']
    body = {'title':'Index exercise','description':'Write a short explanation','updated_at':version['updated_at'],
            'instructions':'Explain B-tree indexes','max_score':20,'exemplar_threshold_percent':80,
            'criteria':[{'title':'Accuracy','description':'Correct use case','max_points':20}],
            'references':[{'title':'Answer key','answer_text':'B-tree indexes speed selective lookups','file_ids':[]}], 'file_ids':[]}
    body.update(changes)
    response = client.patch(f"/api/organizations/{org}/assignments/{assignment['id']}/versions/{version['id']}",json=body,headers=HEADERS)
    if response.status_code==200:
        assignment['version']=response.json()
    return response


def publish(client, org, assignment):
    return post(client,f"organizations/{org}/assignments/{assignment['id']}/versions/{assignment['version']['id']}/publish")


@pytest.fixture
def storage(monkeypatch,tmp_path):
    from app.services import files as files_module
    monkeypatch.setattr(files_module,'LocalStorage',LocalStorage)
    monkeypatch.setattr('app.api.routes.workspace.LocalStorage',lambda: LocalStorage(tmp_path))
    return tmp_path


def upload(client, org, assignment, purpose='assignment', filename='README.md', content=b'Explain indexes'):
    response = client.post(f'/api/organizations/{org}/files',data={'assignment_id':assignment['id'],'purpose':purpose},files={'files':(filename,content,'application/octet-stream')},headers=HEADERS)
    assert response.status_code==201,response.text
    return response.json()[0]


def ready(db, org, file):
    db.execute("UPDATE file_assets SET processing_status='ready' WHERE organization_id=%s AND id=%s", (org,file['id']))


def test_owner_account_changes_are_scoped_and_enforced_immediately(setup):
    client,db,email,uid = setup
    org = organization(db,uid)
    other = organization(db,uid)
    target,target_email = trainer(db,org)
    db.execute("INSERT INTO memberships(organization_id,user_id,role) VALUES (%s,%s,'trainer')", (other,target))
    sign_in(client,email)
    member = next(m for m in client.get(f'/api/organizations/{org}/members?page=1').json()['items'] if m['id']==str(target))
    changed = client.patch(f'/api/organizations/{org}/members/{target}',headers=HEADERS,json={'updated_at':member['updated_at'],'role':'admin','display_name_override':'Team Admin'})
    assert changed.status_code==200,changed.text
    assert db.execute('SELECT display_name FROM users WHERE id=%s',(target,)).fetchone()['display_name']=='Trainer'
    assert db.execute('SELECT role FROM memberships WHERE organization_id=%s AND user_id=%s',(other,target)).fetchone()['role']=='trainer'
    stale = {**changed.json(),'updated_at':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}
    assert client.patch(f'/api/organizations/{org}/members/{target}',headers=HEADERS,json=stale).status_code==409
    assert post(client,f'organizations/{org}/members/{uid}/revoke',{'updated_at':member['updated_at']}).status_code==403
    revoked = post(client,f'organizations/{org}/members/{target}/revoke',{'updated_at':changed.json()['updated_at']})
    assert revoked.status_code==200
    sign_in(client,target_email)
    assert client.get(f'/api/organizations/{org}/assignments').status_code==403
    assert client.get(f'/api/organizations/{other}/assignments').status_code==200
    sign_in(client,email)
    assert post(client,f'organizations/{org}/members/{target}/restore',{'updated_at':revoked.json()['updated_at'],'role':'trainer'}).status_code==200
    sign_in(client,target_email)
    assert client.get(f'/api/organizations/{org}/assignments').status_code==200
    assert client.patch(f'/api/organizations/{org}/members/{uid}',headers=HEADERS,json={'updated_at':member['updated_at'],'role':'admin'}).status_code==403


def test_drafts_publication_visibility_and_versions(setup):
    client,db,email,uid = setup
    org = organization(db,uid)
    _,peer_email = trainer(db,org)
    sign_in(client,email)
    assignment = create(client,org)
    assert publish(client,org,assignment).status_code==422
    assert save(client,org,assignment,criteria=[{'title':'Accuracy','max_points':10}]).status_code==200
    assert publish(client,org,assignment).status_code==422
    sign_in(client,peer_email)
    assert client.get(f'/api/organizations/{org}/assignments').json()['total']==0
    assert client.get(f"/api/organizations/{org}/assignments/{assignment['id']}").status_code==404
    sign_in(client,email)
    assert save(client,org,assignment).status_code==200
    assert publish(client,org,assignment).status_code==200
    assert save(client,org,assignment).status_code==409
    assert post(client,f"organizations/{org}/assignments/{assignment['id']}/versions").status_code==201
    assert post(client,f"organizations/{org}/assignments/{assignment['id']}/versions").status_code==409
    sign_in(client,peer_email)
    detail = client.get(f"/api/organizations/{org}/assignments/{assignment['id']}").json()
    assert len(detail['versions'])==1 and not detail['can_edit']
    assert client.get(f"/api/organizations/{org}/assignments/{assignment['id']}/submissions").status_code==403
    assert post(client,f"organizations/{org}/assignments/{assignment['id']}/versions").status_code==403


def test_upload_categories_private_download_and_publish_readiness(setup,storage):
    client,db,email,uid = setup
    org = organization(db,uid)
    _,peer_email = trainer(db,org)
    other = organization(db,uid)
    sign_in(client,email)
    assignment = create(client,org)
    file = upload(client,org,assignment)
    assert save(client,org,assignment,file_ids=[file['id']]).status_code==200
    assert publish(client,org,assignment).status_code==422
    sign_in(client,peer_email)
    assert client.get(f"/api/organizations/{org}/files/{file['id']}").status_code==403
    assert client.get(f"/api/organizations/{other}/files/{file['id']}/download").status_code==403
    sign_in(client,email)
    ready(db,org,file)
    assert publish(client,org,assignment).status_code==200
    private = upload(client,org,assignment,'submission','answer.txt',b'Student answer')
    ready(db,org,private)
    sign_in(client,peer_email)
    assert client.get(f"/api/organizations/{org}/files/{file['id']}/download").content==b'Explain indexes'
    assert client.get(f"/api/organizations/{org}/files/{private['id']}/download").status_code==403
    assert client.get(f"/api/organizations/{org}/files/{private['id']}/text").status_code==403
    sign_in(client,email)
    draft = post(client,f"organizations/{org}/assignments/{assignment['id']}/versions").json()
    assignment['version']=draft
    assert save(client,org,assignment,file_ids=[private['id']]).status_code==422
    assert post(client,f'organizations/{org}/files/{private["id"]}/retry').status_code==409


def test_submission_idempotency_attempts_and_finalization(setup,storage):
    client,db,email,uid = setup
    org = organization(db,uid)
    sign_in(client,email)
    assignment = create(client,org)
    save(client,org,assignment)
    publish(client,org,assignment)
    student = post(client,f'organizations/{org}/students',{'external_student_id':'ST-1','display_name':'Student'}).json()
    file = upload(client,org,assignment,'submission')
    body = {'assignment_version_id':assignment['version']['id'],'student_id':student['id'],'file_ids':[file['id']],'idempotency_key':str(uuid4())}
    path = f"organizations/{org}/assignments/{assignment['id']}/submissions"
    response = post(client,path,body)
    assert response.status_code==201,response.text
    submission=response.json()
    assert post(client,path,body).json()['id']==submission['id']
    assert post(client,path,{**body,'file_ids':[]}).status_code==422
    second = upload(client,org,assignment,'submission','second.txt',b'Corrected answer')
    assert post(client,path,{**body,'file_ids':[second['id']]}).status_code==409
    assert post(client,f"organizations/{org}/submissions/{submission['id']}/finalize").status_code==422
    ready(db,org,file)
    assert post(client,f"organizations/{org}/submissions/{submission['id']}/finalize").json()['status']=='ready'
    assert post(client,f"organizations/{org}/submissions/{submission['id']}/finalize").status_code==200
    another=post(client,path,{**body,'idempotency_key':str(uuid4())}).json()
    assert another['attempt_number']==2
    assert client.get(f'/api/{path}').json()['total']==2


def test_job_lease_cannot_accept_stale_completion(setup,storage):
    client,db,email,uid = setup
    org = organization(db,uid)
    sign_in(client,email)
    assignment=create(client,org)
    file=upload(client,org,assignment)
    # Restrict fixture claim to this job; no existing jobs are consumed.
    job=db.execute('SELECT * FROM processing_jobs WHERE file_asset_id=%s',(file['id'],)).fetchone()
    token=uuid4()
    db.execute("UPDATE processing_jobs SET status='running',lease_token=%s,lease_expires_at=now()+interval '5 minutes' WHERE id=%s",(token,job['id']))
    job['lease_token']=token
    repo=JobRepository(db)
    assert repo.owned(job)
    db.execute('UPDATE processing_jobs SET lease_token=%s WHERE id=%s',(uuid4(),job['id']))
    assert not repo.complete(job,repo.asset(job),'Stale result',[])
    assert db.execute('SELECT processing_status FROM file_assets WHERE id=%s',(file['id'],)).fetchone()['processing_status']=='uploaded'


def test_real_extraction_worker_and_quarantine(setup,storage,monkeypatch):
    from app import worker
    client,db,email,uid=setup
    org=organization(db,uid)
    sign_in(client,email)
    assignment=create(client,org)
    archive_data=io.BytesIO()
    with zipfile.ZipFile(archive_data,'w') as output:
        output.writestr('README.md','Instructions')
        output.writestr('solution.py','print(1)')
    file=upload(client,org,assignment,filename='project.zip',content=archive_data.getvalue())
    @contextmanager
    def connection():
        with db.transaction():
            yield db
    monkeypatch.setattr(worker,'connection',connection)
    monkeypatch.setattr(worker,'LocalStorage',lambda: LocalStorage(storage))
    assert worker.run_once(UUID(file['id']))
    status=client.get(f"/api/organizations/{org}/files/{file['id']}").json()
    assert status['processing_status']=='ready'
    assert len(status['children'])==2
    assert 'Instructions' in client.get(f"/api/organizations/{org}/files/{file['id']}/text").json()['text']
    assert db.execute('SELECT count(*) AS n FROM file_extractions WHERE organization_id=%s',(org,)).fetchone()['n']==3
    invalid=upload(client,org,assignment,filename='fake.pdf',content=b'Not a PDF')
    assert worker.run_once(UUID(invalid['id']))
    status=client.get(f"/api/organizations/{org}/files/{invalid['id']}").json()
    assert status['processing_status']=='quarantined'
    assert 'valid PDF' in status['error_code']


def archive(path, entries):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as output:
        for name,data in entries:
            output.writestr(name,data)


def test_extraction_zip_and_docx(tmp_path):
    path=tmp_path/'source.zip'
    archive(path,[('README.md','Task instructions'),('src/main.py','print(1)')])
    entries=extract(path,'source.zip',tmp_path/'out')
    assert [entry.name for entry in entries]==['README.md','src/main.py']
    assert entries[1].text=='print(1)'
    archive(path,[('answer.txt','Answer without a README')])
    assert len(extract(path,'source.zip',tmp_path/'out2'))==1
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as doc:
        doc.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Answer</w:t></w:r></w:p></w:body></w:document>')
    assert text_content(stream.getvalue(),'answer.docx')=='Answer'


@pytest.mark.parametrize('name,content',[('../answer.txt','X'),('/answer.txt','X'),('nested.zip','X'),('program.exe','X'),('huge.txt','x'*100000),('fake.pdf','not PDF')])
def test_unsafe_zip_is_rejected(tmp_path,name,content):
    path=tmp_path/'source.zip'
    archive(path,[(name,content)])
    with pytest.raises((InvalidFile,ValueError)):
        extract(path,'source.zip',tmp_path/'out')


def test_zip_symlink_and_size_limits(tmp_path,monkeypatch):
    path=tmp_path/'source.zip'
    with zipfile.ZipFile(path,'w') as output:
        entry=zipfile.ZipInfo('link.txt')
        entry.external_attr=0o120777<<16
        output.writestr(entry,'target')
    with pytest.raises(InvalidFile):
        extract(path,'source.zip',tmp_path/'out')

    from app.services import extraction
    from dataclasses import replace
    monkeypatch.setattr(extraction,'settings',replace(extraction.settings,max_archive_entries=1))
    archive(path,[('a.txt','A'),('b.txt','B')])
    with pytest.raises(InvalidFile):
        extract(path,'source.zip',tmp_path/'out')


def test_grade_publication_coverage_pointer_and_immutability(setup,storage):
    client,db,email,uid=setup
    org=organization(db,uid)
    sign_in(client,email)
    assignment=create(client,org)
    save(client,org,assignment)
    publish(client,org,assignment)
    version=assignment['version']['id']
    student=post(client,f'organizations/{org}/students',{'external_student_id':'GRADE-1','display_name':'Student'}).json()
    file=upload(client,org,assignment,'submission')
    ready(db,org,file)
    submission=post(client,f"organizations/{org}/assignments/{assignment['id']}/submissions",{'assignment_version_id':version,'student_id':student['id'],'file_ids':[file['id']],'idempotency_key':str(uuid4())}).json()
    post(client,f"organizations/{org}/submissions/{submission['id']}/finalize")
    grade=db.execute("""INSERT INTO grade_revisions(organization_id,submission_id,assignment_version_id,revision_number,reviewed_by,total_score,feedback)
        VALUES (%s,%s,%s,1,%s,18,'Good answer') RETURNING id""",(org,submission['id'],version,uid)).fetchone()['id']
    with pytest.raises(psycopg.errors.RaiseException),db.transaction():
        db.execute("UPDATE grade_revisions SET status='published' WHERE id=%s",(grade,))
    criterion=db.execute('SELECT id FROM rubric_criteria WHERE assignment_version_id=%s',(version,)).fetchone()['id']
    db.execute("""INSERT INTO grade_criterion_scores(organization_id,grade_revision_id,assignment_version_id,rubric_criterion_id,score,feedback)
        VALUES (%s,%s,%s,%s,18,'Good answer')""",(org,grade,version,criterion))
    db.execute("UPDATE grade_revisions SET status='published' WHERE id=%s",(grade,))
    assert db.execute('SELECT current_published_grade_id FROM submissions WHERE id=%s',(submission['id'],)).fetchone()['current_published_grade_id']==grade
    assert db.execute("SELECT count(*) AS n FROM audit_events WHERE entity_id=%s AND action='grade.published'",(grade,)).fetchone()['n']==1
    for statement in ('UPDATE grade_revisions SET total_score=17 WHERE id=%s','DELETE FROM grade_revisions WHERE id=%s'):
        with pytest.raises(psycopg.errors.RaiseException),db.transaction():
            db.execute(statement,(grade,))


def test_new_tenant_tables_enforce_rls_for_non_owner_role(setup,storage):
    client,db,email,uid=setup
    org=organization(db,uid)
    sign_in(client,email)
    assignment=create(client,org)
    file=upload(client,org,assignment)
    save(client,org,assignment,file_ids=[file['id']])
    db.execute("INSERT INTO file_extractions(organization_id,file_asset_id,extracted_text) VALUES (%s,%s,'Text')",(org,file['id']))
    post(client,f'organizations/{org}/invitations',{'email':'rls@example.test','role':'trainer'})
    tables=('account_invitations','assignment_version_files','file_extractions')
    role=sql.Identifier('rls_test_'+uuid4().hex)
    db.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOBYPASSRLS').format(role))
    db.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
    for table in tables:
        db.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(sql.Identifier(table),role))
    try:
        db.execute(sql.SQL('SET LOCAL ROLE {}').format(role))
        for tenant,count in (('',0),(str(org),1),(str(uuid4()),0)):
            db.execute("SELECT set_config('app.organization_id',%s,true)",(tenant,))
            for table in tables:
                assert db.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(sql.Identifier(table))).fetchone()['n']==count
    finally:
        db.execute('RESET ROLE')
