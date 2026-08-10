from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

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


@dataclass(frozen=True, slots=True)
class S3StorageConfig:
    bucket: str
    endpoint_url: str | None
    region: str
    access_key_id: str | None
    secret_access_key: str | None
    prefix: str = "datatrace"
    force_path_style: bool = False
    server_side_encryption: str | None = None


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

    def healthcheck(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        if not os.access(self.data_root, os.R_OK | os.W_OK | os.X_OK):
            raise OSError("DATA_ROOT is not readable and writable")

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
        try:
            os.replace(source_path, source_target)
            source_target.chmod(0o440)
            os.replace(parquet_path, data_target)
        except Exception:
            if source_target.exists() and not source_path.exists():
                source_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source_target, source_path)
            data_target.unlink(missing_ok=True)
            raise
        return (
            source_target.relative_to(self.data_root).as_posix(),
            data_target.relative_to(self.data_root).as_posix(),
        )

    def rollback_ingestion(
        self,
        *,
        staged_key: str,
        source_key: str,
        data_key: str,
    ) -> None:
        """Restore the staged source and remove finals after a database commit failure."""
        staged_path = self._safe_path(*PurePosixPath(staged_key).parts)
        source_path = self._safe_path(*PurePosixPath(source_key).parts)
        data_path = self._safe_path(*PurePosixPath(data_key).parts)
        if source_path.exists():
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.unlink(missing_ok=True)
            os.replace(source_path, staged_path)
        data_path.unlink(missing_ok=True)

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


class S3FileStorage(FileStorage):
    """S3-backed immutable storage with a local cache for dataframe tooling."""

    def __init__(
        self,
        cache_root: Path,
        config: S3StorageConfig,
        *,
        client: Any | None = None,
    ) -> None:
        super().__init__(cache_root)
        self.config = config
        if client is None:
            import boto3
            from botocore.config import Config

            addressing_style = "path" if config.force_path_style else "auto"
            client = boto3.client(
                "s3",
                endpoint_url=config.endpoint_url,
                region_name=config.region,
                aws_access_key_id=config.access_key_id,
                aws_secret_access_key=config.secret_access_key,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": addressing_style},
                ),
            )
        self.client = client

    async def stage_upload(
        self,
        upload: UploadFile,
        *,
        job_id: str,
        max_bytes: int,
    ) -> StagedUpload:
        staged = await super().stage_upload(upload, job_id=job_id, max_bytes=max_bytes)
        try:
            self._upload_path(staged.storage_key, super().resolve_key(staged.storage_key))
        except Exception:
            super().remove_staged(job_id)
            self._delete_object(staged.storage_key)
            raise
        return staged

    def remove_staged(self, job_id: str) -> None:
        prefix = self._object_key(f"tmp/{job_id}").rstrip("/") + "/"
        continuation_token: str | None = None
        while True:
            request: dict[str, Any] = {"Bucket": self.config.bucket, "Prefix": prefix}
            if continuation_token:
                request["ContinuationToken"] = continuation_token
            response = self.client.list_objects_v2(**request)
            objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if objects:
                self.client.delete_objects(
                    Bucket=self.config.bucket,
                    Delete={"Objects": objects, "Quiet": True},
                )
            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
        super().remove_staged(job_id)

    def healthcheck(self) -> None:
        super().healthcheck()
        self.client.head_bucket(Bucket=self.config.bucket)

    def resolve_key(self, storage_key: str) -> Path:
        target = super().resolve_key(storage_key)
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            self.client.download_file(
                self.config.bucket,
                self._object_key(storage_key),
                str(temporary),
            )
            os.replace(temporary, target)
            target.chmod(0o440)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target

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
        staged_key = source_path.relative_to(self.data_root).as_posix()
        source_key, data_key = super().commit_ingestion(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
            source_path=source_path,
            parquet_path=parquet_path,
            source_type=source_type,
        )
        try:
            self._upload_path(source_key, super().resolve_key(source_key))
            self._upload_path(data_key, super().resolve_key(data_key))
        except Exception:
            super().rollback_ingestion(
                staged_key=staged_key,
                source_key=source_key,
                data_key=data_key,
            )
            self._delete_object(source_key)
            self._delete_object(data_key)
            raise
        if staged_key != source_key:
            self._delete_object(staged_key)
        return source_key, data_key

    def rollback_ingestion(
        self,
        *,
        staged_key: str,
        source_key: str,
        data_key: str,
    ) -> None:
        super().rollback_ingestion(
            staged_key=staged_key,
            source_key=source_key,
            data_key=data_key,
        )
        staged_path = super().resolve_key(staged_key)
        self._upload_path(staged_key, staged_path)
        self._delete_object(source_key)
        self._delete_object(data_key)

    def commit_derived_parquet(
        self,
        *,
        project_id: str,
        dataset_id: str,
        version_id: str,
        parquet_path: Path,
    ) -> str:
        storage_key = super().commit_derived_parquet(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
            parquet_path=parquet_path,
        )
        self._upload_path(storage_key, super().resolve_key(storage_key))
        return storage_key

    def write_artifact_file(
        self,
        *,
        project_id: str,
        artifact_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        storage_key = super().write_artifact_file(
            project_id=project_id,
            artifact_id=artifact_id,
            file_name=file_name,
            content=content,
        )
        self._upload_path(storage_key, super().resolve_key(storage_key))
        return storage_key

    def quarantine(self, job_id: str, source_path: Path) -> str | None:
        source_key = source_path.relative_to(self.data_root).as_posix()
        quarantine_key = super().quarantine(job_id, source_path)
        if quarantine_key is not None:
            self._upload_path(quarantine_key, super().resolve_key(quarantine_key))
            self._delete_object(source_key)
        return quarantine_key

    def _upload_path(self, storage_key: str, path: Path) -> None:
        extra_args: dict[str, str] = {}
        if self.config.server_side_encryption:
            extra_args["ServerSideEncryption"] = self.config.server_side_encryption
        kwargs = {"ExtraArgs": extra_args} if extra_args else {}
        self.client.upload_file(
            str(path),
            self.config.bucket,
            self._object_key(storage_key),
            **kwargs,
        )

    def _delete_object(self, storage_key: str) -> None:
        self.client.delete_object(
            Bucket=self.config.bucket,
            Key=self._object_key(storage_key),
        )

    def _object_key(self, storage_key: str) -> str:
        parts = PurePosixPath(storage_key).parts
        if not parts or PurePosixPath(storage_key).is_absolute() or ".." in parts:
            raise ValueError("invalid object storage key")
        normalized = self._safe_path(*parts).relative_to(self.data_root).as_posix()
        return f"{self.config.prefix}/{normalized}" if self.config.prefix else normalized


@lru_cache(maxsize=1)
def get_file_storage() -> FileStorage:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3FileStorage(
            settings.storage_cache_root,
            S3StorageConfig(
                bucket=settings.s3_bucket,
                endpoint_url=settings.s3_endpoint_url,
                region=settings.s3_region,
                access_key_id=settings.s3_access_key_id,
                secret_access_key=settings.s3_secret_access_key,
                prefix=settings.s3_prefix,
                force_path_style=settings.s3_force_path_style,
                server_side_encryption=settings.s3_server_side_encryption,
            ),
        )
    return FileStorage(settings.data_root)
