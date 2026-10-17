import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AccountsPage from './AccountsPage';
import AssignmentEditorPage from './AssignmentEditorPage';
import Workspace from '../layouts/Workspace';
import FileUpload from '../components/FileUpload';
import { api, post, uploadFiles } from '../lib/api';

vi.mock('../lib/api', () => ({ api: vi.fn(), post: vi.fn(), uploadFiles: vi.fn() }));
const org = { id: 'org-id', name: 'Training Center', role: 'owner' };
const member = { id: 'trainer-id', email: 'trainer@example.com', display_name: 'Trainer', role: 'trainer', status: 'active', updated_at: '2026-10-13T00:00:00Z', created_at: '2026-10-13T00:00:00Z' };
const version = { id: 'version-id', updated_at: '2026-10-13T00:00:00Z', status: 'draft' };

beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(null, '', '/');
  api.mockImplementation(async path => {
    if (path === 'organizations') return [org];
    if (path.includes('/members?')) return { items: [member], total: 1 };
    if (path.endsWith('/invitations')) return [];
    if (path.endsWith('/upload-policy')) return { max_file_bytes: 50 * 1024 * 1024, max_upload_files: 20 };
    if (path.endsWith('/assignment-authors')) return [];
    if (path.includes('/assignments?')) return { items: [], total: 0 };
    if (path.includes('/versions/')) return version;
    throw new Error(`Unexpected request: ${path}`);
  });
  post.mockImplementation(async path => path.endsWith('/assignments') ? { id: 'assignment-id', version } : {});
});

it('requires confirmation before removing organization access', async () => {
  const user = userEvent.setup();
  render(<AccountsPage organization={org} />);
  await user.click(await screen.findByRole('button', { name: 'Remove Access' }));
  expect(post).not.toHaveBeenCalled();
  expect(screen.getByRole('dialog').textContent).toContain('Assignment and grading history will be retained');
  await user.click(screen.getAllByRole('button', { name: 'Remove Access' })[1]);
  await waitFor(() => expect(post).toHaveBeenCalledWith('organizations/org-id/members/trainer-id/revoke', expect.objectContaining({ updated_at: member.updated_at })));
});

it('edits an organization-specific name and role', async () => {
  const user = userEvent.setup();
  render(<AccountsPage organization={org} />);
  await user.click(await screen.findByRole('button', { name: 'Edit' }));
  await user.type(screen.getByLabelText('Name in this organization'), 'Team Trainer');
  await user.selectOptions(screen.getAllByLabelText('Role')[1], 'admin');
  await user.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => expect(api).toHaveBeenCalledWith('organizations/org-id/members/trainer-id', expect.objectContaining({ method: 'PATCH' })));
  const request = api.mock.calls.find(([, options]) => options?.method === 'PATCH');
  expect(JSON.parse(request[1].body)).toEqual({ updated_at: member.updated_at, role: 'admin', display_name_override: 'Team Trainer' });
});

it('saves a draft and publishes valid instructions, rubric and answer text', async () => {
  const user = userEvent.setup();
  const navigate = vi.fn();
  render(<AssignmentEditorPage organization={org} navigate={navigate} onDirty={vi.fn()} />);
  await user.type(screen.getByLabelText('Title'), 'Explain indexes');
  await user.type(screen.getByLabelText('Instructions'), 'Describe a B-tree use case.');
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.type(await screen.findByLabelText('Answer Text'), 'A B-tree speeds selective lookups.');
  await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByText('100.00 / 100 points')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Publish Assignment' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('organizations/org-id/assignments/assignment-id/versions/version-id/publish'));
  expect(navigate).toHaveBeenCalledWith('/organizations/org-id/assignments/assignment-id', true);
});

it('limits Trainer navigation and confirms leaving unsaved assignment work', async () => {
  const user = userEvent.setup();
  api.mockImplementation(async path => {
    if (path === 'organizations') return [{ ...org, role: 'trainer' }];
    if (path.endsWith('/assignment-authors')) return [];
    if (path.includes('/assignments?')) return { items: [], total: 0 };
    throw new Error(`Unexpected request: ${path}`);
  });
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<Workspace user={{ id: 'trainer-id', display_name: 'Trainer', email: member.email }} signOut={vi.fn()} />);
  await user.click(await screen.findByRole('button', { name: '+ Create Assignment' }));
  expect(screen.queryByRole('button', { name: 'Accounts' })).toBeNull();
  await user.type(screen.getByLabelText('Title'), 'Unsaved exercise');
  await user.click(screen.getByRole('button', { name: 'My Account' }));
  expect(confirm).toHaveBeenCalled();
  expect(screen.getByLabelText('Title').value).toBe('Unsaved exercise');
  confirm.mockReturnValue(true);
  await user.click(screen.getByRole('button', { name: 'My Account' }));
  expect(await screen.findByRole('heading', { name: 'My Account' })).toBeTruthy();
  confirm.mockRestore();
});

it('rejects unsupported files before starting an upload', async () => {
  const user = userEvent.setup({ applyAccept: false });
  render(<FileUpload base="organizations/org-id" assignmentId="assignment-id" purpose="assignment" files={[]} onChange={vi.fn()} />);
  const picker = screen.getByLabelText('Choose files to upload');
  await waitFor(() => expect(picker.disabled).toBe(false));
  await user.upload(picker, new File(['binary'], 'program.exe', { type: 'application/octet-stream' }));
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(uploadFiles).not.toHaveBeenCalled();
});

it.each([
  'assignments',
  'assignments/new',
  'assignments/assignment-id',
  'assignments/assignment-id/versions/version-id/edit',
  'assignments/assignment-id/submissions/upload',
])('blocks Owner navigation directly to %s', async route => {
  window.history.replaceState(null, '', `/organizations/org-id/${route}`);
  render(<Workspace user={{ id: 'owner-id', display_name: 'Owner', email: 'owner@example.com' }} signOut={vi.fn()} />);
  expect((await screen.findByRole('alert')).textContent).toContain('Assignment pages are available to admins and trainers');
  expect(screen.queryByRole('button', { name: 'Assignments' })).toBeNull();
  expect(api.mock.calls.every(([path]) => path === 'organizations')).toBe(true);
});
