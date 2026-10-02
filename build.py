#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CXHarvest 的可复现 PyInstaller 构建入口。

默认生成 ``dist/<应用名>/`` 目录。使用 ``--no-clean`` 可复用上一次
PyInstaller 工作目录，使用 ``--dry-run`` 可在未安装 PyInstaller 时检查参数。
"""

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from core.version import APP_ICON, APP_NAME, __version__


PROJECT_ROOT = Path(__file__).resolve().parent


def parse_version_tuple(version: str) -> Tuple[int, int, int, int]:
    """将语义版本转换成 Windows 文件版本需要的四段整数。"""
    parts = []
    for piece in str(version).split("."):
        try:
            parts.append(max(0, int(piece)))
        except (TypeError, ValueError):
            parts.append(0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])  # type: ignore[return-value]


def create_version_file(
    root: Path = PROJECT_ROOT,
    app_name: str = APP_NAME,
    version: str = __version__,
) -> Path:
    """生成供 PyInstaller 使用的 Windows 版本资源文件。"""
    build_dir = root / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    version_file = build_dir / "version_info.autogen.txt"

    major, minor, patch, build = parse_version_tuple(version)
    version_tuple = f"({major}, {minor}, {patch}, {build})"
    version_text = f"{major}.{minor}.{patch}.{build}"
    content = textwrap.dedent(
        f"""\
        # UTF-8
        VSVersionInfo(
          ffi=FixedFileInfo(
            filevers={version_tuple},
            prodvers={version_tuple},
            mask=0x3f,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0)
            ),
          kids=[
            StringFileInfo(
              [
              StringTable(
                u'080404b0',
                [
                StringStruct(u'CompanyName', u'重庆彭于晏'),
                StringStruct(u'FileDescription', u'{app_name}'),
                StringStruct(u'FileVersion', u'{version_text}'),
                StringStruct(u'InternalName', u'cxharvest'),
                StringStruct(u'LegalCopyright', u'Copyright (c) 2026 wjn6'),
                StringStruct(u'OriginalFilename', u'{app_name}.exe'),
                StringStruct(u'ProductName', u'{app_name}'),
                StringStruct(u'ProductVersion', u'{version_text}')])
              ]),
            VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
          ]
        )
        """
    )
    version_file.write_text(content, encoding="utf-8")
    return version_file


def build_pyinstaller_args(
    root: Path = PROJECT_ROOT,
    clean: bool = True,
    console: bool = False,
) -> List[str]:
    """构造唯一的 PyInstaller 参数源，供本地和 CI 共用。"""
    root = root.resolve()
    version_file = create_version_file(root)
    args = [
        str(root / "main.py"),
        f"--name={APP_NAME}",
        "--onedir",
        "--console" if console else "--noconsole",
        "--noconfirm",
        "--contents-directory=libs",
        f"--version-file={version_file}",
        f"--distpath={root / 'dist'}",
        f"--workpath={root / 'build'}",
        f"--specpath={root}",
        f"--add-data={root / 'README.md'}{os.pathsep}.",
        f"--add-data={root / 'assets'}{os.pathsep}assets",
        "--collect-all=qfluentwidgets",
    ]
    if clean:
        args.append("--clean")

    icon_path = root / APP_ICON
    if icon_path.exists():
        args.append(f"--icon={icon_path}")
    return args


def validate_project(root: Path = PROJECT_ROOT) -> None:
    """在启动耗时构建前报告缺失的必需文件。"""
    required = [root / "main.py", root / "README.md", root / "assets"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("缺少构建所需文件: " + ", ".join(missing))


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建 CXHarvest 桌面应用")
    parser.add_argument(
        "--no-clean", action="store_true",
        help="保留 PyInstaller 缓存以加快重复构建",
    )
    parser.add_argument(
        "--console", action="store_true",
        help="保留控制台窗口，便于调试启动问题",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅验证项目并打印 PyInstaller 参数",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _create_parser().parse_args(argv)
    try:
        validate_project()
        pyinstaller_args = build_pyinstaller_args(
            clean=not args.no_clean,
            console=args.console,
        )
    except (OSError, ValueError) as exc:
        print(f"构建配置错误: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps(pyinstaller_args, ensure_ascii=False, indent=2))
        return 0

    try:
        import PyInstaller.__main__
    except ImportError:
        print(
            "未安装 PyInstaller。请先运行: python -m pip install pyinstaller",
            file=sys.stderr,
        )
        return 2

    print(f"正在构建 {APP_NAME} v{__version__} ...")
    PyInstaller.__main__.run(pyinstaller_args)
    print(f"构建完成: {PROJECT_ROOT / 'dist' / APP_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
