import { useEffect, useRef, useState } from 'react';
import { api, post, uploadFiles } from '../lib/api';
import { Alert, Badge, Button } from './ui';

export const supportedTypes = '.zip,.pdf,.docx,.txt,.md,.py,.js,.ts,.java,.sql,.html,.css,.json';

export function FileList({ files, base }) {
  const [details, setDetails] = useState({});
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const missing = files.filter(file => file.processing_status === 'ready' && !file.children);
    if (missing.length) Promise.all(missing.map(file => api(`${base}/files/${file.id}`)))
      .then(results => { if (active) setDetails(Object.fromEntries(results.map(file => [file.id, file]))); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [base, files]);
  const visible = files.map(file => ({ ...file, ...details[file.id] }));
  return <><Alert error={error} /><ul className="space-y-3">{visible.map(file => <li key={file.id} className="rounded-xl border border-slate-200 bg-white p-4 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><span className="break-all font-medium">{file.original_filename}</span><Badge>{file.processing_status}</Badge>{file.processing_status === 'ready' && <a href={`/api/${base}/files/${file.id}/download`} className="font-medium underline">Download</a>}</div>{file.error_code && <p className="mt-2 text-red-700">{file.error_code}</p>}{file.children?.length > 0 && <details className="mt-3"><summary className="cursor-pointer text-slate-500">Archive files ({file.children.length})</summary><ul className="mt-2 space-y-2">{file.children.map(child => <li key={child.id} className="flex flex-wrap justify-between gap-2 border-t border-slate-100 pt-2"><span className="break-all">{child.archive_entry_path}</span><a href={`/api/${base}/files/${child.id}/download`} className="underline">Download</a></li>)}</ul></details>}</li>)}</ul></>;
}

export default function FileUpload({ base, assignmentId, purpose, files, onChange, onBusyChange = () => {} }) {
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(null);
  const [policy, setPolicy] = useState(null);
  const values = useRef(files);
  const changed = useRef(onChange);
  const uploading = useRef(false);
  const picker = useRef(null);
  values.current = files; changed.current = onChange;
  useEffect(() => { api(`${base}/upload-policy`).then(setPolicy).catch(err => setError(err.message)); }, [base]);
  useEffect(() => {
    let active = true;
    const timer = setInterval(async () => {
      const pending = values.current.filter(file => ['uploaded', 'scanning', 'extracting'].includes(file.processing_status));
      if (!pending.length) return;
      try {
        const results = await Promise.all(pending.map(file => api(`${base}/files/${file.id}`)));
        if (active) changed.current(values.current.map(file => results.find(result => result.id === file.id) ?? file));
      } catch (err) { if (active) setError(err.message); }
    }, 1500);
    return () => { active = false; clearInterval(timer); };
  }, [base]);

  async function upload(selected) {
    if (uploading.current || !selected.length || !policy) return;
    setError('');
    if (selected.length + values.current.length > policy.max_upload_files) { setError(`Attach up to ${policy.max_upload_files} files.`); return; }
    for (const file of selected) {
      const suffix = `.${file.name.split('.').pop().toLowerCase()}`;
      if (!supportedTypes.split(',').includes(suffix)) { setError(`Unsupported file type: ${file.name}`); return; }
      if (!file.size || file.size > policy.max_file_bytes) { setError(`Each file must be nonempty and at most ${policy.max_file_bytes / 1024 / 1024} MB.`); return; }
    }
    const body = new FormData();
    body.append('assignment_id', assignmentId); body.append('purpose', purpose);
    selected.forEach(file => body.append('files', file));
    uploading.current = true; onBusyChange(true); setProgress(0);
    try { const uploaded = await uploadFiles(`${base}/files`, body, setProgress); changed.current([...values.current, ...uploaded]); }
    catch (err) { setError(err.message); }
    finally { uploading.current = false; onBusyChange(false); setProgress(null); if (picker.current) picker.current.value = ''; }
  }

  return <div className="space-y-4">
    <div onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); upload([...event.dataTransfer.files]); }} className="rounded-2xl border-2 border-dashed border-[#cbd9c5] bg-[#f8faf5] p-6 text-center">
      <p className="font-medium">Drop files here, or choose from your device</p><p className="my-3 text-xs leading-6 text-slate-500">ZIP, PDF, DOCX, text, Markdown, and source code.<br />{policy ? `${policy.max_file_bytes / 1024 / 1024} MB per file · up to ${policy.max_upload_files} files` : 'Loading upload limits…'}</p>
      <input ref={picker} type="file" multiple accept={supportedTypes} disabled={progress !== null || !policy} aria-label="Choose files to upload" onChange={event => upload([...event.target.files])} className="max-w-full text-sm file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:bg-[#173b35] file:px-4 file:py-2 file:text-white" />
      {progress !== null && <div className="mt-4"><p role="status" className="mb-2 text-sm">Uploading: {progress}%</p><progress aria-label="Upload progress" value={progress} max="100" className="w-full accent-[#173b35]" /></div>}
    </div>
    <Alert error={error} />
    <FileList files={files} base={base} />
    {files.map(file => <div key={file.id} className="flex justify-end gap-2">{file.processing_status === 'failed' && <Button secondary onClick={async () => { try { const updated = await post(`${base}/files/${file.id}/retry`); changed.current(values.current.map(item => item.id === updated.id ? updated : item)); } catch (err) { setError(err.message); } }}>Retry Processing</Button>}<Button secondary disabled={progress !== null} onClick={() => changed.current(values.current.filter(item => item.id !== file.id))}>Remove {file.original_filename}</Button></div>)}
    {files.some(file => ['uploaded', 'scanning', 'extracting'].includes(file.processing_status)) && <p role="status" className="text-xs text-slate-500">Files are being checked and extracted. Status refreshes automatically.</p>}
  </div>;
}
