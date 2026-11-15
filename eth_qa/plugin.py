"""pytest fixtures around eth-tester.

eth-tester ships a great in-memory EVM backend but no pytest integration:
every test file ends up re-creating the tester, wiring accounts and deploying
bytecode by hand. This module turns that boilerplate into three fixtures:

    chain     -> a fresh EthereumTester per test (full isolation)
    accounts  -> the 10 prefunded accounts
    deploy    -> factory that deploys raw init bytecode and returns the address

It is intentionally dependency-free beyond eth-tester so it stays a drop-in
`pytest_plugins = ["eth_qa.plugin"]` include.
"""

from __future__ import annotations

import os
from typing import Any, Callable

import pytest
from eth_tester import EthereumTester
from eth_tester.backends.mock import MockBackend

from eth_tester.tools.gas_burner_contract import (
    GAS_BURNER_ABI,
    GAS_BURNER_BYTECODE,
)
from eth_tester.utils.emitter_contract import EMITTER_ABI, EMITTER_BYTECODE
from eth_tester.utils.math_contract import MATH_ABI, MATH_BYTECODE
from eth_tester.utils.throws_contract import THROWS_ABI, THROWS_BYTECODE

from .contracts import ContractHandle, deploy_contract, error_selector
from .erc20_artifact import (
    ERC20_ABI,
    ERC20_BYTECODE,
    ERC20_CONSTRUCTOR_TYPES,
    ERC20_DECIMALS,
    ERC20_INITIAL_SUPPLY,
    ERC20_MUTANT_BYTECODES,
    ERC20_NAME,
    ERC20_SYMBOL,
)

# A 10-byte runtime program that always returns uint256(42):
#   PUSH1 0x2a PUSH1 0x00 MSTORE PUSH1 0x20 PUSH1 0x00 RETURN
# prefixed with a 12-byte init program that returns the runtime above.
RETURN_42_INIT_CODE = "0x600a600c600039600a6000f3602a60005260206000f3"

DEFAULT_GAS = 500_000


@pytest.fixture
def chain() -> EthereumTester:
    """A fresh in-memory chain per test.

    Function scope is deliberate: a shared chain leaks state across tests and
    turns order-dependent failures into heisenbugs.
    """
    return EthereumTester()


@pytest.fixture
def accounts(chain: EthereumTester) -> list[str]:
    """The prefunded accounts, as plain strings so tests never mutate the tuple."""
    return list(chain.get_accounts())


@pytest.fixture
def deploy(chain: EthereumTester, accounts: list[str]) -> Callable[..., str]:
    """Deploy raw init bytecode and return the resulting contract address.

    Usage::

        addr = deploy(RETURN_42_INIT_CODE)
        addr = deploy(some_init_code, sender=accounts[1], gas=1_000_000)
    """

    def _deploy(
        init_code: str,
        *,
        sender: str | None = None,
        gas: int = DEFAULT_GAS,
        value: int = 0,
    ) -> str:
        tx_hash = chain.send_transaction(
            {
                "from": sender or accounts[0],
                "data": init_code,
                "gas": gas,
                "value": value,
            }
        )
        receipt = chain.get_transaction_receipt(tx_hash)
        contract_address = receipt["contract_address"]
        assert contract_address, "deployment produced no contract address"
        return contract_address

    return _deploy


@pytest.fixture
def call(chain: EthereumTester, accounts: list[str]) -> Callable[..., Any]:
    """Read-only contract call (does not mine a block, does not change state)."""

    def _call(to: str, data: str = "0x", *, sender: str | None = None) -> Any:
        return chain.call({"from": sender or accounts[0], "to": to, "data": data})

    return _call


@pytest.fixture
def snapshot(chain: EthereumTester):
    """Give a test a snapshot id and always revert to it afterwards.

    Yields the snapshot id so a test can also revert mid-test and keep going.
    """
    if not hasattr(chain, "take_snapshot"):
        pytest.skip("backend does not support snapshots")

    snapshot_id = chain.take_snapshot()
    yield snapshot_id
    chain.revert_to_snapshot(snapshot_id)


# ---------------------------------------------------------------------------
# 合约层：eth-tester 自带四个预编译合约（源码以注释形式贴在 bytecode 旁边，
# 所以不需要 solc）。这里把它们包成可直接调用的 fixture。
# ---------------------------------------------------------------------------


@pytest.fixture
def contract(chain: EthereumTester, accounts: list[str]) -> Callable[..., ContractHandle]:
    """通用部署工厂：给 bytecode + ABI，返回 ContractHandle。

    带构造函数的合约传 `args` + `arg_types`。
    """

    def _deploy(
        bytecode: str,
        abi: dict,
        *,
        sender: str | None = None,
        gas: int = DEFAULT_GAS,
        args: tuple = (),
        arg_types: tuple = (),
    ) -> ContractHandle:
        return deploy_contract(
            chain,
            bytecode,
            abi,
            sender=sender or accounts[0],
            gas=gas,
            constructor_args=args,
            constructor_types=arg_types,
        )

    return _deploy


@pytest.fixture
def erc20(contract: Callable[..., ContractHandle]) -> ContractHandle:
    """被测业务合约：SimpleERC20（1,000,000 SHT 全部分配给部署者）。

    可用环境变量 `ETH_QA_ERC20_VARIANT` 切换成**合约层变异体**：
    变异测试用它来验证「这套用例能不能抓住合约本身的 bug」。
    """
    variant = os.environ.get("ETH_QA_ERC20_VARIANT", "good")
    bytecode = (
        ERC20_BYTECODE
        if variant == "good"
        else ERC20_MUTANT_BYTECODES.get(variant, ERC20_BYTECODE)
    )

    return contract(
        bytecode,
        ERC20_ABI,
        gas=4_000_000,  # 合约约 4.6KB，默认 50 万不够部署
        args=(ERC20_NAME, ERC20_SYMBOL, ERC20_DECIMALS, ERC20_INITIAL_SUPPLY),
        arg_types=ERC20_CONSTRUCTOR_TYPES,
    )


@pytest.fixture
def math(contract: Callable[..., ContractHandle]) -> ContractHandle:
    """算术合约：counter / increment / add / multiply7 / return13。"""
    return contract(MATH_BYTECODE, MATH_ABI)


@pytest.fixture
def emitter(contract: Callable[..., ContractHandle]) -> ContractHandle:
    """事件合约：能发 0-4 个参数、带不带 indexed 的日志。"""
    return contract(EMITTER_BYTECODE, EMITTER_ABI)


@pytest.fixture
def gas_burner(contract: Callable[..., ContractHandle]) -> ContractHandle:
    """gas 燃烧器：区块号越大，同样一次调用的 gas 越高。"""
    return contract(GAS_BURNER_BYTECODE, GAS_BURNER_ABI)


@pytest.fixture
def throws(contract: Callable[..., ContractHandle]) -> Callable[[str], ContractHandle]:
    """失败合约工厂，因为它有两个合约（throw_contract / revert_contract）。"""

    def _deploy(name: str) -> ContractHandle:
        return contract(THROWS_BYTECODE[name], THROWS_ABI[name])

    return _deploy


# ---------------------------------------------------------------------------
# 后端矩阵：同一套 API 在不同链配置下的行为必须被显式验证。
# ---------------------------------------------------------------------------


@pytest.fixture
def chain_manual() -> EthereumTester:
    """关闭自动挖矿的链：发交易只进 pending，必须手动 mine_block 才生效。"""
    return EthereumTester(auto_mine_transactions=False)


@pytest.fixture
def mock_chain() -> EthereumTester:
    """MockBackend：不做 EVM 执行，用于验证门面层的降级行为。"""
    return EthereumTester(backend=MockBackend())
