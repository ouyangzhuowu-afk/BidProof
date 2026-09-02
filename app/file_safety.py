from pathlib import Path, PurePosixPath
import zipfile


MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
BLOCKED_ARCHIVE_SUFFIXES = {".exe", ".dll", ".com", ".scr", ".bat", ".cmd", ".ps1", ".vbs", ".js"}
PDF_ACTIVE_TOKENS = (b"/JavaScript", b"/JS", b"/OpenAction", b"/Launch", b"/EmbeddedFile")


def scan_upload_safety(path: Path) -> list[str]:
    issues: list[str] = []
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        payload = path.read_bytes()
        if any(token in payload for token in PDF_ACTIVE_TOKENS):
            issues.append("PDF 包含 JavaScript、自动打开动作或嵌入文件等活动内容")
    if suffix in {".docx", ".xlsx", ".pptx"}:
        issues.extend(_scan_ooxml(path))
    return issues


def _scan_ooxml(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                issues.append("Office 压缩包条目数量异常")
            if sum(item.file_size for item in entries) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                issues.append("Office 压缩包解压后体积超过安全限制")
            for item in entries:
                normalized = item.filename.replace("\\", "/")
                parts = PurePosixPath(normalized).parts
                if normalized.startswith("/") or ".." in parts:
                    issues.append("Office 压缩包包含路径穿越条目")
                    break
            lowered = {item.filename.casefold() for item in entries}
            if any(name.endswith("vbaproject.bin") for name in lowered):
                issues.append("Office 文件包含宏项目，当前安全策略拒绝处理")
            if any(Path(name).suffix.casefold() in BLOCKED_ARCHIVE_SUFFIXES for name in lowered):
                issues.append("Office 压缩包包含可执行或脚本文件")
            for item in entries:
                if not item.filename.casefold().endswith(".rels") or item.file_size > 2 * 1024 * 1024:
                    continue
                relationship_xml = archive.read(item).casefold()
                if b'targetmode="external"' in relationship_xml and any(scheme in relationship_xml for scheme in (b"javascript:", b"file:", b"ms-msdt:")):
                    issues.append("Office 文件包含不安全的外部关系")
                    break
    except (OSError, zipfile.BadZipFile):
        issues.append("Office 压缩包结构无效")
    return list(dict.fromkeys(issues))

