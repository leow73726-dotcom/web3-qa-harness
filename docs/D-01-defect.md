# D-01：公开的 `ValidationError` 与后端实际抛出的异常类型不一致

| 字段 | 内容 |
| --- | --- |
| 被测项目 | [`ApeWorX/eth-tester`](https://github.com/ApeWorX/eth-tester) v0.14.0b1（MIT） |
| 环境 | eth-tester 0.14.0b1 + py-evm 0.12.1b1 + Python 3.12.10 |
| 严重级别 | Medium（可用性 / API 契约） |
| 状态 | 已复现、已定位根因、已产出可应用补丁；**尚未向上游提交** |
| 修复补丁 | [`patches/D-01.patch`](patches/D-01.patch) |

## 1. 复现

```python
from eth_tester import EthereumTester
from eth_tester.exceptions import ValidationError   # 文档里就是这个路径

t = EthereumTester()
accts = list(t.get_accounts())
try:
    t.send_transaction({"from": accts[0], "to": accts[1],
                        "value": t.get_balance(accts[0]) * 2, "gas": 21000})
except ValidationError:
    print("caught")     # ← 永远不会执行
```

可执行版本见 [`../demo_defect/test_doc_style.py`](../demo_defect/test_doc_style.py)。

## 2. 预期 vs 实际

| | |
| --- | --- |
| **预期** | 抛出 `eth_tester.exceptions.ValidationError`，按文档写的 `pytest.raises` / `except` 能捕获 |
| **实际** | 抛出 `eth_utils.exceptions.ValidationError`，与前者**无任何继承关系** |

```
eth_tester.ValidationError MRO: ['eth_tester.exceptions.ValidationError', 'builtins.Exception', ...]
eth_utils.ValidationError  MRO: ['eth_utils.exceptions.ValidationError',  'builtins.Exception', ...]
same class?                    False
issubclass(te, ue)?            False
issubclass(ue, te)?            False
catchable by eth_tester type?  NO
```

## 3. 影响

凡是以 `eth_tester.exceptions.ValidationError` 做断言或捕获目标的调用方，全部失效。两种失败形态：

1. `pytest.raises(ValidationError)` 不触发 → 用例红，报 `DID NOT RAISE`，容易误判成「被测逻辑没校验」；
2. `try/except ValidationError` 接不住 → 异常穿透，可能被外层宽泛的 `except Exception` 吞掉 → **假绿**：
   测试显示通过，但那条断言根本没执行。

第 2 种更危险：它把「没测到」伪装成「测过了」。

## 4. 根因

- `eth_tester/exceptions.py` 自行定义了 `class ValidationError(Exception)`；
- eth-tester 自己的 `validation/*.py` 从中导入并使用；
- 但**余额校验发生在 py-evm 后端**（`eth/vm/forks/frontier/validation.py`），抛的是
  `eth_utils.exceptions.ValidationError`；
- `eth_tester/main.py` 的 `send_transaction` → `_add_transaction_to_pending_block` 在调用
  `backend.send_transaction(...)` 时**没有做异常归一化**，后端异常原样穿透。

## 5. 修复

```python
# eth_tester/exceptions.py 第 1 行
from eth_utils.exceptions import ValidationError  # noqa: F401  (re-exported public name)
```

删掉本地类定义，让两个名字指向**同一个类**。一行改动，零新增依赖（`eth_utils` 本就是必需依赖）。

### 被实测否定的第一版方案

我最初写的是「让公开异常**继承**后端异常」：

```python
class ValidationError(_EthUtilsValidationError):   # ← 无效
    pass
```

跑完反例套件**依然 3/3 判红**。原因：

> `pytest.raises(X)` 捕获的是 `X` 的实例。把 `eth_tester.ValidationError` 变成
> `eth_utils.ValidationError` 的**子类**，并不会让父类实例变成子类实例——**继承方向反了**。

必须让两个名字指向同一个类（re-export），或在抛出侧做转换。

## 6. 验证

| 状态 | `demo_defect` 反例套件 | 主套件 84 条 | 回归锁用例 |
| --- | --- | --- | --- |
| 修复前 | 3/3 轮 `stable-fail`，exit 1 | 84 passed | passed（断言两类不同） |
| 修复后 | 3/3 轮 `stable-pass`，exit 0 | 83 passed + **1 failed** | **failed**（断言失效） |

回归锁用例是**故意**断言「两个类不同」的：它的职责是在上游修复时转红，提醒维护者关闭缺陷单。
修复后它果然红了，说明这套机制闭合。

```bash
git apply docs/patches/D-01.patch
python -m pytest                        # 期望 83 passed, 1 failed（回归锁）
python -m eth_qa.quality --tests demo_defect --runs 3   # 期望 exit 0
```
