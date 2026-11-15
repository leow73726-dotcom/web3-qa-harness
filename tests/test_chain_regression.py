"""Web3 链上回归套件：ETH 转账 + 合约部署/调用 + 状态隔离 + 负向用例。

每条用例只通过 eth_qa.plugin 提供的 fixture 访问链，不直接 new EthernetTester，
以此验证 fixture 层本身可用（这也是本轮改造的核心交付）。
"""

from __future__ import annotations

import pytest
from eth_tester.exceptions import ValidationError as EthTesterValidationError
from eth_utils.exceptions import ValidationError as EthUtilsValidationError

from eth_qa.plugin import RETURN_42_INIT_CODE

ZERO_ADDRESS = "0x" + "00" * 20


class TestAccounts:
    """账户与余额基线。"""

    def test_chain_exposes_ten_prefunded_accounts(self, accounts):
        assert len(accounts) == 10
        assert len(set(accounts)) == 10, "duplicate account addresses"

    def test_every_account_starts_with_the_same_balance(self, chain, accounts):
        balances = {chain.get_balance(acct) for acct in accounts}
        assert len(balances) == 1
        assert balances.pop() > 0

    def test_accounts_are_valid_hex_addresses(self, accounts):
        for acct in accounts:
            assert acct.startswith("0x")
            assert len(acct) == 42
            int(acct, 16)  # raises if not hex


class TestNativeTransfer:
    """原生 ETH 转账：正向、记账、边界。"""

    def test_native_transfer_updates_receiver_balance(self, chain, accounts):
        before = chain.get_balance(accounts[1])
        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 10**18, "gas": 21000}
        )
        assert chain.get_balance(accounts[1]) - before == 10**18

    def test_sender_is_charged_value_plus_gas(self, chain, accounts):
        value = 10**18
        before_sender = chain.get_balance(accounts[0])
        tx_hash = chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": value, "gas": 21000}
        )
        receipt = chain.get_transaction_receipt(tx_hash)
        charged = before_sender - chain.get_balance(accounts[0])
        expected = value + receipt["gas_used"] * receipt["effective_gas_price"]
        assert charged == expected, f"charged={charged} expected={expected}"

    def test_transfer_larger_than_balance_is_rejected(self, chain, accounts):
        balance = chain.get_balance(accounts[0])
        # D-01: 余额校验由 py-evm 后端抛出 eth_utils.exceptions.ValidationError，
        # 不是 eth-tester 自己 exceptions 模块里的那个类，所以这里必须两个都收。
        with pytest.raises(
            (EthTesterValidationError, EthUtilsValidationError), match="enough balance"
        ):
            chain.send_transaction(
                {
                    "from": accounts[0],
                    "to": accounts[1],
                    "value": balance * 2,
                    "gas": 21000,
                }
            )

    def test_backend_validation_error_type_differs_from_public_exception(self, chain, accounts):
        """D-01 回归锁：确认异常类型不一致仍然存在。

        上游一旦把后端异常归一化，这条会失败，提示我们更新缺陷单和上面的用例。
        """
        assert EthTesterValidationError is not EthUtilsValidationError

        balance = chain.get_balance(accounts[0])
        with pytest.raises(EthUtilsValidationError):
            chain.send_transaction(
                {
                    "from": accounts[0],
                    "to": accounts[1],
                    "value": balance * 2,
                    "gas": 21000,
                }
            )

        # 关键断言：用项目自身公开的异常类抓不到。
        try:
            chain.send_transaction(
                {
                    "from": accounts[0],
                    "to": accounts[1],
                    "value": balance * 2,
                    "gas": 21000,
                }
            )
        except EthTesterValidationError:
            pytest.fail("backend error is now normalized; update D-01")
        except Exception:  # noqa: BLE001 - 就是要证明抓不到
            pass

    def test_transfer_to_zero_address_is_allowed_by_the_evm(self, chain, accounts):
        """EVM 本身不禁止转给零地址；这条锁住行为，防止后端偷偷加校验。"""
        tx_hash = chain.send_transaction(
            {"from": accounts[0], "to": ZERO_ADDRESS, "value": 1, "gas": 21000}
        )
        assert chain.get_transaction_receipt(tx_hash)["status"] == 1


class TestContract:
    """合约部署与只读调用。"""

    def test_minimal_contract_returns_42(self, chain, accounts, deploy, call):
        address = deploy(RETURN_42_INIT_CODE)
        raw = call(address)
        assert int(raw, 16) == 42

    def test_deployed_code_is_stored_on_chain(self, chain, deploy):
        address = deploy(RETURN_42_INIT_CODE)
        code = chain.get_code(address)
        assert code not in ("0x", "0x0", ""), "no bytecode at the deployed address"

    def test_contract_call_does_not_mine_a_block(self, chain, deploy, call):
        address = deploy(RETURN_42_INIT_CODE)
        block_before = chain.get_block_by_number("latest")["number"]
        call(address)
        assert chain.get_block_by_number("latest")["number"] == block_before


class TestTransactionReceipt:
    """交易回执契约：字段、状态、EIP-1559 类型。"""

    REQUIRED_FIELDS = {
        "block_number",
        "from",
        "to",
        "gas_used",
        "status",
        "transaction_hash",
        "logs",
    }

    def test_receipt_has_required_fields(self, chain, accounts):
        tx_hash = chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 1, "gas": 21000}
        )
        receipt = chain.get_transaction_receipt(tx_hash)
        assert self.REQUIRED_FIELDS <= set(receipt)
        assert receipt["status"] == 1

    def test_eip1559_transaction_is_typed_0x2(self, chain, accounts):
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
        assert chain.get_transaction_by_hash(tx_hash)["type"] == "0x2"

    def test_gas_estimate_for_plain_transfer_is_21000(self, chain, accounts):
        assert chain.estimate_gas({"from": accounts[0], "to": accounts[1], "value": 1}) == 21000


class TestSnapshotIsolation:
    """状态快照与回滚 —— 用例之间必须互不污染。"""

    def test_snapshot_revert_restores_balance(self, chain, accounts, snapshot):
        baseline = chain.get_balance(accounts[1])
        chain.send_transaction(
            {"from": accounts[0], "to": accounts[1], "value": 10**18, "gas": 21000}
        )
        assert chain.get_balance(accounts[1]) > baseline

        chain.revert_to_snapshot(snapshot)
        assert chain.get_balance(accounts[1]) == baseline

    def test_revert_also_rolls_back_contract_deployment(self, chain, deploy, snapshot):
        before = chain.get_block_by_number("latest")["number"]
        address = deploy(RETURN_42_INIT_CODE)
        chain.revert_to_snapshot(snapshot)
        assert chain.get_block_by_number("latest")["number"] == before
        assert chain.get_code(address) in ("0x", "0x0", "")
