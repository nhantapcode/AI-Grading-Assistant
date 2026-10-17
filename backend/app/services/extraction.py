"""Bounded, non-executing extraction of allowlisted documents and ZIP entries."""
import hashlib
import io
import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader

from app.core.config import settings
from app.services.files import SUPPORTED


class InvalidFile(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedFile:
    name: str
    path: Path
    text: str


def text_content(data: bytes, filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in SUPPORTED or suffix == '.zip':
        raise InvalidFile('Unsupported or nested archive entry')
    if suffix == '.pdf':
        if not data.startswith(b'%PDF-'):
            raise InvalidFile('File is not a valid PDF')
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages)>500:
            raise InvalidFile('Encrypted PDFs or PDFs over 500 pages are unsupported')
        parts = []
        size = 0
        for page in reader.pages:
            if page.get_contents() and len(page.get_contents().get_data())>10*1024*1024:
                raise InvalidFile('PDF page is too complex')
            part = page.extract_text() or ''
            size += len(part)
            if size>2_000_000:
                raise InvalidFile('Extracted text exceeds the limit')
            parts.append(part)
        text = '\n'.join(parts)
        if not text.strip():
            raise InvalidFile('PDF has no readable text. Upload a text-based PDF; OCR is not supported')
    elif suffix == '.docx':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist())>settings.max_archive_entries or sum(i.file_size for i in archive.infolist())>settings.max_extracted_bytes:
                raise InvalidFile('DOCX exceeds extraction limits')
            info = archive.getinfo('word/document.xml')
            if info.file_size>10*1024*1024 or info.flag_bits & 1:
                raise InvalidFile('DOCX document is too large or encrypted')
            document = fromstring(archive.read(info))
            text = '\n'.join(''.join(p.itertext()) for p in document.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
    else:
        if data.startswith((b'MZ',b'\x7fELF',b'PK\x03\x04')) or b'\x00' in data:
            raise InvalidFile('File content does not match a supported text format')
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as error:
            raise InvalidFile('Text files must use UTF-8 encoding') from error
        if suffix == '.json':
            json.loads(text)
    if not text.strip():
        raise InvalidFile('File has no readable text')
    if len(text)>2_000_000:
        raise InvalidFile('Extracted text exceeds the limit')
    return text


def extract(source: Path, filename: str, destination: Path) -> list[ExtractedFile]:
    if source.stat().st_size>settings.max_file_bytes:
        raise InvalidFile('File exceeds the size limit')
    data = source.read_bytes()
    destination.mkdir(parents=True,exist_ok=True)
    if PurePosixPath(filename).suffix.lower() != '.zip':
        return [ExtractedFile(filename,source,text_content(data,filename))]
    result = []
    total = 0
    total_text = 0
    paths = set()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries)>settings.max_archive_entries:
            raise InvalidFile('ZIP contains too many entries')
        if sum(entry.file_size for entry in entries)>settings.max_extracted_bytes:
            raise InvalidFile('ZIP exceeds the extracted size limit')
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            mode = entry.external_attr >> 16
            if '\\' in name or '\x00' in name or ':' in name or path.is_absolute() or '..' in path.parts or len(name)>255:
                raise InvalidFile('ZIP contains an unsafe path')
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):
                raise InvalidFile('ZIP symlinks and special entries are unsupported')
            if entry.flag_bits & 1:
                raise InvalidFile('Encrypted archives are unsupported')
            if entry.is_dir():
                continue
            if name in paths or path.suffix.lower() not in SUPPORTED or path.suffix.lower()=='.zip':
                raise InvalidFile('ZIP contains duplicate, unsupported, or nested files')
            paths.add(name)
            if entry.file_size>settings.max_file_bytes or entry.file_size>max(entry.compress_size,1)*200:
                raise InvalidFile('ZIP entry exceeds size or compression ratio limits')
            with archive.open(entry) as stream:
                content = stream.read(settings.max_file_bytes+1)
            total += len(content)
            if len(content)>settings.max_file_bytes or total>settings.max_extracted_bytes:
                raise InvalidFile('ZIP exceeds extraction limits')
            text = text_content(content,name)
            total_text += len(text)
            if total_text>10_000_000:
                raise InvalidFile('ZIP extracted text exceeds the limit')
            child = destination / str(uuid4())
            child.write_bytes(content)
            result.append(ExtractedFile(name,child,text))
    if not result:
        raise InvalidFile('ZIP must contain at least one supported file')
    return result


def manifest(source: Path, filename: str, destination: Path) -> None:
    files = extract(source,filename,destination)
    payload = {'sha256':hashlib.sha256(source.read_bytes()).hexdigest(), 'files':[
        {'name':file.name,'path':str(file.path),'text':file.text} for file in files]}
    (destination/'manifest.json').write_text(json.dumps(payload),encoding='utf-8')
