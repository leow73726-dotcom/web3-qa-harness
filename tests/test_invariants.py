"""不变量测试（property-based）。

和「给定输入 → 断言输出」的用例不同，这里断言的是**无论发生什么都必须成立的规则**：

  INV-1  余额守恒：任意交易之后，全链余额总和必须正好减少「这笔交易烧掉的 gas」
  INV-2  失败执行仍烧 gas：revert 的交易不转移价值，但 gas 必须照扣
  INV-3  校验失败零副作用：余额不足在入参校验阶段就被拒，链上状态与 nonce 都不动
  INV-4  自转账只花 gas：from == to 时金额绕一圈回来，净变化只能是 -gas
  INV-5  nonce 单调递增：同一账户的 nonce 只增不减，且每成功交易 +1
  INV-6  只读调用无副作用：call 不产块、不动余额、不改 nonce
  INV-7  快照回滚幂等：回滚到同一快照 N 次，状态始终等于快照时刻

用 Hypothesis 生成随机交易序列：它会在失败时**自动收缩（shrink）**出最小反例——
如果守恒律在某个随机序列上破了，它会告诉你「最少 2 笔交易就能复现」，
而不是甩给你一段 8 笔交易的噪声。

这比「再写 20 条用例」更能说明问题：用例只能覆盖你想得到的场景，
不变量覆盖你想不到的组合。
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from eth_tester import EthereumTester
from eth_tester.exceptions import (
    TransactionFailed,
    ValidationError as EthTesterValidationError,
)
from eth_utils.exceptions import ValidationError as EthUtilsValidationError

# D-01：两层校验抛的是两个不同类，同时收。
ANY_VALIDATION_ERROR = (EthTesterValidationError, EthUtilsValidationError)

ACCOUNT_COUNT = 10
ONE_ETHER = 10**18

# 现场属性测试的通用设置：不设 deadline（EVM 建链耗时波动大），
# 关掉「函数级 fixture 太慢」的告警。
PROPERTY_SETTINGS = settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

# 一笔转账操作 = (from 下标, to 下标, 金额)
Transfer = tuple[int, int, int]
transfer_ops = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=ACCOUNT_COUNT - 1),
        st.integers(min_value=0, max_value=ACCOUNT_COUNT - 1),
        st.integers(min_value=0, max_value=5 * ONE_ETHER),
    ),
    min_size=1,
    max_size=6,
)


def total_balance(chain: EthereumTester) -> int:
    return sum(chain.get_balance(acct) for acct in chain.get_accounts())


def gas_spent(receipt: dict) -> int:
    return receipt["gas_used"] * receipt["effective_gas_price"]


def execute(chain: EthereumTester, accounts: list[str], ops: list[Transfer]) -> list[dict]:
    """执行一串转账，跳过余额不足的，返回成功落链的回执。"""
    receipts = []
    for from_idx, to_idx, value in ops:
        sender, receiver = accounts[from_idx], accounts[to_idx]
        if value > chain.get_balance(sender):
            continue
        tx_hash = chain.send_transaction(
            {"from": sender, "to": receiver, "value": value, "gas": 21000}
        )
        receipts.append(chain.get_transaction_receipt(tx_hash))
    return receipts


class TestConservationLaw:
    """INV-1 / INV-4：余额守恒。"""

    @PROPERTY_SETTINGS
    @given(ops=transfer_ops)
    def test_total_balance_only_drops_by_gas(self, ops):
        chain = EthereumTester()
        accounts = list(chain.get_accounts())
        expected_total = total_balance(chain)

        receipts = execute(chain, accounts, ops)
        for receipt in receipts:
            expected_total -= gas_spent(receipt)

        assert total_balance(chain) == expected_total, (
            "任意交易序列之后，全链余额总和必须正好等于初始总量减去累计 gas"
        )

    @PROPERTY_SETTINGS
    @given(
        value=st.integers(min_value=0, max_value=ONE_ETHER),
        sender_idx=st.integers(min_value=0, max_value=ACCOUNT_COUNT - 1),
    )
    def test_self_transfer_costs_only_gas(self, value, sender_idx):
        chain = EthereumTester()
        accounts = list(chain.get_accounts())
        sender = accounts[sender_idx]
        before = chain.get_balance(sender)

        tx_hash = chain.send_transaction(
            {"from": sender, "to": sender, "value": value, "gas": 21000}
        )
        receipt = chain.get_transaction_receipt(tx_hash)

        assert chain.get_balance(sender) == before - gas_spent(receipt)


class TestFailureAccounting:
    """INV-2 / INV-3：失败路径的记账。"""

    def test_revert_burns_gas_but_transfers_nothing(self, chain, accounts, throws):
        contract = throws("throw_contract")
        sender = accounts[0]
        before_sender = chain.get_balance(sender)
        before_total = total_balance(chain)

        receipt = contract.send("willThrow")

        assert receipt["status"] == 0
        assert chain.get_balance(sender) == before_sender - gas_spent(receipt)
        assert total_balance(chain) == before_total - gas_spent(receipt)

    @PROPERTY_SETTINGS
    @given(multiplier=st.integers(min_value=2, max_value=10))
    def test_validation_failure_has_zero_side_effects(self, multiplier):
        chain = EthereumTester()
        accounts = list(chain.get_accounts())
        sender, receiver = accounts[0], accounts[1]
        before_total = total_balance(chain)
        before_nonce = chain.get_nonce(sender)
        before_balance = chain.get_balance(sender)

        with pytest.raises(ANY_VALIDATION_ERROR):
            chain.send_transaction(
                {
                    "from": sender,
                    "to": receiver,
                    "value": before_balance * multiplier,
                    "gas": 21000,
                }
            )

        assert total_balance(chain) == before_total
        assert chain.get_balance(sender) == before_balance
        assert chain.get_nonce(sender) == before_nonce


class TestNonceAndReadOnly:
    """INV-5 / INV-6：nonce 单调、只读无副作用。"""

    @PROPERTY_SETTINGS
    @given(ops=transfer_ops)
    def test_nonce_is_monotonic(self, ops):
        chain = EthereumTester()
        accounts = list(chain.get_accounts())
        counts: dict[str, int] = {acct: 0 for acct in accounts}

        for from_idx, to_idx, value in ops:
            sender, receiver = accounts[from_idx], accounts[to_idx]
            if value > chain.get_balance(sender):
                continue
            chain.send_transaction(
                {"from": sender, "to": receiver, "value": value, "gas": 21000}
            )
            counts[sender] += 1

        for acct, expected in counts.items():
            assert chain.get_nonce(acct) == expected

    def test_call_has_no_side_effects(self, chain, accounts, math):
        before_total = total_balance(chain)
        before_block = chain.get_block_by_number("latest")["number"]
        before_nonce = chain.get_nonce(accounts[0])

        for _ in range(3):
            assert math.read("counter") == (0,)

        assert total_balance(chain) == before_total
        assert chain.get_block_by_number("latest")["number"] == before_block
        assert chain.get_nonce(accounts[0]) == before_nonce


class TestSnapshotIdempotence:
    """INV-7：快照回滚幂等。"""

    @PROPERTY_SETTINGS
    @given(repeats=st.integers(min_value=2, max_value=4))
    def test_revert_is_idempotent(self, repeats):
        chain = EthereumTester()
        accounts = list(chain.get_accounts())
        baseline_total = total_balance(chain)
        snapshot_id = chain.take_snapshot()

        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 3 * ONE_ETHER, "gas": 21000}
        )
        assert total_balance(chain) < baseline_total

        for _ in range(repeats):
            chain.revert_to_snapshot(snapshot_id)

        assert total_balance(chain) == baseline_total
