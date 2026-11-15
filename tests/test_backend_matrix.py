"""后端矩阵：同一套 API 在不同链配置下的行为必须被显式验证。

eth-tester 支持两个后端（py-evm / mock）和两种挖矿模式（自动 / 手动）。
主套件只覆盖了「py-evm + 自动挖矿」这一条最常用的路径，这里把另外三条补上。

**为什么值得写**：换后端或换挖矿模式之后，同样的代码可能静默改变行为
（比如交易没上链、回执拿不到、合约根本不会执行）。这类差异不写用例就发现不了，
而它们恰恰是 CI 里最容易被误判成「flaky」的东西。
"""

from __future__ import annotations

import pytest
from eth_tester.exceptions import TransactionNotFound

from eth_qa.plugin import RETURN_42_INIT_CODE


class TestAutoMineDisabled:
    """手动挖矿模式：发交易 ≠ 生效。"""

    def test_send_does_not_advance_block(self, chain_manual):
        accounts = list(chain_manual.get_accounts())
        before = chain_manual.get_block_by_number("latest")["number"]

        chain_manual.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )

        assert chain_manual.get_block_by_number("latest")["number"] == before

    def test_balance_unchanged_until_mined(self, chain_manual):
        accounts = list(chain_manual.get_accounts())
        before = chain_manual.get_balance(accounts[1])

        chain_manual.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 10**18, "gas": 21000}
        )

        assert chain_manual.get_balance(accounts[1]) == before

    def test_receipt_is_unavailable_before_mining(self, chain_manual):
        accounts = list(chain_manual.get_accounts())
        tx_hash = chain_manual.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )

        with pytest.raises(TransactionNotFound):
            chain_manual.get_transaction_receipt(tx_hash)

    def test_mine_blocks_applies_pending_and_advances(self, chain_manual):
        accounts = list(chain_manual.get_accounts())
        before_balance = chain_manual.get_balance(accounts[1])
        tx_hash = chain_manual.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 10**18, "gas": 21000}
        )

        chain_manual.mine_blocks(3)

        assert chain_manual.get_block_by_number("latest")["number"] == 3
        assert chain_manual.get_balance(accounts[1]) - before_balance == 10**18
        assert chain_manual.get_transaction_receipt(tx_hash)["status"] == 1


class TestMockBackend:
    """Mock 后端：支持门面层 API，但不执行 EVM。

    这些断言的作用是**把降级行为写死**——以后谁想在这个后端上跑合约测试，
    会立刻看到「这里根本不支持」，而不是拿到一堆莫名其妙的 status=0。
    """

    def test_accounts_and_balances_are_available(self, mock_chain):
        accounts = list(mock_chain.get_accounts())
        assert len(accounts) == 10
        assert mock_chain.get_balance(accounts[0]) > 0

    def test_call_is_not_implemented(self, mock_chain):
        accounts = list(mock_chain.get_accounts())
        with pytest.raises(NotImplementedError):
            mock_chain.call({"from": accounts[0], "to": accounts[1], "data": "0x"})

    def test_contract_deployment_yields_no_address(self, mock_chain):
        accounts = list(mock_chain.get_accounts())
        tx_hash = mock_chain.send_transaction(
            {"from": accounts[0], "data": RETURN_42_INIT_CODE, "gas": 200_000}
        )
        receipt = mock_chain.get_transaction_receipt(tx_hash)

        assert receipt["contract_address"] is None
        assert receipt["status"] == 0, "没有 EVM 执行，交易不可能成功"

    def test_get_code_returns_empty(self, mock_chain):
        accounts = list(mock_chain.get_accounts())
        assert mock_chain.get_code(accounts[0]) in ("0x", "0x0", "")
