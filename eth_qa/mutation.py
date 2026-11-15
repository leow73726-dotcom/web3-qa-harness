"""变异测试运行器：给被测系统注入人工缺陷，看回归套件能不能抓住。

度量口径：

    变异得分 = 被杀灭的变异体 / 变异体总数

- **被杀灭（killed）**：注入后套件变红 → 说明有用例真的验证了这块行为。
- **存活（survived）**：注入后套件仍然全绿 → **用例空洞**，断言没覆盖到这条契约。

存活的变异体不是「框架 bug」，是**测试套件的缺陷报告**——每一个都要
么补用例杀掉，要么明确写出「为什么不管」。

用法：
    python -m eth_qa.mutation --tests tests --out reports
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from eth_qa.mutants import CONTRACT_MUTANTS, MUTANTS

BASELINE_TIMEOUT = 900
MUTANT_TIMEOUT = 900


@dataclass
class MutantResult:
    name: str
    description: str
    kind: str
    killed: bool
    returncode: int
    seconds: float
    head_of_failure: str = ""


def _run_pytest(
    project_dir: Path,
    tests_dir: Path,
    mutant: str | None = None,
    contract_variant: str | None = None,
) -> tuple[int, float, str]:
    env = dict(os.environ)
    env.pop("ETH_QA_MUTANT", None)
    env.pop("ETH_QA_ERC20_VARIANT", None)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(tests_dir),
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
        "-x",
        "--tb=line",
    ]
    if mutant:
        env["ETH_QA_MUTANT"] = mutant
        cmd += ["-p", "eth_qa.mutant_plugin"]
    if contract_variant:
        env["ETH_QA_ERC20_VARIANT"] = contract_variant

    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        cmd,
        cwd=str(project_dir),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=MUTANT_TIMEOUT,
    )
    seconds = (datetime.now(timezone.utc) - started).total_seconds()
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, seconds, output


def _first_failure_line(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAILED "):
            return stripped[:180]
    return ""


def run_mutation(project_dir: Path, tests_dir: Path, only: list[str] | None = None) -> list[MutantResult]:
    print("[baseline] 先确认未注入时套件是绿的 ...")
    code, seconds, output = _run_pytest(project_dir, tests_dir)
    if code != 0:
        tail = "\n".join(output.strip().splitlines()[-15:])
        raise SystemExit(f"baseline 未通过（exit {code}），无法做变异测试：\n{tail}")
    print(f"[baseline] OK  ({seconds:.1f}s)\n")

    specs: list[tuple[str, str, str]] = [
        (name, desc, "python") for name, (desc, _) in MUTANTS.items()
    ] + [
        (name, desc, "contract") for name, (desc, _) in CONTRACT_MUTANTS.items()
    ]
    if only:
        wanted = set(only)
        specs = [s for s in specs if s[0] in wanted]

    results: list[MutantResult] = []
    for i, (name, description, kind) in enumerate(specs, start=1):
        if kind == "python":
            code, seconds, output = _run_pytest(project_dir, tests_dir, mutant=name)
        else:
            variant = CONTRACT_MUTANTS[name][1]
            code, seconds, output = _run_pytest(
                project_dir, tests_dir, contract_variant=variant
            )
        killed = code != 0
        mark = "KILLED  " if killed else "SURVIVED"
        print(f"[{i}/{len(specs)}] {mark} {name}  ({seconds:.1f}s)")
        results.append(
            MutantResult(
                name=name,
                description=description,
                kind=kind,
                killed=killed,
                returncode=code,
                seconds=round(seconds, 2),
                head_of_failure=_first_failure_line(output) if killed else "",
            )
        )
    return results


def render(results: list[MutantResult], baseline_seconds: float = 0.0) -> str:
    total = len(results)
    killed = sum(1 for r in results if r.killed)
    survived = total - killed
    score = (killed / total * 100) if total else 0.0

    lines = [
        "# 变异测试报告",
        "",
        f"- 生成时间（UTC）：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 变异体总数：{total}",
        f"- 被杀灭：{killed}",
        f"- 存活：{survived}",
        f"- **变异得分：{score:.1f}%**",
        "",
        "## 判定口径",
        "",
        "| 结论 | 含义 | 处置 |",
        "| --- | --- | --- |",
        "| KILLED | 注入缺陷后套件变红 → 这块行为真的被验证过 | 无需动作 |",
        "| SURVIVED | 注入缺陷后套件仍全绿 → **用例空洞** | 补用例，或写明为什么不管 |",
        "",
        "## 变异体明细",
        "",
        "| 变异体 | 层级 | 注入的缺陷 | 结果 | 耗时(s) | 命中的用例 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(results, key=lambda x: (x.killed, x.name)):
        verdict = "KILLED" if r.killed else "**SURVIVED**"
        hit = r.head_of_failure.replace("FAILED ", "") if r.head_of_failure else "—"
        lines.append(f"| `{r.name}` | {r.kind} | {r.description} | {verdict} | {r.seconds} | `{hit}` |")

    survivors = [r for r in results if not r.killed]
    lines += ["", "## 存活的变异体（测试套件的空洞）", ""]
    if not survivors:
        lines.append("无。当前变异体集合全部被杀灭。")
    else:
        for r in survivors:
            lines.append(f"- **`{r.name}`** —— {r.description}")
        lines.append("")
        lines.append("> 每一条都说明：这段行为要么没被断言，要么只被相对断言覆盖（改绝对值也不影响）。")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="对 eth-tester 做变异测试并输出得分")
    parser.add_argument("--tests", default="tests")
    parser.add_argument("--out", default="reports")
    parser.add_argument("--project", default=".", help="项目根目录（含 eth_qa 包）")
    parser.add_argument("--only", nargs="*", help="只跑指定变异体")
    args = parser.parse_args(argv)

    project_dir = Path(args.project).resolve()
    tests_dir = Path(args.tests).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    results = run_mutation(project_dir, tests_dir, args.only)
    report = render(results)
    (out_dir / "MUTATION_REPORT.md").write_text(report, encoding="utf-8")

    total = len(results)
    killed = sum(1 for r in results if r.killed)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": total,
        "killed": killed,
        "survived": total - killed,
        "mutation_score_pct": round(killed / total * 100, 1) if total else 0.0,
        "mutants": [
            {
                "name": r.name,
                "kind": r.kind,
                "description": r.description,
                "killed": r.killed,
                "seconds": r.seconds,
                "hitting_test": r.head_of_failure,
            }
            for r in results
        ],
    }
    (out_dir / "mutation_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n变异得分: {payload['mutation_score_pct']}%  ({killed}/{total})")
    print(f"report -> {out_dir / 'MUTATION_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
