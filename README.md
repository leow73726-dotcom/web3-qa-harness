# eth-qa

> A pytest harness for [eth-tester](https://github.com/ApeWorX/eth-tester): fixtures, contract
> handles, property-based invariants, mutation testing — **including contract-level mutants** —
> and a CI quality gate.
>
> Level: **84 test cases · 26 test classes · mutation score 17/17 (100%) · public-API coverage 78.1%**

一个给以太坊测试用的「练习场」配标准考试流程的项目：在被测库 `eth-tester` 之上补齐 pytest
集成层，并用**不变量测试**与**变异测试**证明这套用例真的能抓 bug，而不是只会打绿灯。

---

## 1. 它解决什么问题

`eth-tester` 是一个内存以太坊节点，用来测 dApp / 合约。它提供了链和账户，但**没有 pytest 集成**：

- 每个用例都要自己 `EthereumTester()`、取账户、写部署辅助函数
- 调用合约要手拼 4 字节选择器 + ABI 编码 + 解码返回值 + 解码事件
- 它有 10+ 个公开方法，没人知道自己的用例覆盖了几个
- 它自己有一致性套件，但不给使用者用

这个仓库把那四件事补上，并且加了两层「度量」——不变量测试和变异测试。

---

## 2. 快速开始

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate

pip install -e .

python -m pytest                       # 84 条用例，约 10 秒
```

不需要 Docker、不需要节点、不需要测试网、不需要 GPU、**测试期不需要 solc**
（ERC-20 的编译产物已提交）。

---

## 3. 质量度量

| 度量 | 结果 | 命令 |
| --- | --- | --- |
| 回归套件 | **84 passed**（26 个测试类，约 10s） | `python -m pytest` |
| 公开 API 面覆盖率 | **25 / 32 = 78.1%** | `python -m eth_qa.api_coverage --tests tests` |
| 变异得分 | **17 / 17 = 100%** | `python -m eth_qa.mutation --tests tests` |
| CI 质量门禁 | 3 轮全 `stable-pass`，0 flaky | `python -m eth_qa.quality --tests tests --runs 3` |

> 「公开 API 面覆盖率」= 被测类 `EthereumTester` 的 32 个公开方法里，有多少被用例真的
> 调用过。它**不是**代码覆盖率，也不是 EVM 字节码覆盖率——口径必须说清。

---

## 4. 覆盖了什么

| 层次 | 测试类 | 条数 | 重点 |
| --- | --- | --- | --- |
| 链层 | `TestAccounts` `TestNativeTransfer` `TestContract` `TestTransactionReceipt` `TestSnapshotIsolation` | 16 | 账户基线、转账记账、gas 计费、回执契约、快照回滚 |
| 工具合约 | `TestThrowsContract` `TestMathContract` `TestEmitterContract` `TestGasBurnerContract` | 19 | revert 行为、状态机、事件与 indexed 参数、区块依赖 gas |
| **业务合约（ERC-20）** | `TestMetadataAndInitialAllocation` `TestTransfer` `TestApproval` `TestInvariants` | **19** | 授权模型、自定义错误解码、零地址/零金额边界 |
| 后端矩阵 | `TestAutoMineDisabled` `TestMockBackend` | 8 | 手动挖矿、mock 后端降级契约 |
| 公开 API 面 | `TestQueryApi` `TestChainLifecycle` `TestFilters` | 10 | nonce / storage / logs / fee history / 重置 / 过滤器 |
| 不变量 | `TestConservationLaw` `TestFailureAccounting` `TestNonceAndReadOnly` `TestSnapshotIdempotence` | 7 | 守恒律、失败记账、只读无副作用 |
| 变异补强 | `TestAbsoluteValues` `TestReceiptContract` `TestFeeHistoryWindow` `TestStorageSlotSemantics` | 5 | 由存活变异体反推出的缺失断言 |

---

## 5. 两个非常规做法

### 5.1 不变量测试（`tests/test_invariants.py`）

普通用例只覆盖你想得到的场景；不变量覆盖你想不到的组合。

核心断言是**守恒律**：

> 任意交易序列之后，全链余额总和必须**正好**减少这笔交易烧掉的 gas。

用 [Hypothesis](https://hypothesis.readthedocs.io/) 随机生成 1–6 笔转账，每笔之后重算全链总和。
失败时 Hypothesis 会**自动收缩**成最小反例（比如「2 笔交易就能复现」），而不是甩给你一段噪声序列。

顺带锁住的几条规则（都是容易被写错的）：

| 不变量 | 实测行为 |
| --- | --- |
| revert 的交易 | 不转移价值，但 **gas 照烧** |
| 余额不足（校验失败） | **零副作用**：不扣 gas、不动 nonce、不产块 |
| 自转账 `from == to` | 净变化**正好是 −gas** |
| 只读 `call` | 不产块、不动余额、不改 nonce |
| 快照回滚 | **幂等**：回滚 N 次状态相同 |

### 5.2 变异测试（`eth_qa/mutation.py`）

**故意把被测系统改坏**，看套件能不能抓住：

- 套件变红 → 变异体「被杀灭」→ 这块行为真的被断言保护着
- 套件仍全绿 → 变异体「存活」→ **这是测试套件的漏洞报告**

17 个变异体分两层：

| 层级 | 数量 | 举例 |
| --- | --- | --- |
| Python 层（给 `EthereumTester` 方法打补丁） | 15 | 交易金额被抹成 0、失败交易也报 `status=1`、只读调用也产块、回执 type 改成 `0x0` |
| **合约层（编译出写错的 ERC-20）** | 2 | `transferFrom` 不扣 allowance、`_transfer` 跳过余额检查 |

合约层的做法：`contracts/MutantsERC20.sol` 里两个故意写错的合约，编译成字节码提交；
`erc20` fixture 读环境变量 `ETH_QA_ERC20_VARIANT` 决定部署哪个变体，跑同一套 19 条用例。

**第一轮结果不是 100%，是 80%（12/15）**，3 个存活变异体暴露出真实的断言空洞：

| 存活变异体 | 暴露的空洞 | 补的断言 |
| --- | --- | --- |
| `balance_off_by_one` | 所有余额断言都是相对值（前后做差），整体偏移 1 wei 抓不到 | 创世余额精确等于 1,000,000 ETH |
| `receipt_type_legacy` | `type` 只在 `get_transaction_by_hash` 上验过，**回执上的没验** | 回执本身也必须是 `0x2` |
| `fee_history_truncated` | 只断言「非空」，没断言**条数等于窗口** | 请求 3 条必须返 3 条 |

补 5 条断言后 15/15，再加 2 个合约层变异体 → **17/17**。

> 这一步的真正价值不是 100%，而是它证明了：**「用例全绿」≠「行为被验证」**。

---

## 6. 一个真实缺陷（附带修复补丁）

写负向用例时发现 `eth-tester` 的一个契约缺陷 **D-01**：

`eth_tester.exceptions.ValidationError` 与 py-evm 后端实际抛出的
`eth_utils.exceptions.ValidationError` 是**两个同名但互不继承**的类，而 `main.py`
在 backend 边界没有做异常归一化。后果是按官方文档写的 `pytest.raises(ValidationError)`
**永远接不住**余额校验错误；更糟的是异常穿透后可能被外层 `except Exception` 吞掉，
把「没测到」伪装成「测过了」。

- 缺陷说明：[`docs/D-01-defect.md`](docs/D-01-defect.md)
- 修复补丁：[`docs/patches/D-01.patch`](docs/patches/D-01.patch)（`git apply` 可应用）
- 修复验证：补丁应用后 `demo_defect` 从 3/3 判红转为全绿，同时回归锁用例按设计转红

> 修复方向我一开始写错过：直觉上「让公开异常继承后端异常」，实测**无效**——
> `pytest.raises(X)` 捕获的是 X 的实例，把 A 变成 B 的子类不会让 B 的实例变成 A 的实例。
> 正确做法是 re-export 别名。这个坑记录在缺陷说明里。

---

## 7. 目录结构

```
.
├── eth_qa/                     # 被测工具之上补的工程层
│   ├── plugin.py               # 12 个 pytest fixture（链 / 账户 / 部署 / 快照 / 合约 / 后端矩阵）
│   ├── contracts.py            # 合约句柄：ABI 编解码、事件解码、custom error 解码
│   ├── quality.py              # CI 质量门禁：N 轮 → stable-pass / flaky / stable-fail
│   ├── api_coverage.py         # 公开 API 面覆盖率
│   ├── mutants.py              # 17 个变异体注册表（15 Python + 2 合约）
│   ├── mutation.py             # 变异测试运行器 + 杀灭率报告
│   ├── mutant_plugin.py        # 按环境变量注入变异体
│   └── erc20_artifact.py       # ERC-20 编译产物（bytecode + ABI + 2 个变异体字节码）
├── contracts/
│   ├── SimpleERC20.sol         # 自写自包含 ERC-20（solc 0.8.38）
│   └── MutantsERC20.sol        # 2 个故意写错的变异体
├── scripts/build_erc20.py      # 一次性编译脚本（开发期用，测试期不需要 solc）
├── tests/                      # 84 条用例
├── demo_defect/                # 演示用：故意按「文档写法」写的错误用例（必红）
├── docs/                       # 缺陷说明 + 修复补丁
└── conftest.py                 # 注册插件，免安装即可跑
```

---

## 8. 复现每一项指标

```bash
# 主套件
python -m pytest

# 单独看 ERC-20 业务合约
python -m pytest tests/test_erc20.py -v

# 单独看属性测试
python -m pytest tests/test_invariants.py -v

# 公开 API 面覆盖率 → 生成 reports/API_COVERAGE.md
python -m eth_qa.api_coverage --tests tests --out reports

# 变异测试 → 生成 reports/MUTATION_REPORT.md（约 2 分钟）
python -m eth_qa.mutation --tests tests --out reports

# CI 质量门禁（3 轮）→ 生成 reports/QUALITY_REPORT.md
python -m eth_qa.quality --tests tests --runs 3 --out reports

# 反例演示：这个套件应当稳定判红（exit 1）
python -m eth_qa.quality --tests demo_defect --runs 3 --out reports-demo

# 可选：重新编译 ERC-20（需先下载 solc 0.8.38，产物已提交，平时不需要跑）
#   $env:SOLC_BIN = "C:\path\to\solc.exe"
python scripts/build_erc20.py
```

> 重新编译后 `eth_qa/erc20_artifact.py` 的字节码应当**完全一致**（已验证），
> 这就是「产物可复现」的含义。

---

## 9. 设计取舍与已知限制

**为什么用内存 EVM 而不是测试网**：可复现、零成本、无需水龙头。代价是测不到真实网络延迟与
节点差异。

**为什么手写 ERC-20 而不是 import OpenZeppelin**：避免外部依赖让字节码不可复现；同时可以
精确控制被测边界（自定义错误、无限授权语义、零地址行为）。

**已知限制（不回避）**：

1. **没有 EVM 字节码覆盖率** —— 需要插桩，本项目未做。78.1% 是 API 面覆盖，不是代码覆盖。
2. **业务合约只到标准 ERC-20** —— 没有重入、滑点、闪电贷这类复杂 DeFi 逻辑。
3. **只测了 eth-tester 的两个后端**（py-evm 为主，mock 只验证降级契约）。
4. **D-01 的补丁尚未向上游提交** —— 目前只存在于 `docs/patches/`。
5. **不变量测试不覆盖「本该被拒绝的操作」** —— 例如「余额不足也能转」这个合约变异体，
   守恒律抓不到（因为不变量只在余额充足的合法转账里跑），只被负向用例抓住。

---

## 10. License

MIT。ERC-20 合约与所有测试代码为本仓库原创；`eth-tester` 与 `py-evm` 遵循其自身许可。
