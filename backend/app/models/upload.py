from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class UploadSource:
    filename: str
    file: BinaryIO
