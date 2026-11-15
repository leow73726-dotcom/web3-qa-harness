"""统计回归套件对 eth-tester **公开 API** 的覆盖率。

为什么不做「智能合约行覆盖率」：EVM 字节码覆盖率需要额外插桩，成本高且本轮预算外。
但 QA 视角下有一个同样有意义、且可以精确计算的指标：

    被测库的公开 API，到底有多少条被用例真的调用过？

这直接对应「接口覆盖」这个概念：一个方法从来没被调用，就说明它的行为完全没被验证。
比「跑了多少条用例」更能说明测试的深度。

用法：
    python -m eth_qa.api_coverage --tests tests --out reports
"""

from __future__ import annotations

import argparse
import functools
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from eth_tester import EthereumTester

CALLED: set[str] = set()


def public_api() -> list[str]:
    """收集 EthereumTester 的公开方法名（排除 dunder 与私有）。"""
    names = []
    for name in dir(EthereumTester):
        if name.startswith("_"):
            continue
        attr = inspect.getattr_static(EthereumTester, name)
        if inspect.isfunction(attr):
            names.append(name)
    return sorted(names)


def _patch() -> dict[str, Any]:
    originals: dict[str, Any] = {}
    for name in public_api():
        original = EthereumTester.__dict__.get(name)
        if not inspect.isfunction(original):
            continue
        originals[name] = original

        @functools.wraps(original)
        def wrapper(self, *args, __name=name, __fn=original, **kwargs):
            CALLED.add(__name)
            return __fn(self, *args, **kwargs)

        setattr(EthereumTester, name, wrapper)
    return originals


def _unpatch(originals: dict[str, Any]) -> None:
    for name, original in originals.items():
        setattr(EthereumTester, name, original)


class _Recorder:
    def pytest_sessionstart(self, session):  # noqa: ARG002
        CALLED.clear()


def render(api: list[str], called: set[str], out_dir: Path) -> str:
    covered = [m for m in api if m in called]
    missed = [m for m in api if m not in called]
    pct = (len(covered) / len(api) * 100) if api else 0.0

    lines = [
        "# 公开 API 覆盖率",
        "",
        f"- 生成时间（UTC）：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 被测类：`eth_tester.EthereumTester`",
        f"- 公开方法总数：{len(api)}",
        f"- 被用例调用过：{len(covered)}",
        f"- 覆盖率：**{pct:.1f}%**",
        "",
        "## 已覆盖",
        "",
        "| 方法 |",
        "| --- |",
    ]
    lines += [f"| `{m}` |" for m in covered]
    lines += ["", "## 未覆盖（下一步可补）", "", "| 方法 |", "| --- |"]
    lines += [f"| `{m}` |" for m in missed] if missed else ["| 无 |"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统计对 eth-tester 公开 API 的覆盖率")
    parser.add_argument("--tests", default="tests")
    parser.add_argument("--out", default="reports")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    api = public_api()
    originals = _patch()
    try:
        pytest_args = [str(Path(args.tests).resolve()), "-p", "no:cacheprovider", "-q", "--no-header"]
        if args.quiet:
            pytest_args.append("--tb=no")
        code = pytest.main(pytest_args, plugins=[_Recorder()])
    finally:
        _unpatch(originals)

    report = render(api, CALLED, out_dir)
    (out_dir / "API_COVERAGE.md").write_text(report, encoding="utf-8")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(api),
        "covered": sorted(m for m in api if m in CALLED),
        "missed": sorted(m for m in api if m not in CALLED),
        "coverage_pct": round(len([m for m in api if m in CALLED]) / len(api) * 100, 1) if api else 0.0,
        "pytest_exit": int(code),
    }
    (out_dir / "api_coverage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    covered_n = len(payload["covered"])
    print(f"public_api={len(api)} covered={covered_n} pct={payload['coverage_pct']}%")
    print(f"report -> {out_dir / 'API_COVERAGE.md'}")
    return 0 if int(code) == 0 else int(code)


if __name__ == "__main__":
    sys.exit(main())
