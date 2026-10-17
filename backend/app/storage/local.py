"""Private objects use generated UUID keys, never uploaded filenames."""
import hashlib
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from app.core.config import settings
from app.services.errors import WorkspaceError


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.storage_root

    def path(self, key: str) -> Path:
        return self.root / str(UUID(key))

    def write(self, key: str, stream: BinaryIO, maximum: int) -> tuple[int,str]:
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        size, digest = 0, hashlib.sha256()
        path = self.path(key)
        try:
            with path.open('xb') as output:
                path.chmod(0o600)
                while chunk := stream.read(1024*1024):
                    size += len(chunk)
                    if size > maximum:
                        raise WorkspaceError(413,'File exceeds the configured size limit')
                    digest.update(chunk)
                    output.write(chunk)
                if not size:
                    raise WorkspaceError(422,'Empty files are not supported')
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return size,digest.hexdigest()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)
