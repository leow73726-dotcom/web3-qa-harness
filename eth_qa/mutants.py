"""变异体注册表：对被测系统注入「看起来合理但其实是 bug」的行为改动。

思路来自变异测试（mutation testing）：如果我把代码改坏，而测试套件仍然全绿，
那说明这段代码**根本没被有效验证过**——用例在，但断言是空的。

每个变异体都只改一处**对外行为**，不改到「直接崩溃」的程度，
否则杀灭就变成了「因为报错所以失败」，失去意义。
"""

from __future__ import annotations

from typing import Any, Callable

from eth_tester import EthereumTester
from eth_tester.exceptions import ValidationError

ZERO_ADDRESS = "0x" + "00" * 20


def _patch(name: str, factory: Callable[[Any], Any]) -> None:
    original = getattr(EthereumTester, name)
    setattr(EthereumTester, name, factory(original))


def _receipt_rewriter(mutate: Callable[[dict], dict]) -> Callable[[Any], Any]:
    """生成一个包装 get_transaction_receipt 的变异函数。"""

    def factory(original):
        def wrapper(self, *args, **kwargs):
            return mutate(dict(original(self, *args, **kwargs)))

        return wrapper

    return factory


# --------------------------------------------------------------------------
# 各自定义
# --------------------------------------------------------------------------


def _m_balance_off_by_one():
    """get_balance 多返回 1 wei —— 只影响绝对值，不影响相对变化。"""
    _patch("get_balance", lambda orig: lambda self, *a, **k: orig(self, *a, **k) + 1)


def _m_transfer_value_dropped():
    """交易照发，但金额被抹成 0 —— 收款方永远收不到钱。"""

    def factory(original):
        def wrapper(self, transaction, *args, **kwargs):
            tx = dict(transaction)
            tx["value"] = 0
            return original(self, tx, *args, **kwargs)

        return wrapper

    _patch("send_transaction", factory)


def _m_receipt_status_always_1():
    """失败交易也报成功 —— 最经典的「看起来没事」缺陷。"""
    _patch("get_transaction_receipt", _receipt_rewriter(lambda r: {**r, "status": 1}))


def _m_receipt_gas_price_wrong():
    """回执里的成交价永远报 1 wei —— 对账时全错。"""
    _patch(
        "get_transaction_receipt",
        _receipt_rewriter(lambda r: {**r, "effective_gas_price": 1}),
    )


def _m_receipt_type_legacy():
    """EIP-1559 交易被标成老类型 0x0 —— 下游解析全错。"""
    _patch(
        "get_transaction_receipt",
        _receipt_rewriter(lambda r: {**r, "type": "0x0"}),
    )


def _m_call_mines_block():
    """只读调用也产块 —— 破坏「查询不写账本」的契约。"""

    def factory(original):
        def wrapper(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            try:
                self.mine_block()
            except Exception:  # noqa: BLE001 - 变异体不应因为挖块失败而崩溃
                pass
            return result

        return wrapper

    _patch("call", factory)


def _m_revert_to_snapshot_noop():
    """回滚变成空操作 —— 快照测试会立刻失去保护力。"""
    _patch("revert_to_snapshot", lambda orig: lambda self, *a, **k: None)


def _m_get_code_empty():
    """永远说合约没有字节码。"""
    _patch("get_code", lambda orig: lambda self, *a, **k: "0x")


def _m_nonce_frozen():
    """nonce 永远返回 0。"""
    _patch("get_nonce", lambda orig: lambda self, *a, **k: 0)


def _m_logs_dropped():
    """事件日志全丢 —— dApp 前端会完全收不到通知。"""
    _patch("get_transaction_receipt", _receipt_rewriter(lambda r: {**r, "logs": []}))


def _m_estimate_gas_doubled():
    """gas 估算翻倍。"""
    _patch("estimate_gas", lambda orig: lambda self, *a, **k: orig(self, *a, **k) * 2)


def _m_mine_blocks_ignores_count():
    """要求挖 N 个块，实际只挖 1 个。"""

    def factory(original):
        def wrapper(self, num_blocks=1, *args, **kwargs):
            return original(self, 1, *args, **kwargs)

        return wrapper

    _patch("mine_blocks", factory)


def _m_zero_address_rejected():
    """「好心」禁止转给零地址 —— 悄悄改了链的兼容行为。"""

    def factory(original):
        def wrapper(self, transaction, *args, **kwargs):
            to = (transaction or {}).get("to")
            if isinstance(to, str) and to.lower() == ZERO_ADDRESS:
                raise ValidationError("transfer to the zero address is not allowed")
            return original(self, transaction, *args, **kwargs)

        return wrapper

    _patch("send_transaction", factory)


def _m_storage_slot_ignored():
    """不管查哪个 slot，永远返回 slot 0 —— 只有读非零 slot 才看得出来。"""

    def factory(original):
        def wrapper(self, account, slot, *args, **kwargs):
            return original(self, account, "0x0", *args, **kwargs)

        return wrapper

    _patch("get_storage_at", factory)


def _m_fee_history_truncated():
    """费率历史永远只返回 1 条 —— 只断言「非空」的用例抓不到。"""

    def factory(original):
        def wrapper(self, *args, **kwargs):
            history = dict(original(self, *args, **kwargs))
            for key in ("base_fee_per_gas", "gas_used_ratio", "reward"):
                if key in history and history[key]:
                    history[key] = history[key][:1]
            return history

        return wrapper

    _patch("get_fee_history", factory)


# --------------------------------------------------------------------------
# 注册表：name -> (说明, 应用函数)
# --------------------------------------------------------------------------

MUTANTS: dict[str, tuple[str, Callable[[], None]]] = {
    "balance_off_by_one": ("get_balance 多返回 1 wei", _m_balance_off_by_one),
    "transfer_value_dropped": ("交易金额被抹成 0", _m_transfer_value_dropped),
    "receipt_status_always_1": ("失败交易也报 status=1", _m_receipt_status_always_1),
    "receipt_gas_price_wrong": ("回执成交价永远报 1 wei", _m_receipt_gas_price_wrong),
    "receipt_type_legacy": ("EIP-1559 交易被标成 0x0", _m_receipt_type_legacy),
    "call_mines_block": ("只读调用也产块", _m_call_mines_block),
    "revert_to_snapshot_noop": ("快照回滚变成空操作", _m_revert_to_snapshot_noop),
    "get_code_empty": ("永远说合约没字节码", _m_get_code_empty),
    "nonce_frozen": ("nonce 永远返回 0", _m_nonce_frozen),
    "logs_dropped": ("事件日志全丢", _m_logs_dropped),
    "estimate_gas_doubled": ("gas 估算翻倍", _m_estimate_gas_doubled),
    "mine_blocks_ignores_count": ("要求挖 N 块实际只挖 1 块", _m_mine_blocks_ignores_count),
    "zero_address_rejected": ("禁止转给零地址", _m_zero_address_rejected),
    "storage_slot_ignored": ("storage 永远读 slot 0", _m_storage_slot_ignored),
    "fee_history_truncated": ("费率历史永远只返 1 条", _m_fee_history_truncated),
}


def apply_mutant(name: str) -> None:
    if name not in MUTANTS:
        raise SystemExit(f"unknown mutant: {name}. Available: {sorted(MUTANTS)}")
    MUTANTS[name][1]()


# --------------------------------------------------------------------------
# 合约层变异体
#
# 上面 15 个变异体只能覆盖 eth-tester 的 **Python 层**；合约本身是 EVM 字节码，
# 打不了 Python 补丁。所以另外编译两个「故意写错的 ERC-20」，部署它们跑同一套
# ERC-20 用例 —— 这才是真正意义上的「合约变异测试」。
# --------------------------------------------------------------------------

CONTRACT_MUTANTS: dict[str, tuple[str, str]] = {
    "contract_no_allowance_decrement": (
        "合约变异体：transferFrom 不递减 allowance",
        "no_allowance_decrement",
    ),
    "contract_no_balance_check": (
        "合约变异体：transfer 跳过余额检查（unchecked 下溢回绕）",
        "no_balance_check",
    ),
}
