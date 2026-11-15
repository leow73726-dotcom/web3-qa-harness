"""合约句柄层：把「ABI 编码 → 发交易 → 解码返回值 / 事件」这套活包起来。

eth-tester 自带的四个预编译合约只给了 bytecode + ABI，没有任何调用封装。
这个模块把 ABI 编码、交易发送、返回值解码、事件解码统一成一个 ContractHandle，
让用例可以写成 `math.read("counter")` 而不是手拼 4 字节选择器。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from eth_abi import decode, encode
from eth_tester import EthereumTester
from eth_utils import decode_hex, encode_hex, event_abi_to_log_topic
from eth_utils.abi import function_abi_to_4byte_selector

DEFAULT_GAS = 500_000


def _topic_hex(value: Any) -> str:
    """把 bytes / HexBytes / "0x..." 统一成小写十六进制字符串，方便比较。"""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    return str(value).lower()


@dataclass
class DecodedLog:
    """一条已解码的日志。name 为 None 表示匿名事件或未知事件。"""

    name: str | None
    args: dict[str, Any] = field(default_factory=dict)
    raw_topics: list[str] = field(default_factory=list)
    raw_data: str = "0x"


class ContractHandle:
    """一个已部署合约的操作句柄。"""

    def __init__(self, chain: EthereumTester, address: str, abi: Mapping[str, Mapping]):
        self.chain = chain
        self.address = address
        self.abi = dict(abi)
        self._event_index = self._build_event_index()

    # ------------------------------------------------------------------ 编码
    def _entry(self, fn_name: str) -> Mapping:
        try:
            entry = self.abi[fn_name]
        except KeyError:
            raise KeyError(
                f"{fn_name!r} not in ABI; available: {sorted(self.abi)}"
            ) from None
        if entry.get("type") not in (None, "function"):
            raise TypeError(f"{fn_name!r} is a {entry.get('type')}, not a function")
        return entry

    def encode(self, fn_name: str, args: Sequence[Any] = ()) -> str:
        entry = self._entry(fn_name)
        arg_types = [a["type"] for a in entry.get("inputs", [])]
        selector = function_abi_to_4byte_selector(entry)
        return encode_hex(selector + encode(arg_types, list(args)))

    def _decode_output(self, fn_name: str, raw: str) -> Any:
        entry = self._entry(fn_name)
        out_types = [a["type"] for a in entry.get("outputs", [])]
        if not out_types:
            return None
        return decode(out_types, decode_hex(raw))

    # ------------------------------------------------------------------ 调用
    def read(self, fn_name: str, args: Sequence[Any] = (), *, sender: str | None = None) -> Any:
        """只读调用（不产块、不花 gas）。"""
        sender = sender or self.chain.get_accounts()[0]
        raw = self.chain.call(
            {"from": sender, "to": self.address, "data": self.encode(fn_name, args)}
        )
        return self._decode_output(fn_name, raw)

    def send(
        self,
        fn_name: str,
        args: Sequence[Any] = (),
        *,
        sender: str | None = None,
        gas: int = DEFAULT_GAS,
        value: int = 0,
    ) -> dict[str, Any]:
        """发起状态变更交易，返回回执。"""
        sender = sender or self.chain.get_accounts()[0]
        tx_hash = self.chain.send_transaction(
            {
                "from": sender,
                "to": self.address,
                "gas": gas,
                "value": value,
                "data": self.encode(fn_name, args),
            }
        )
        return self.chain.get_transaction_receipt(tx_hash)

    # ------------------------------------------------------------------ 事件
    def _build_event_index(self) -> dict[str, tuple[str, Mapping]]:
        index: dict[str, tuple[str, Mapping]] = {}
        for name, entry in self.abi.items():
            if entry.get("type") == "event":
                index[_topic_hex(event_abi_to_log_topic(entry))] = (name, entry)
        return index

    def decode_logs(self, receipt: Mapping[str, Any]) -> list[DecodedLog]:
        """把回执里的 logs 解码成事件名 + 参数。"""
        decoded: list[DecodedLog] = []
        for log in receipt.get("logs", []):
            topics = [_topic_hex(t) for t in log.get("topics", [])]
            data = _topic_hex(log.get("data", "0x"))
            name: str | None = None
            args: dict[str, Any] = {}

            if topics and topics[0] in self._event_index:
                name, entry = self._event_index[topics[0]]
                inputs = entry.get("inputs", [])
                indexed = [i for i in inputs if i.get("indexed")]
                plain = [i for i in inputs if not i.get("indexed")]

                for spec, topic in zip(indexed, topics[1:]):
                    args[spec["name"]] = self._decode_topic(spec["type"], topic)

                if plain:
                    values = decode(
                        [i["type"] for i in plain],
                        decode_hex(data) if data not in ("0x", "") else b"",
                    )
                    for spec, value in zip(plain, values):
                        args[spec["name"]] = value

            decoded.append(
                DecodedLog(name=name, args=args, raw_topics=topics, raw_data=data)
            )
        return decoded

    @staticmethod
    def _decode_topic(type_name: str, topic_hex: str) -> Any:
        try:
            return decode([type_name], decode_hex(topic_hex))[0]
        except Exception:  # noqa: BLE001 - topic 解码失败时保留原始值更有用
            return topic_hex


def error_selector(abi_entry: Mapping) -> bytes:
    """算出 custom error 的 4 字节选择器（与函数选择器同算法）。"""
    return function_abi_to_4byte_selector(abi_entry)


def revert_data(exc: BaseException) -> bytes:
    """从异常里取出 revert 的原始字节。

    eth-tester 抛 `TransactionFailed` 时，revert data 是以**字符串形式的 bytes repr**
    放在 `args[0]` 里的（形如 `b'\\xdbB\\x14M...'`），不是真正的 bytes。
    这里统一还原成 bytes，方便断言选择器。这是个容易踩的坑。
    """
    raw: Any = exc.args[0] if exc.args else b""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    text = str(raw)
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (bytes, bytearray)):
            return bytes(parsed)
    except (ValueError, SyntaxError):
        pass
    return text.encode("utf-8", errors="replace")


def decode_error(abi_entry: Mapping, payload: bytes) -> tuple:
    """把 revert payload 解码成自定义错误的参数元组。"""
    types = [i["type"] for i in abi_entry.get("inputs", [])]
    return decode(types, payload[4:]) if types else ()


def deploy_contract(
    chain: EthereumTester,
    bytecode: str,
    abi: Mapping[str, Mapping],
    *,
    sender: str | None = None,
    gas: int = DEFAULT_GAS,
    constructor_args: Sequence[Any] = (),
    constructor_types: Sequence[str] = (),
) -> ContractHandle:
    """部署合约并返回可操作句柄。

    带构造函数参数的合约，需要把 ABI 编码后的参数**追加到 bytecode 末尾**。
    """
    raw = bytes.fromhex(bytecode.removeprefix("0x"))
    if constructor_args:
        raw += encode(list(constructor_types), list(constructor_args))

    sender = sender or chain.get_accounts()[0]
    tx_hash = chain.send_transaction(
        {"from": sender, "gas": gas, "data": "0x" + raw.hex()}
    )
    receipt = chain.get_transaction_receipt(tx_hash)
    address = receipt["contract_address"]
    if not address:
        raise RuntimeError("contract deployment produced no address (deploy failed?)")
    return ContractHandle(chain, address, abi)
