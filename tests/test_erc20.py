"""ERC-20 业务合约回归套件。

这是「从测工具升级到测业务合约」的那一层：被测对象是一个真实编译出来的
ERC-20 实现（`contracts/SimpleERC20.sol`，solc 0.8.38 编译，产物已提交）。

覆盖四块：
  1. 元数据与初始分配
  2. transfer：记账 / 事件 / 自转账 / 零金额 / 余额不足
  3. approve + transferFrom：授权、递减、无限授权、越权
  4. 自定义错误的 selector 与参数解码

外加 3 条不变量：总供应量恒定、余额之和恒等于总供应量、allowance 不超过授权额。
"""

from __future__ import annotations

import pytest
from eth_tester.exceptions import TransactionFailed
from hypothesis import HealthCheck, given, settings, strategies as st

from eth_qa.contracts import decode_error, error_selector, revert_data
from eth_qa.erc20_artifact import (
    ERC20_DECIMALS,
    ERC20_ERRORS,
    ERC20_INITIAL_SUPPLY,
    ERC20_NAME,
    ERC20_SYMBOL,
)

ZERO_ADDRESS = "0x" + "00" * 20
MAX_UINT256 = 2**256 - 1
ONE_TOKEN = 10**ERC20_DECIMALS

PROPERTY_SETTINGS = settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)


def balance(token, account) -> int:
    return token.read("balanceOf", (account,))[0]


def allowance(token, owner, spender) -> int:
    return token.read("allowance", (owner, spender))[0]


def expect_revert(token, fn_name, args, error_entry, sender=None):
    """执行一次会 revert 的调用，返回解码后的自定义错误参数。"""
    with pytest.raises(TransactionFailed) as excinfo:
        token.read(fn_name, args, sender=sender)

    payload = revert_data(excinfo.value)
    assert payload[:4] == error_selector(error_entry), (
        f"revert 应该带 {error_entry['name']} 的选择器，实际是 {payload[:4].hex()}"
    )
    return decode_error(error_entry, payload)


class TestMetadataAndInitialAllocation:
    def test_metadata(self, erc20):
        assert erc20.read("name") == (ERC20_NAME,)
        assert erc20.read("symbol") == (ERC20_SYMBOL,)
        assert erc20.read("decimals") == (ERC20_DECIMALS,)

    def test_total_supply_is_fixed_at_deploy(self, erc20):
        assert erc20.read("totalSupply") == (ERC20_INITIAL_SUPPLY,)

    def test_deployer_holds_the_entire_supply(self, erc20, accounts):
        assert balance(erc20, accounts[0]) == ERC20_INITIAL_SUPPLY
        for acct in accounts[1:]:
            assert balance(erc20, acct) == 0


class TestTransfer:
    def test_transfer_moves_value(self, erc20, accounts):
        sender, receiver = accounts[0], accounts[1]
        before_sender = balance(erc20, sender)

        receipt = erc20.send("transfer", (receiver, 500 * ONE_TOKEN), sender=sender)

        assert receipt["status"] == 1
        assert balance(erc20, receiver) == 500 * ONE_TOKEN
        assert balance(erc20, sender) == before_sender - 500 * ONE_TOKEN

    def test_transfer_emits_transfer_event_with_decoded_args(self, erc20, accounts):
        sender, receiver = accounts[0], accounts[1]
        receipt = erc20.send("transfer", (receiver, 42), sender=sender)

        logs = erc20.decode_logs(receipt)
        assert len(logs) == 1
        assert logs[0].name == "Transfer"
        assert logs[0].args["from"].lower() == sender.lower()
        assert logs[0].args["to"].lower() == receiver.lower()
        assert logs[0].args["value"] == 42

    def test_transfer_returns_true(self, erc20, accounts):
        # 用 call 模拟，拿返回值但不落状态
        assert erc20.read("transfer", (accounts[1], 1)) == (True,)

    def test_self_transfer_keeps_balance_and_emits(self, erc20, accounts):
        sender = accounts[0]
        before = balance(erc20, sender)

        receipt = erc20.send("transfer", (sender, 1000), sender=sender)

        assert balance(erc20, sender) == before
        logs = erc20.decode_logs(receipt)
        assert len(logs) == 1
        assert logs[0].args["value"] == 1000

    def test_zero_value_transfer_is_allowed_and_emits(self, erc20, accounts):
        receipt = erc20.send("transfer", (accounts[1], 0), sender=accounts[0])

        assert receipt["status"] == 1
        assert balance(erc20, accounts[1]) == 0
        assert erc20.decode_logs(receipt)[0].args["value"] == 0

    def test_transfer_to_zero_address_is_allowed_by_the_contract(self, erc20, accounts):
        """ERC-20 标准不禁止转给零地址；这里锁住行为，避免有人「好心」加校验。"""
        receipt = erc20.send("transfer", (ZERO_ADDRESS, 7), sender=accounts[0])

        assert receipt["status"] == 1
        assert balance(erc20, ZERO_ADDRESS) == 7

    def test_transfer_more_than_balance_reverts_with_custom_error(self, erc20, accounts):
        (owner, available, required) = expect_revert(
            erc20,
            "transfer",
            (accounts[1], ERC20_INITIAL_SUPPLY + 1),
            ERC20_ERRORS["InsufficientBalance"],
        )

        assert owner.lower() == accounts[0].lower()
        assert available == ERC20_INITIAL_SUPPLY
        assert required == ERC20_INITIAL_SUPPLY + 1


class TestApproval:
    def test_approve_sets_allowance_and_emits(self, erc20, accounts):
        owner, spender = accounts[0], accounts[2]
        receipt = erc20.send("approve", (spender, 1000), sender=owner)

        assert allowance(erc20, owner, spender) == 1000
        logs = erc20.decode_logs(receipt)
        assert logs[0].name == "Approval"
        assert logs[0].args["owner"].lower() == owner.lower()
        assert logs[0].args["spender"].lower() == spender.lower()
        assert logs[0].args["value"] == 1000

    def test_approve_overwrites_previous_allowance(self, erc20, accounts):
        owner, spender = accounts[0], accounts[2]
        erc20.send("approve", (spender, 1000), sender=owner)
        erc20.send("approve", (spender, 10), sender=owner)

        assert allowance(erc20, owner, spender) == 10

    def test_transfer_from_consumes_allowance(self, erc20, accounts):
        owner, spender, receiver = accounts[0], accounts[2], accounts[3]
        erc20.send("approve", (spender, 1000), sender=owner)

        receipt = erc20.send("transferFrom", (owner, receiver, 400), sender=spender)

        assert receipt["status"] == 1
        assert balance(erc20, receiver) == 400
        assert allowance(erc20, owner, spender) == 600

    def test_transfer_from_beyond_allowance_reverts(self, erc20, accounts):
        owner, spender, receiver = accounts[0], accounts[2], accounts[3]
        erc20.send("approve", (spender, 100), sender=owner)

        (o, available, required) = expect_revert(
            erc20,
            "transferFrom",
            (owner, receiver, 101),
            ERC20_ERRORS["InsufficientAllowance"],
            sender=spender,
        )

        assert o.lower() == owner.lower()
        assert available == 100
        assert required == 101

    def test_transfer_from_without_approval_reverts(self, erc20, accounts):
        stranger = accounts[4]
        expect_revert(
            erc20,
            "transferFrom",
            (accounts[0], accounts[3], 1),
            ERC20_ERRORS["InsufficientAllowance"],
            sender=stranger,
        )

    def test_infinite_allowance_is_not_decremented(self, erc20, accounts):
        owner, spender, receiver = accounts[0], accounts[2], accounts[3]
        erc20.send("approve", (spender, MAX_UINT256), sender=owner)

        erc20.send("transferFrom", (owner, receiver, 1000), sender=spender)

        assert allowance(erc20, owner, spender) == MAX_UINT256


class TestInvariants:
    """业务层面的不变量：这三条在任何合法操作下都必须成立。"""

    def test_total_supply_never_changes(self, erc20, accounts):
        erc20.send("transfer", (accounts[1], 5 * ONE_TOKEN))
        erc20.send("approve", (accounts[2], 100))
        erc20.send("transferFrom", (accounts[0], accounts[3], 100), sender=accounts[2])

        assert erc20.read("totalSupply") == (ERC20_INITIAL_SUPPLY,)

    @PROPERTY_SETTINGS
    @given(
        amounts=st.lists(
            st.integers(min_value=0, max_value=10 * ONE_TOKEN), min_size=1, max_size=5
        ),
        to_index=st.integers(min_value=1, max_value=4),
    )
    def test_sum_of_balances_always_equals_total_supply(self, amounts, to_index):
        from eth_tester import EthereumTester

        from eth_qa.contracts import deploy_contract
        from eth_qa.erc20_artifact import (
            ERC20_ABI,
            ERC20_BYTECODE,
            ERC20_CONSTRUCTOR_TYPES,
        )

        chain = EthereumTester()
        accts = list(chain.get_accounts())
        token = deploy_contract(
            chain,
            ERC20_BYTECODE,
            ERC20_ABI,
            sender=accts[0],
            gas=4_000_000,
            constructor_args=(
                ERC20_NAME,
                ERC20_SYMBOL,
                ERC20_DECIMALS,
                ERC20_INITIAL_SUPPLY,
            ),
            constructor_types=ERC20_CONSTRUCTOR_TYPES,
        )

        for amount in amounts:
            token.send("transfer", (accts[to_index], amount), sender=accts[0])

        total = sum(balance(token, a) for a in accts)
        assert total == ERC20_INITIAL_SUPPLY

    @PROPERTY_SETTINGS
    @given(approved=st.integers(min_value=0, max_value=10 * ONE_TOKEN))
    def test_allowance_never_exceeds_what_was_approved(self, approved):
        from eth_tester import EthereumTester

        from eth_qa.contracts import deploy_contract
        from eth_qa.erc20_artifact import (
            ERC20_ABI,
            ERC20_BYTECODE,
            ERC20_CONSTRUCTOR_TYPES,
        )

        chain = EthereumTester()
        accts = list(chain.get_accounts())
        token = deploy_contract(
            chain,
            ERC20_BYTECODE,
            ERC20_ABI,
            sender=accts[0],
            gas=4_000_000,
            constructor_args=(
                ERC20_NAME,
                ERC20_SYMBOL,
                ERC20_DECIMALS,
                ERC20_INITIAL_SUPPLY,
            ),
            constructor_types=ERC20_CONSTRUCTOR_TYPES,
        )

        token.send("approve", (accts[1], approved), sender=accts[0])
        if approved > 0:
            token.send("transferFrom", (accts[0], accts[2], approved), sender=accts[1])

        assert allowance(token, accts[0], accts[1]) == 0
