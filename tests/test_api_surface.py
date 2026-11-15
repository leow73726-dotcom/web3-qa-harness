"""公开 API 面覆盖：把主套件没碰过的查询 / 生命周期 / 过滤器接口补上。

目的不是「提高覆盖率数字」，而是**每一条都验证一个对外承诺**：
非ce 怎么变、storage 怎么读、日志怎么按地址查、时间戳怎么推进、
整条链怎么重置、过滤器怎么跟踪新块、自动挖矿怎么开关。

刻意不覆盖的 7 个方法（见 reports/API_COVERAGE.md）：
`add_account` / `send_raw_transaction`（需要外部私钥与签名流程）、
`lock_account` / `unlock_account`（预制账户没有密码状态，无法构造前置条件）、
`create_log_filter` / `create_pending_transaction_filter` / `get_all_filter_logs`
（过滤器家族的另一半，与已覆盖的块过滤器同构，边际信息量低）。
"""

from __future__ import annotations

import pytest
from eth_tester.exceptions import (
    FilterNotFound,
    ValidationError as EthTesterValidationError,
)
from eth_utils.exceptions import ValidationError as EthUtilsValidationError

# D-01：eth-tester 自己的校验用 eth_tester 的类，后端校验用 eth_utils 的类，
# 两者无继承关系，所以同时收。
ANY_VALIDATION_ERROR = (EthTesterValidationError, EthUtilsValidationError)


class TestQueryApi:
    """查询类接口：nonce / storage / logs / fee history / 时间。"""

    def test_get_nonce_increments_after_transaction(self, chain, accounts):
        assert chain.get_nonce(accounts[0]) == 0
        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )
        assert chain.get_nonce(accounts[0]) == 1

    def test_get_storage_at_reads_counter_slot(self, chain, math):
        math.send("increment")
        raw = chain.get_storage_at(math.address, "0x0")
        assert int(raw, 16) == 1

    def test_get_storage_at_requires_hex_slot(self, chain, math):
        """slot 必须是十六进制字符串，传 int 会被校验拦住 —— 这是个常见踩坑点。"""
        with pytest.raises(ANY_VALIDATION_ERROR, match="hex string"):
            chain.get_storage_at(math.address, 0)

    def test_get_logs_filters_by_address(self, emitter):
        from eth_tester.utils.emitter_contract import EMITTER_ENUM

        emitter.send("logDouble", (EMITTER_ENUM["LogDoubleArg"], 11, 22))
        logs = emitter.chain.get_logs(address=emitter.address)

        assert len(logs) == 1
        assert logs[0]["address"].lower() == emitter.address.lower()

    def test_get_fee_history_returns_series(self, chain, accounts):
        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )
        history = chain.get_fee_history(3, "latest", [])

        assert {"oldest_block", "base_fee_per_gas", "gas_used_ratio"} <= set(history)
        assert len(history["base_fee_per_gas"]) >= 1

    def test_time_travel_shifts_block_timestamp(self, chain):
        before = chain.get_block_by_number("latest")["timestamp"]
        chain.time_travel(before + 3600)
        chain.mine_block()

        after = chain.get_block_by_number("latest")["timestamp"]
        assert after >= before + 3600


class TestChainLifecycle:
    """生命周期：整链重置、自动挖矿开关。"""

    def test_reset_to_genesis_clears_state(self, chain, accounts):
        genesis_balance = chain.get_balance(accounts[1])
        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 10**18, "gas": 21000}
        )
        assert chain.get_balance(accounts[1]) == genesis_balance + 10**18

        chain.reset_to_genesis()

        assert chain.get_balance(accounts[1]) == genesis_balance
        assert chain.get_block_by_number("latest")["number"] == 0

    def test_disable_then_enable_auto_mine(self, chain, accounts):
        chain.disable_auto_mine_transactions()
        before = chain.get_block_by_number("latest")["number"]
        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )
        assert chain.get_block_by_number("latest")["number"] == before

        chain.enable_auto_mine_transactions()
        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )
        assert chain.get_block_by_number("latest")["number"] > before


class TestFilters:
    """过滤器：只返回「自上次查询以来的增量」，是轮询式监听的底层机制。"""

    def test_block_filter_tracks_new_blocks(self, chain, accounts):
        filter_id = chain.create_block_filter()
        assert chain.get_only_filter_changes(filter_id) == ()

        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )
        changes = chain.get_only_filter_changes(filter_id)

        assert len(changes) == 1

    def test_delete_filter_makes_it_unusable(self, chain):
        filter_id = chain.create_block_filter()
        chain.delete_filter(filter_id)

        with pytest.raises(FilterNotFound):
            chain.get_only_filter_changes(filter_id)
