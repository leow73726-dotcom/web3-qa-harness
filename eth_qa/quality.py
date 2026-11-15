"""重复执行回归套件并把结果分成「稳定通过 / 不稳定 / 稳定失败」。

QA 场景里单跑一次绿灯没有意义：真正要回答的是「这套用例进了 CI 之后，会不会
时红时绿」。所以这里跑 N 轮，用同一用例的通过率做判据，并把失败证据落盘。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STABLE_PASS = "stable-pass"
FLAKY = "flaky"
STABLE_FAIL = "stable-fail"


@dataclass
class CaseResult:
    case_id: str
    runs: int = 0
    passes: int = 0
    durations: list[float] = field(default_factory=list)
    failure_messages: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passes / self.runs if self.runs else 0.0

    @property
    def mean_duration(self) -> float:
        return sum(self.durations) / len(self.durations) if self.durations else 0.0

    @property
    def verdict(self) -> str:
        if self.passes == self.runs:
            return STABLE_PASS
        if self.passes == 0:
            return STABLE_FAIL
        return FLAKY


def _case_id(classname: str, name: str) -> str:
    """去掉文件路径前缀，只留 类名::用例名，方便跨轮次对齐。"""
    short = classname.split(".")[-1] if classname else ""
    return f"{short}::{name}" if short else name


def parse_junit(path: Path) -> list[tuple[str, bool, float, str]]:
    """返回 [(case_id, passed, duration, failure_message)]。"""
    tree = ET.parse(path)
    out: list[tuple[str, bool, float, str]] = []
    for case in tree.iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        duration = float(case.get("time", "0") or 0)
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")
        skipped = case.find("skipped")
        if skipped is not None:
            continue
        passed = failure is None
        message = ""
        if failure is not None:
            message = (failure.get("message") or "").strip()
            if not message:
                message = (failure.text or "").strip()
        out.append((_case_id(classname, name), passed, duration, message))
    return out


def run_suite(python: str, target: Path, runs: int, workdir: Path) -> dict[str, CaseResult]:
    results: dict[str, CaseResult] = {}
    for i in range(1, runs + 1):
        xml_path = workdir / f"junit-run{i}.xml"
        proc = subprocess.run(
            [
                python,
                "-m",
                "pytest",
                str(target),
                "-p",
                "no:cacheprovider",
                "-q",
                "--no-header",
                f"--junitxml={xml_path}",
            ],
            cwd=str(target.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print(f"  run {i}/{runs} -> exit {proc.returncode}")
        if not xml_path.exists():
            print(proc.stdout[-2000:])
            print(proc.stderr[-2000:])
            raise SystemExit(f"pytest produced no junit xml on run {i}")

        for case_id, passed, duration, message in parse_junit(xml_path):
            entry = results.setdefault(case_id, CaseResult(case_id=case_id))
            entry.runs += 1
            entry.durations.append(duration)
            if passed:
                entry.passes += 1
            elif message:
                entry.failure_messages.append(message)
    return results


def _md_escape(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("|", "\\|").strip()


def render_report(results: dict[str, CaseResult], runs: int, out_dir: Path) -> str:
    ordered = sorted(results.values(), key=lambda c: (c.verdict != STABLE_FAIL, c.case_id))
    total = len(ordered)
    stable = sum(1 for c in ordered if c.verdict == STABLE_PASS)
    flaky = sum(1 for c in ordered if c.verdict == FLAKY)
    failing = sum(1 for c in ordered if c.verdict == STABLE_FAIL)

    lines = [
        "# Web3 链上回归 · 质量门禁报告",
        "",
        f"- 生成时间（UTC）：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 执行轮次：{runs}",
        f"- 用例总数：{total}",
        f"- 稳定通过：{stable}",
        f"- 不稳定（flaky）：{flaky}",
        f"- 稳定失败：{failing}",
        "",
        "## 判定规则",
        "",
        "| 结论 | 条件 | 处置 |",
        "| --- | --- | --- |",
        f"| {STABLE_PASS} | 每轮都通过 | 可进 CI 门禁 |",
        f"| {FLAKY} | 部分轮次通过 | 不得进门禁，先定位不确定性来源 |",
        f"| {STABLE_FAIL} | 每轮都失败 | 转缺陷单，阻断合入 |",
        "",
        "## 用例明细",
        "",
        "| 用例 | 结论 | 通过率 | 平均耗时(s) |",
        "| --- | --- | --- | --- |",
    ]
    for c in ordered:
        lines.append(
            f"| `{_md_escape(c.case_id)}` | {c.verdict} | {c.passes}/{c.runs} "
            f"({c.pass_rate:.0%}) | {c.mean_duration:.3f} |"
        )

    bad = [c for c in ordered if c.verdict != STABLE_PASS]
    lines += ["", "## 失败证据", ""]
    if not bad:
        lines.append("无失败用例。")
    else:
        for c in bad:
            lines.append(f"### {c.case_id}")
            lines.append("")
            lines.append(f"- 结论：{c.verdict}，通过率 {c.passes}/{c.runs}")
            for msg in dict.fromkeys(c.failure_messages):
                lines.append(f"- 失败信息：{_md_escape(msg)[:600]}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重复执行 Web3 回归套件并输出质量报告")
    parser.add_argument("--tests", default="tests", help="测试目录")
    parser.add_argument("--runs", type=int, default=3, help="重复轮次")
    parser.add_argument("--out", default="reports", help="报告输出目录")
    parser.add_argument("--python", default=sys.executable, help="用于跑 pytest 的解释器")
    args = parser.parse_args(argv)

    target = Path(args.tests).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"suite={target} runs={args.runs} python={args.python}")
    results = run_suite(args.python, target, args.runs, out_dir)

    report = render_report(results, args.runs, out_dir)
    (out_dir / "QUALITY_REPORT.md").write_text(report, encoding="utf-8")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runs": args.runs,
        "cases": [
            {
                "case_id": c.case_id,
                "verdict": c.verdict,
                "pass_rate": round(c.pass_rate, 4),
                "mean_duration": round(c.mean_duration, 4),
                "failure_messages": c.failure_messages,
            }
            for c in results.values()
        ],
    }
    (out_dir / "quality_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    stable_fail = sum(1 for c in results.values() if c.verdict == STABLE_FAIL)
    flaky = sum(1 for c in results.values() if c.verdict == FLAKY)
    print(f"cases={len(results)} stable_fail={stable_fail} flaky={flaky}")
    print(f"report -> {out_dir / 'QUALITY_REPORT.md'}")
    return 1 if stable_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
