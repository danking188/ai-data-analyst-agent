from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.domain.errors import DomainError, validation_error

SUPPORTED_EXTENSIONS = {"csv", "xls", "xlsx", "parquet"}
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class StagedUpload:
    display_name: str
    source_type: str
    storage_key: str
    sha256: str
    size_bytes: int


class FileStorage:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()

    async def stage_upload(
        self,
        upload: UploadFile,
        *,
        job_id: str,
        max_bytes: int,
    ) -> StagedUpload:
        display_name = self._safe_display_name(upload.filename)
        extension = self._extension(display_name)
        target_dir = self._safe_path("tmp", job_id)
        target_dir.mkdir(parents=True, exist_ok=False)
        target = target_dir / f"source.{extension}"
        digest = hashlib.sha256()
        size = 0
        leading = b""
        try:
            with target.open("xb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    if not leading:
                        leading = chunk[:8]
                    size += len(chunk)
                    if size > max_bytes:
                        raise DomainError(
                            "FILE_TOO_LARGE",
                            "文件超过当前部署限制",
                            413,
                            details={"max_upload_bytes": max_bytes},
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if size == 0:
                raise validation_error("上传文件为空")
            self._validate_signature(extension, leading)
            return StagedUpload(
                display_name=display_name,
                source_type=extension,
                storage_key=target.relative_to(self.data_root).as_posix(),
                sha256=f"sha256:{digest.hexdigest()}",
                size_bytes=size,
            )
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise
        finally:
            await upload.close()

    def remove_staged(self, job_id: str) -> None:
        shutil.rmtree(self._safe_path("tmp", job_id), ignore_errors=True)

    def resolve_key(self, storage_key: str) -> Path:
        candidate = self.data_root.joinpath(storage_key).resolve()
        if self.data_root not in candidate.parents:
            raise ValueError("storage key escaped DATA_ROOT")
        return candidate

    def temp_parquet_path(self, job_id: str) -> Path:
        path = self._safe_path("tmp", job_id, "data.parquet")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def commit_ingestion(
        self,
        *,
        project_id: str,
        dataset_id: str,
        version_id: str,
        source_path: Path,
        parquet_path: Path,
        source_type: str,
    ) -> tuple[str, str]:
        source_target = self._safe_path(
            "originals",
            project_id,
            dataset_id,
            version_id,
            f"source.{source_type}",
        )
        data_target = self._safe_path(
            "versions",
            project_id,
            dataset_id,
            version_id,
            "data.parquet",
        )
        source_target.parent.mkdir(parents=True, exist_ok=True)
        data_target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source_path, source_target)
        source_target.chmod(0o440)
        os.replace(parquet_path, data_target)
        return (
            source_target.relative_to(self.data_root).as_posix(),
            data_target.relative_to(self.data_root).as_posix(),
        )

    def commit_derived_parquet(
        self,
        *,
        project_id: str,
        dataset_id: str,
        version_id: str,
        parquet_path: Path,
    ) -> str:
        target = self._safe_path(
            "versions",
            project_id,
            dataset_id,
            version_id,
            "data.parquet",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(parquet_path, target)
        target.chmod(0o440)
        return target.relative_to(self.data_root).as_posix()

    def write_artifact_file(
        self,
        *,
        project_id: str,
        artifact_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        safe_name = self._safe_display_name(file_name)
        target = self._safe_path("artifacts", project_id, artifact_id, safe_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(content)
        target.chmod(0o440)
        return target.relative_to(self.data_root).as_posix()

    def quarantine(self, job_id: str, source_path: Path) -> str | None:
        if not source_path.exists():
            return None
        target = self._safe_path("quarantine", job_id, source_path.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source_path, target)
        target.chmod(0o440)
        return target.relative_to(self.data_root).as_posix()

    @staticmethod
    def checksum_path(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"

    def _safe_path(self, *parts: str) -> Path:
        candidate = self.data_root.joinpath(*parts).resolve()
        if candidate != self.data_root and self.data_root not in candidate.parents:
            raise ValueError("storage path escaped DATA_ROOT")
        return candidate

    @staticmethod
    def _safe_display_name(filename: str | None) -> str:
        name = Path(filename or "upload").name
        name = CONTROL_CHARS.sub("", name).strip()
        return name[:255] or "upload"

    @staticmethod
    def _extension(filename: str) -> str:
        extension = Path(filename).suffix.lower().removeprefix(".")
        if extension not in SUPPORTED_EXTENSIONS:
            raise DomainError(
                "UNSUPPORTED_FILE_TYPE",
                "文件类型不受支持",
                415,
                details={"supported_file_types": sorted(SUPPORTED_EXTENSIONS)},
            )
        return extension

    @staticmethod
    def _validate_signature(extension: str, leading: bytes) -> None:
        valid = True
        if extension == "xls":
            valid = leading.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
        elif extension == "xlsx":
            valid = leading.startswith(b"PK")
        elif extension == "parquet":
            valid = leading.startswith(b"PAR1")
        if not valid:
            raise DomainError(
                "FILE_CORRUPTED",
                "文件内容与扩展名不匹配或文件已损坏",
                422,
            )
