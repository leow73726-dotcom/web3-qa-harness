"""合约行为回归套件。

覆盖 eth-tester 自带的四个预编译合约（源码以注释形式贴在 bytecode 旁边，
不需要 solc）：
  * throws      —— 失败路径：revert / require(false)
  * math        —— 状态机与算术
  * emitter     —— 事件日志（含 indexed 参数）
  * gas_burner  —— 区块号依赖的 gas 消耗

设计原则：只断言「对外可观察的行为」，不断言内部实现细节。
"""

from __future__ import annotations

import pytest
from eth_tester.utils.emitter_contract import EMITTER_ENUM


class TestThrowsContract:
    """失败路径。

    eth-tester 的关键约定：合约 revert 不抛异常，而是返回 status=0 的回执。
    这条行为必须锁住 —— 它和「直连节点 + web3.py」的体验不同，很容易写错断言。
    """

    def test_initial_value_is_one(self, throws):
        contract = throws("throw_contract")
        assert contract.read("value") == (1,)

    def test_set_value_persists(self, throws):
        contract = throws("throw_contract")
        receipt = contract.send("setValue", (7,))
        assert receipt["status"] == 1
        assert contract.read("value") == (7,)

    def test_will_throw_yields_failed_receipt_instead_of_exception(self, throws):
        contract = throws("throw_contract")
        receipt = contract.send("willThrow")
        assert receipt["status"] == 0
        assert receipt["logs"] == []

    def test_failed_call_does_not_change_stored_state(self, throws):
        contract = throws("throw_contract")
        contract.send("setValue", (7,))
        contract.send("willThrow")
        assert contract.read("value") == (7,), "失败的交易必须把状态回滚干净"

    def test_revert_contract_covers_both_branches(self, throws):
        contract = throws("revert_contract")
        assert contract.send("do_revert", (True,))["status"] == 0
        assert contract.send("do_revert", (False,))["status"] == 1


class TestMathContract:
    """状态机与算术：验证 ABI 编码的入参能正确落到合约里。"""

    def test_counter_starts_at_zero(self, math):
        assert math.read("counter") == (0,)

    def test_increment_is_monotonic(self, math):
        math.send("increment")
        assert math.read("counter") == (1,)
        math.send("increment")
        assert math.read("counter") == (2,)

    def test_return13_is_stable_across_calls(self, math):
        assert math.read("return13") == (13,)
        assert math.read("return13") == (13,), "只读调用不能有副作用"

    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [(3, 4, 7), (0, 0, 0), (10**18, 1, 10**18 + 1)],
    )
    def test_add_returns_sum(self, math, a, b, expected):
        assert math.read("add", (a, b)) == (expected,)

    def test_multiply7(self, math):
        assert math.read("multiply7", (6,)) == (42,)


class TestEmitterContract:
    """事件日志：dApp 的前端更新全靠事件，事件发错就等于「操作了但没人知道」。"""

    def test_no_argument_event(self, emitter):
        receipt = emitter.send("logNoArgs", (EMITTER_ENUM["LogNoArguments"],))
        logs = emitter.decode_logs(receipt)
        assert len(logs) == 1
        assert logs[0].name == "LogNoArguments"
        assert logs[0].args == {}

    def test_single_arg_event_payload(self, emitter):
        receipt = emitter.send("logSingle", (EMITTER_ENUM["LogSingleArg"], 77))
        logs = emitter.decode_logs(receipt)
        assert logs[0].name == "LogSingleArg"
        assert logs[0].args == {"arg0": 77}

    def test_double_arg_event_payload(self, emitter):
        receipt = emitter.send(
            "logDouble", (EMITTER_ENUM["LogDoubleArg"], 11, 22)
        )
        logs = emitter.decode_logs(receipt)
        assert logs[0].name == "LogDoubleArg"
        assert logs[0].args == {"arg0": 11, "arg1": 22}

    def test_indexed_argument_lands_in_topics(self, emitter):
        receipt = emitter.send(
            "logSingle", (EMITTER_ENUM["LogSingleWithIndex"], 5)
        )
        raw_logs = receipt["logs"]
        assert len(raw_logs[0]["topics"]) == 2, "indexed 参数应进 topics 而非 data"

        logs = emitter.decode_logs(receipt)
        assert logs[0].name == "LogSingleWithIndex"
        assert logs[0].args == {"arg0": 5}

    def test_successful_call_without_events_has_no_logs(self, throws):
        contract = throws("throw_contract")
        receipt = contract.send("setValue", (3,))
        assert receipt["logs"] == []


class TestGasBurnerContract:
    """gas 与区块号的关系：用来验证 estimator 和真实消耗是否同向变化。"""

    def test_gas_used_grows_with_block_number(self, chain, gas_burner):
        first = gas_burner.send("burnBlockNumberDependentGas")["gas_used"]
        chain.mine_blocks(30)
        second = gas_burner.send("burnBlockNumberDependentGas")["gas_used"]
        assert second > first, "合约按 block.number 循环，gas 必须随之增长"

    def test_gas_estimate_tracks_block_number(self, chain, accounts, gas_burner):
        data = gas_burner.encode("burnBlockNumberDependentGas")
        tx = {"from": accounts[0], "to": gas_burner.address, "data": data}

        before = chain.estimate_gas(dict(tx))
        chain.mine_blocks(30)
        after = chain.estimate_gas(dict(tx))

        assert after > before, "估算值也要随区块号增长，否则就是 estimator 的 bug"
