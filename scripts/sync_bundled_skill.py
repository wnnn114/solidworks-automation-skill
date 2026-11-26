"""生成 CAD Studio 桌面包内嵌的运行时 Skill 快照。"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SKILL = ROOT / "apps/workbench-ui/src-tauri/resources/skill"

TOP_LEVEL_FILES = (
    "README.md",
    "SKILL.md",
    "SUBSKILLS.md",
    "capabilities.yaml",
    "golden-workflows.yaml",
    "requirements.txt",
    "requirements-mesh.txt",
    "requirements-occt.txt",
    "requirements-pdf.txt",
)
RUNTIME_ROOTS = (
    "agents",
    "dotnet",
    "examples",
    "mcp-server",
    "profiles/drc",
    "references",
    "scripts",
    "subskills",
    "apps/desktop/cad_workbench",
)
RUNTIME_FILES = ("apps/desktop/__init__.py",)
SKIPPED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "bin",
    "build",
    "dist",
    "node_modules",
    "obj",
    "output",
    "release-output",
}
SKIPPED_SUFFIXES = {".pyc", ".pyo"}
PRIVATE_SUFFIXES = {".env", ".key", ".pem", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".log", ".jsonl", ".bak"}
PRIVATE_NAMES = {"auth.json", "credentials.json", "secret.key", "id_rsa", "id_ed25519", ".npmrc", ".pypirc"}
PRIVATE_CONTENT = (
    ("private-key", re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("service-token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{25,}|AKIA[A-Z0-9]{16})\b")),
    ("personal-email", re.compile(rb"[A-Za-z0-9._%+\-]+@(?:qq|163|126|gmail|hotmail|outlook|icloud|protonmail)\.com\b", re.I)),
)
HOME_PATH = re.compile(rb"(?:[A-Za-z]:[\\/]+Users[\\/]+|/(?:Users|home)/)([^\\/\s\"'<>]+)")
EXAMPLE_USERS = {b"user", b"you", b"current", b"public", b"test", b"test-user", b"example", b"username"}


def validate_public_payload(payload: dict[str, bytes]) -> None:
    """拒绝高置信度敏感内容；错误只报告文件名和规则，不回显秘密。"""
    for name, data in payload.items():
        for rule, pattern in PRIVATE_CONTENT:
            if pattern.search(data):
                raise ValueError(f"发布隐私检查失败 ({rule}): {name}")
        for match in HOME_PATH.finditer(data):
            if match.group(1).lower() not in EXAMPLE_USERS:
                raise ValueError(f"发布隐私检查失败 (personal-home-path): {name}")


def _tracked_files(root: Path) -> set[Path]:
    """只接受本仓库的 Git 索引，禁止递归打包开发者未提交的本地文件。"""
    if not (root / ".git").exists():
        raise ValueError("发布运行时必须从 Git 检出构建，不能从无索引目录递归收集")
    try:
        top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, stderr=subprocess.PIPE).decode("utf-8").strip()
        if Path(top).resolve() != root:
            raise ValueError("发布源目录必须是 Git 仓库根目录")
        names = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=root, stderr=subprocess.PIPE).decode("utf-8")
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("无法读取发布源 Git 索引，拒绝打包") from error
    return {Path(name) for name in names.split("\0") if name}


def _validate_target(root: Path, target: Path) -> None:
    """@brief 限制同步目标只能是仓库内的 Tauri resources/skill。"""
    expected_parent = (root / "apps/workbench-ui/src-tauri/resources").resolve()
    resolved_target = target.resolve()
    if resolved_target.parent != expected_parent or resolved_target.name != "skill":
        raise ValueError(f"拒绝写入非预期内嵌 Skill 目录: {resolved_target}")


def _is_runtime_file(path: Path, source_root: Path) -> bool:
    """@brief 排除缓存、构建产物和字节码，只保留可发布源文件。"""
    relative = path.relative_to(source_root)
    name = path.name.casefold()
    return (
        not any(part.casefold() in SKIPPED_DIRECTORIES for part in relative.parts)
        and path.suffix.casefold() not in SKIPPED_SUFFIXES | PRIVATE_SUFFIXES
        and name not in PRIVATE_NAMES
        and not name.startswith(".env")
        and ".local." not in name
    )


def collect_runtime_files(root: Path) -> dict[Path, Path]:
    """@brief 收集内嵌 Skill 所需的源文件，键为相对仓库路径。"""
    root = root.resolve(strict=True)
    tracked = _tracked_files(root)
    files: dict[Path, Path] = {}
    for relative_name in (*TOP_LEVEL_FILES, *RUNTIME_FILES):
        source = root / relative_name
        if not source.is_file():
            raise FileNotFoundError(f"内嵌 Skill 源文件缺失: {source}")
        if Path(relative_name) not in tracked:
            raise ValueError(f"内嵌 Skill 必需文件未被 Git 跟踪: {relative_name}")
        files[Path(relative_name)] = source
    for relative_root in RUNTIME_ROOTS:
        source_root = root / relative_root
        if not source_root.is_dir():
            raise FileNotFoundError(f"内嵌 Skill 源目录缺失: {source_root}")
        for relative in sorted(tracked):
            if not relative.is_relative_to(Path(relative_root)):
                continue
            source = root / relative
            if source.is_file() and _is_runtime_file(source, source_root):
                files[source.relative_to(root)] = source
    for relative, source in files.items():
        if source.is_symlink() or not source.resolve(strict=True).is_relative_to(root):
            raise ValueError(f"发布源文件越出仓库或是符号链接: {relative.as_posix()}")
    validate_public_payload({relative.as_posix(): source.read_bytes() for relative, source in files.items()})
    return files


def sync_bundled_skill(root: Path = ROOT, target: Path = BUNDLED_SKILL) -> dict[str, object]:
    """@brief 同步运行时文件并清理目标中已无源文件的陈旧副本。"""
    root = root.resolve()
    target = target.resolve()
    _validate_target(root, target)
    source_files = collect_runtime_files(root)
    target.mkdir(parents=True, exist_ok=True)
    for relative_path, source in source_files.items():
        destination = target / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    pruned: list[str] = []
    expected = set(source_files)
    for bundled_file in sorted(path for path in target.rglob("*") if path.is_file()):
        relative_path = bundled_file.relative_to(target)
        if relative_path not in expected:
            bundled_file.unlink()
            pruned.append(relative_path.as_posix())
    for directory in sorted((path for path in target.rglob("*") if path.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return {
        "status": "pass",
        "target": str(target),
        "files": len(source_files),
        "pruned": pruned,
    }


def main() -> int:
    """@brief 命令行入口。"""
    parser = argparse.ArgumentParser(description="同步 CAD Studio 内嵌 Skill")
    parser.parse_args()
    print(json.dumps(sync_bundled_skill(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
