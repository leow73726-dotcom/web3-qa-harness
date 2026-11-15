"""故意保留「按 eth-tester 文档写法」的错误用例，用来证明质量门禁会稳定判红。

D-01：项目自己 `exceptions` 模块导出了 `ValidationError`，但 py-evm 后端在余额不足时
抛的是 `eth_utils.exceptions.ValidationError`，两者不是同一个类、没有继承关系。
所以按文档写的 `pytest.raises(ValidationError)` 永远接不住，用例稳定失败。

质量门禁对它的判定应当是 `stable-fail`（而不是 flaky），并带上失败证据。
详见 docs/D-01-defect.md 。
"""

import pytest
from eth_tester.exceptions import ValidationError  # 文档里就是这个路径


def test_doc_style_validation_error_is_caught(chain, accounts):
    balance = chain.get_balance(accounts[0])
    with pytest.raises(ValidationError):
        chain.send_transaction(
            {
                "from": accounts[0],
                "to": accounts[1],
                "value": balance * 2,
                "gas": 21000,
            }
        )
