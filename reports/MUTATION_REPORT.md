# 变异测试报告

- 生成时间（UTC）：2026-11-15T14:11:55+00:00
- 变异体总数：17
- 被杀灭：17
- 存活：0
- **变异得分：100.0%**

## 判定口径

| 结论 | 含义 | 处置 |
| --- | --- | --- |
| KILLED | 注入缺陷后套件变红 → 这块行为真的被验证过 | 无需动作 |
| SURVIVED | 注入缺陷后套件仍全绿 → **用例空洞** | 补用例，或写明为什么不管 |

## 变异体明细

| 变异体 | 层级 | 注入的缺陷 | 结果 | 耗时(s) | 命中的用例 |
| --- | --- | --- | --- | --- | --- |
| `balance_off_by_one` | python | get_balance 多返回 1 wei | KILLED | 14.51 | `tests/test_mutation_hardening.py::TestAbsoluteValues::test_genesis_balance_is_exactly_one_million_ether` |
| `call_mines_block` | python | 只读调用也产块 | KILLED | 4.12 | `tests/test_chain_regression.py::TestContract::test_contract_call_does_not_mine_a_block` |
| `contract_no_allowance_decrement` | contract | 合约变异体：transferFrom 不递减 allowance | KILLED | 6.4 | `tests/test_erc20.py::TestApproval::test_transfer_from_consumes_allowance` |
| `contract_no_balance_check` | contract | 合约变异体：transfer 跳过余额检查（unchecked 下溢回绕） | KILLED | 6.15 | `tests/test_erc20.py::TestTransfer::test_transfer_more_than_balance_reverts_with_custom_error` |
| `estimate_gas_doubled` | python | gas 估算翻倍 | KILLED | 4.21 | `tests/test_chain_regression.py::TestTransactionReceipt::test_gas_estimate_for_plain_transfer_is_21000` |
| `fee_history_truncated` | python | 费率历史永远只返 1 条 | KILLED | 13.96 | `tests/test_mutation_hardening.py::TestFeeHistoryWindow::test_fee_history_returns_requested_window_size` |
| `get_code_empty` | python | 永远说合约没字节码 | KILLED | 4.29 | `tests/test_chain_regression.py::TestContract::test_deployed_code_is_stored_on_chain` |
| `logs_dropped` | python | 事件日志全丢 | KILLED | 3.47 | `tests/test_api_surface.py::TestQueryApi::test_get_logs_filters_by_address` |
| `mine_blocks_ignores_count` | python | 要求挖 N 块实际只挖 1 块 | KILLED | 3.72 | `tests/test_backend_matrix.py::TestAutoMineDisabled::test_mine_blocks_applies_pending_and_advances` |
| `nonce_frozen` | python | nonce 永远返回 0 | KILLED | 3.47 | `tests/test_api_surface.py::TestQueryApi::test_get_nonce_increments_after_transaction` |
| `receipt_gas_price_wrong` | python | 回执成交价永远报 1 wei | KILLED | 3.87 | `tests/test_chain_regression.py::TestNativeTransfer::test_sender_is_charged_value_plus_gas` |
| `receipt_status_always_1` | python | 失败交易也报 status=1 | KILLED | 3.66 | `tests/test_backend_matrix.py::TestMockBackend::test_contract_deployment_yields_no_address` |
| `receipt_type_legacy` | python | EIP-1559 交易被标成 0x0 | KILLED | 15.09 | `tests/test_mutation_hardening.py::TestReceiptContract::test_receipt_type_is_present_on_the_receipt` |
| `revert_to_snapshot_noop` | python | 快照回滚变成空操作 | KILLED | 3.66 | `tests/test_api_surface.py::TestChainLifecycle::test_disable_then_enable_auto_mine` |
| `storage_slot_ignored` | python | storage 永远读 slot 0 | KILLED | 3.33 | `tests/test_api_surface.py::TestQueryApi::test_get_storage_at_requires_hex_slot` |
| `transfer_value_dropped` | python | 交易金额被抹成 0 | KILLED | 3.51 | `tests/test_api_surface.py::TestChainLifecycle::test_reset_to_genesis_clears_state` |
| `zero_address_rejected` | python | 禁止转给零地址 | KILLED | 4.0 | `tests/test_chain_regression.py::TestNativeTransfer::test_transfer_to_zero_address_is_allowed_by_the_evm` |

## 存活的变异体（测试套件的空洞）

无。当前变异体集合全部被杀灭。
