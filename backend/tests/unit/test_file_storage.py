import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi import UploadFile

from app.storage.files import FileStorage, S3FileStorage, S3StorageConfig


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.upload_extra_args: dict[str, str] | None = None

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        **kwargs: Any,
    ) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()
        self.upload_extra_args = kwargs.get("ExtraArgs")

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        Path(filename).write_bytes(self.objects[(bucket, key)])

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)

    def list_objects_v2(self, **request: Any) -> dict[str, Any]:
        bucket = str(request["Bucket"])
        prefix = str(request["Prefix"])
        return {
            "Contents": [
                {"Key": key}
                for object_bucket, key in self.objects
                if object_bucket == bucket and key.startswith(prefix)
            ],
            "IsTruncated": False,
        }

    def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
        for item in Delete["Objects"]:
            self.objects.pop((Bucket, item["Key"]), None)

    def head_bucket(self, *, Bucket: str) -> None:
        assert Bucket


def test_storage_paths_cannot_escape_data_root(tmp_path: Path) -> None:
    storage = FileStorage(tmp_path)
    with pytest.raises(ValueError):
        storage._safe_path("tmp", "..", "..", "escape")


def test_display_name_removes_paths_and_control_characters() -> None:
    assert FileStorage._safe_display_name("../../bad\x00name.csv") == "badname.csv"


def test_s3_storage_restores_artifact_after_local_cache_is_removed(tmp_path: Path) -> None:
    client = FakeS3Client()
    storage = S3FileStorage(
        tmp_path,
        S3StorageConfig(
            bucket="datatrace-test",
            endpoint_url="https://objects.example.test",
            region="auto",
            access_key_id="test-key",
            secret_access_key="test-secret",
            prefix="production",
            server_side_encryption="AES256",
        ),
        client=client,
    )
    storage_key = storage.write_artifact_file(
        project_id="prj_1",
        artifact_id="art_1",
        file_name="report.html",
        content=b"persistent report",
    )
    cached = FileStorage.resolve_key(storage, storage_key)
    cached.unlink()

    restored = storage.resolve_key(storage_key)

    assert restored.read_bytes() == b"persistent report"
    assert client.objects[("datatrace-test", f"production/{storage_key}")] == b"persistent report"
    assert client.upload_extra_args == {"ServerSideEncryption": "AES256"}
    storage.healthcheck()


def test_s3_storage_commits_derived_parquet_and_rejects_unsafe_keys(tmp_path: Path) -> None:
    client = FakeS3Client()
    storage = S3FileStorage(
        tmp_path,
        S3StorageConfig(
            bucket="datatrace-test",
            endpoint_url=None,
            region="us-east-1",
            access_key_id=None,
            secret_access_key=None,
        ),
        client=client,
    )
    parquet = storage.temp_parquet_path("job_1")
    parquet.write_bytes(b"PAR1-test")

    storage_key = storage.commit_derived_parquet(
        project_id="prj_1",
        dataset_id="ds_1",
        version_id="dsv_1",
        parquet_path=parquet,
    )
    FileStorage.resolve_key(storage, storage_key).unlink()

    assert storage.resolve_key(storage_key).read_bytes() == b"PAR1-test"
    with pytest.raises(ValueError):
        storage.resolve_key("../../escape")


def test_s3_storage_stages_upload_for_a_separate_worker(tmp_path: Path) -> None:
    client = FakeS3Client()
    storage = S3FileStorage(
        tmp_path,
        S3StorageConfig(
            bucket="datatrace-test",
            endpoint_url=None,
            region="us-east-1",
            access_key_id=None,
            secret_access_key=None,
        ),
        client=client,
    )
    upload = UploadFile(filename="orders.csv", file=BytesIO(b"name,value\na,1\n"))

    staged = asyncio.run(storage.stage_upload(upload, job_id="job_1", max_bytes=1024))
    FileStorage.resolve_key(storage, staged.storage_key).unlink()

    assert storage.resolve_key(staged.storage_key).read_bytes() == b"name,value\na,1\n"
    storage.remove_staged("job_1")
    assert client.objects == {}


def test_local_ingestion_can_be_rolled_back_after_database_failure(tmp_path: Path) -> None:
    storage = FileStorage(tmp_path)
    staged = storage._safe_path("tmp", "job_1", "source.csv")
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"name,value\na,1\n")
    parquet = storage.temp_parquet_path("job_1")
    parquet.write_bytes(b"PAR1-test")

    source_key, data_key = storage.commit_ingestion(
        project_id="prj_1",
        dataset_id="ds_1",
        version_id="dsv_1",
        source_path=staged,
        parquet_path=parquet,
        source_type="csv",
    )
    storage.rollback_ingestion(
        staged_key="tmp/job_1/source.csv",
        source_key=source_key,
        data_key=data_key,
    )

    assert staged.read_bytes() == b"name,value\na,1\n"
    assert not storage.resolve_key(source_key).exists()
    assert not storage.resolve_key(data_key).exists()
