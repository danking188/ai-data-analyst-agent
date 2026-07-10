from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from app.domain.errors import DomainError, validation_error


@dataclass(frozen=True, slots=True)
class ParsedDataset:
    frame: pd.DataFrame
    effective_options: dict[str, Any]
    sheet_name: str | None


class DatasetParser:
    def parse(
        self,
        source_path: Path,
        *,
        source_type: str,
        options: dict[str, Any],
    ) -> ParsedDataset:
        if source_type == "csv":
            parsed = self._parse_csv(source_path, options)
        elif source_type in {"xls", "xlsx"}:
            parsed = self._parse_excel(source_path, source_type, options)
        elif source_type == "parquet":
            parsed = self._parse_parquet(source_path, options)
        else:
            raise DomainError("UNSUPPORTED_FILE_TYPE", "文件类型不受支持", 415)
        self._normalize_columns(parsed.frame)
        if parsed.frame.shape[1] == 0:
            raise validation_error("数据文件不包含字段")
        return parsed

    def write_verified_parquet(self, frame: pd.DataFrame, target: Path) -> tuple[int, int]:
        frame.to_parquet(target, engine="pyarrow", index=False)
        metadata = pq.ParquetFile(target).metadata
        if metadata is None:
            raise validation_error("生成的 Parquet 缺少元数据")
        if metadata.num_rows != len(frame) or metadata.num_columns != len(frame.columns):
            raise validation_error("Parquet 写入后校验失败")
        return metadata.num_rows, metadata.num_columns

    def _parse_csv(self, path: Path, options: dict[str, Any]) -> ParsedDataset:
        requested_encoding = options.get("encoding")
        encodings = (
            [requested_encoding] if requested_encoding else ["utf-8-sig", "utf-8", "gb18030"]
        )
        last_error: Exception | None = None
        for encoding in encodings:
            if not isinstance(encoding, str):
                continue
            try:
                delimiter = options.get("delimiter")
                if delimiter is None:
                    delimiter = self._detect_delimiter(
                        path,
                        encoding,
                        int(options.get("header_row", 0)),
                    )
                self._validate_csv_header(
                    path,
                    encoding,
                    delimiter,
                    int(options.get("header_row", 0)),
                )
                frame = pd.read_csv(
                    path,
                    encoding=encoding,
                    sep=delimiter,
                    header=int(options.get("header_row", 0)),
                )
                effective = dict(options)
                effective.update({"encoding": encoding, "delimiter": delimiter})
                return ParsedDataset(frame, effective, None)
            except UnicodeDecodeError as exc:
                last_error = exc
                continue
            except pd.errors.ParserError as exc:
                raise DomainError(
                    "FILE_CORRUPTED",
                    "CSV 结构无法解析",
                    422,
                    details={"reason": "inconsistent_rows"},
                ) from exc
        raise DomainError(
            "FILE_CORRUPTED",
            "无法识别 CSV 编码",
            422,
            details={"reason": type(last_error).__name__ if last_error else "unknown"},
        )

    def _parse_excel(
        self,
        path: Path,
        source_type: str,
        options: dict[str, Any],
    ) -> ParsedDataset:
        engine = "xlrd" if source_type == "xls" else "openpyxl"
        try:
            workbook = pd.ExcelFile(path, engine=engine)
        except Exception as exc:
            raise DomainError("FILE_CORRUPTED", "Excel 文件无法打开", 422) from exc
        requested_sheet = options.get("sheet_name")
        if requested_sheet is None:
            if len(workbook.sheet_names) != 1:
                raise DomainError(
                    "SHEET_REQUIRED",
                    "工作簿包含多个 Sheet，请选择后重试",
                    422,
                    details={"sheets": workbook.sheet_names},
                )
            requested_sheet = workbook.sheet_names[0]
        if requested_sheet not in workbook.sheet_names:
            raise validation_error(
                "指定的 Sheet 不存在",
                sheets=workbook.sheet_names,
            )
        try:
            frame = pd.read_excel(
                workbook,
                sheet_name=requested_sheet,
                header=int(options.get("header_row", 0)),
            )
        except Exception as exc:
            raise DomainError("FILE_CORRUPTED", "Excel Sheet 无法解析", 422) from exc
        effective = dict(options)
        effective["sheet_name"] = requested_sheet
        return ParsedDataset(frame, effective, str(requested_sheet))

    @staticmethod
    def _parse_parquet(path: Path, options: dict[str, Any]) -> ParsedDataset:
        try:
            frame = pd.read_parquet(path, engine="pyarrow")
        except Exception as exc:
            raise DomainError("FILE_CORRUPTED", "Parquet 文件无法解析", 422) from exc
        return ParsedDataset(frame, dict(options), None)

    @staticmethod
    def _detect_delimiter(path: Path, encoding: str, header_row: int) -> str:
        with path.open(encoding=encoding, newline="") as handle:
            sample = "".join(handle.readline() for _ in range(max(header_row + 5, 5)))
        try:
            return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except csv.Error:
            return ","

    @staticmethod
    def _validate_csv_header(
        path: Path,
        encoding: str,
        delimiter: str,
        header_row: int,
    ) -> None:
        with path.open(encoding=encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            header: list[str] | None = None
            for index, row in enumerate(reader):
                if index == header_row:
                    header = [str(value).strip() for value in row]
                    break
        if not header or any(not value for value in header):
            raise validation_error("CSV 表头包含空字段")
        if len(set(header)) != len(header):
            raise validation_error("CSV 表头包含重复字段")

    @staticmethod
    def _normalize_columns(frame: pd.DataFrame) -> None:
        names = [str(column).strip() for column in frame.columns]
        if any(not name for name in names):
            raise validation_error("字段名不能为空")
        if len(set(names)) != len(names):
            raise validation_error("数据包含重复字段名")
        frame.columns = names
