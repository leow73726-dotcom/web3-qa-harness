"""把 ERC-20 合约（正常版 + 变异体）编译成 Python 产物。

**测试运行时不需要 solc**：这里只生成 `eth_qa/erc20_artifact.py`，
产物（bytecode + ABI）提交进仓库，和 eth-tester 自带四个预编译合约的做法一致。

变异体的用途：让变异测试能覆盖到**合约层**，而不只是 eth-tester 的 Python 层。
做法是编译出「故意写错的合约」，部署它跑同一套 ERC-20 用例，看能不能被抓到。

用法：
    python scripts/build_erc20.py        # 需要 ../tools/solc.exe
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / "contracts"
# 编译器不进仓库（约 9.5MB）；用环境变量指定，或放到 tools/solc.exe
#   下载：https://binaries.soliditylang.org/windows-amd64/  (solc-windows-amd64-v0.8.38+...)
SOLC = Path(os.environ.get("SOLC_BIN", ROOT / "tools" / "solc.exe"))
OUT = ROOT / "eth_qa" / "erc20_artifact.py"

# Solidity 合约名 -> 产物里的变体名
VARIANT_CONTRACTS = {
    "SimpleERC20": "good",
    "NoAllowanceDecrementERC20": "no_allowance_decrement",
    "NoBalanceCheckERC20": "no_balance_check",
}

HEADER = '''"""ERC-20 编译产物 —— 由 scripts/build_erc20.py 生成，请勿手改。

Solc 版本：0.8.38
源文件：contracts/SimpleERC20.sol（正常版）+ contracts/MutantsERC20.sol（变异体）

测试运行时**不需要 solc**，只要这里的 bytecode 与 ABI。
"""

from __future__ import annotations

'''


def compile_contracts(solc: Path, sources: list[Path]) -> dict[str, dict]:
    if not solc.exists():
        raise SystemExit(f"找不到 solc：{solc}")

    proc = subprocess.run(
        [str(solc), "--combined-json", "abi,bin"] + [str(s) for s in sources],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(f"solc 编译失败：\n{proc.stdout}\n{proc.stderr}")

    payload = json.loads(proc.stdout)
    compiled: dict[str, dict] = {}
    for key, entry in payload["contracts"].items():
        name = key.rsplit(":", 1)[-1]
        abi = json.loads(entry["abi"]) if isinstance(entry["abi"], str) else entry["abi"]
        compiled[name] = {"abi": abi, "bin": entry["bin"]}
    return compiled


def abi_to_index(abi: list[dict]) -> dict[str, dict]:
    return {
        item["name"]: item
        for item in abi
        if item.get("type") in ("function", "event") and item.get("name")
    }


def main() -> int:
    sources = [CONTRACTS_DIR / "SimpleERC20.sol", CONTRACTS_DIR / "MutantsERC20.sol"]
    compiled = compile_contracts(SOLC, sources)

    base = compiled["SimpleERC20"]
    abi = base["abi"]
    constructor = next((i for i in abi if i.get("type") == "constructor"), None)
    ctor_types = [i["type"] for i in (constructor or {}).get("inputs", [])]

    variants = {v: compiled[c]["bin"] for c, v in VARIANT_CONTRACTS.items() if c in compiled}

    lines = [HEADER]
    lines.append("# 构造函数参数类型（string _name, string _symbol, uint8 _decimals, uint256 _supply）")
    lines.append(f"ERC20_CONSTRUCTOR_TYPES = {ctor_types!r}")
    lines.append("")
    lines.append("ERC20_ABI: dict[str, dict] = " + repr(abi_to_index(abi)))
    lines.append("")
    lines.append(
        "ERC20_EVENTS: dict[str, dict] = "
        + repr({i["name"]: i for i in abi if i.get("type") == "event"})
    )
    lines.append("")
    lines.append(
        "ERC20_ERRORS: dict[str, dict] = "
        + repr({i["name"]: i for i in abi if i.get("type") == "error"})
    )
    lines.append("")
    lines.append("# 正常版 bytecode")
    lines.append(f'ERC20_BYTECODE = "{variants["good"]}"')
    lines.append("")
    lines.append("# 合约层变异体：变体名 -> 部署 bytecode（ABI 与正常版一致）")
    lines.append("ERC20_MUTANT_BYTECODES: dict[str, str] = {")
    for name, code in variants.items():
        if name != "good":
            lines.append(f'    "{name}": "{code}",')
    lines.append("}")
    lines.append("")
    lines.append("ERC20_DECIMALS = 18")
    lines.append('ERC20_NAME = "Shushu Test Token"')
    lines.append('ERC20_SYMBOL = "SHT"')
    lines.append("ERC20_INITIAL_SUPPLY = 1_000_000 * 10**ERC20_DECIMALS")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"wrote {OUT}  (正常版 {len(variants['good']) // 2} bytes, "
        f"变异体 {len(variants) - 1} 个, {len(abi_to_index(abi))} 个条目)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
