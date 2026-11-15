"""变异测试补强用例。

这批用例不是「想到什么写什么」，而是**变异测试的报告转化来的**：
第一轮 15 个变异体里活下来 3 个，每一个都对应一条缺失的断言。

| 存活的变异体 | 暴露的用例空洞 | 本文件对应的补强用例 |
| --- | --- | --- |
| `balance_off_by_one` | 所有余额断言都是**相对值**（前后做差），没有一条锁定绝对值 | `test_genesis_balance_is_exactly_one_million_ether` |
| `receipt_type_legacy` | `type` 只在 `get_transaction_by_hash` 上断言过，**回执里的 type 从没被验证** | `test_receipt_type_is_present_on_the_receipt` |
| `fee_history_truncated` | 只断言「非空」，没断言**返回条数等于请求窗口** | `test_fee_history_returns_requested_window_size` |

外加一条顺带补的：`storage_slot_ignored` 虽然被杀掉了，但杀它的是「slot 必须是 hex」的
负向用例（顺带失败），并没有真正确认「不同 slot 返回不同值」。所以补一条真正的区分断言。
"""

from __future__ import annotations


class TestAbsoluteValues:
    """绝对断言：锁死具体数值，防止「整体偏移但相对不变」的缺陷漏网。"""

    def test_genesis_balance_is_exactly_one_million_ether(self, chain, accounts):
        expected = 10**6 * 10**18  # 1,000,000 ETH

        for acct in accounts:
            assert chain.get_balance(acct) == expected

    def test_gas_price_of_a_plain_transfer_is_positive(self, chain, accounts):
        tx_hash = chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )
        receipt = chain.get_transaction_receipt(tx_hash)

        assert receipt["effective_gas_price"] > 1, (
            "成交价必须 > 1 wei；否则说明扣费口径被改坏了"
        )


class TestReceiptContract:
    """回执是下游（浏览器 / 索引服务 / 会计）的输入，字段本身也要断言。"""

    def test_receipt_type_is_present_on_the_receipt(self, chain, accounts):
        tx_hash = chain.send_transaction(
            {
                "from": accounts[0],
                "to": accounts[1],
                "value": 1,
                "gas": 21000,
                "max_fee_per_gas": 10**9,
                "max_priority_fee_per_gas": 10**9,
            }
        )
        receipt = chain.get_transaction_receipt(tx_hash)

        assert receipt["type"] == "0x2", (
            "回执上的 type 也必须标 EIP-1559，不能只靠 get_transaction_by_hash 验证"
        )
        assert chain.get_transaction_by_hash(tx_hash)["type"] == "0x2"


class TestFeeHistoryWindow:
    """费率历史：条数必须等于请求窗口，而不只是「非空」。"""

    def test_fee_history_returns_requested_window_size(self, chain, accounts):
        chain.mine_blocks(3)
        history = chain.get_fee_history(3, "latest", [])

        assert len(history["base_fee_per_gas"]) == 3
        assert len(history["gas_used_ratio"]) == 3


class TestStorageSlotSemantics:
    """storage 读的是「指定 slot」，不是「永远是 slot 0」。"""

    def test_get_storage_at_distinguishes_slots(self, chain, math):
        math.send("increment")

        assert int(chain.get_storage_at(math.address, "0x0"), 16) == 1
        assert int(chain.get_storage_at(math.address, "0x1"), 16) == 0
        assert int(chain.get_storage_at(math.address, "0x2"), 16) == 0
