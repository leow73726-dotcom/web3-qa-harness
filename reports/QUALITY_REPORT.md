# Web3 链上回归 · 质量门禁报告

- 生成时间（UTC）：2026-11-15T11:40:34+00:00
- 执行轮次：3
- 用例总数：84
- 稳定通过：84
- 不稳定（flaky）：0
- 稳定失败：0

## 判定规则

| 结论 | 条件 | 处置 |
| --- | --- | --- |
| stable-pass | 每轮都通过 | 可进 CI 门禁 |
| flaky | 部分轮次通过 | 不得进门禁，先定位不确定性来源 |
| stable-fail | 每轮都失败 | 转缺陷单，阻断合入 |

## 用例明细

| 用例 | 结论 | 通过率 | 平均耗时(s) |
| --- | --- | --- | --- |
| `TestAbsoluteValues::test_gas_price_of_a_plain_transfer_is_positive` | stable-pass | 3/3 (100%) | 0.036 |
| `TestAbsoluteValues::test_genesis_balance_is_exactly_one_million_ether` | stable-pass | 3/3 (100%) | 0.021 |
| `TestAccounts::test_accounts_are_valid_hex_addresses` | stable-pass | 3/3 (100%) | 0.013 |
| `TestAccounts::test_chain_exposes_ten_prefunded_accounts` | stable-pass | 3/3 (100%) | 0.013 |
| `TestAccounts::test_every_account_starts_with_the_same_balance` | stable-pass | 3/3 (100%) | 0.015 |
| `TestApproval::test_approve_overwrites_previous_allowance` | stable-pass | 3/3 (100%) | 0.069 |
| `TestApproval::test_approve_sets_allowance_and_emits` | stable-pass | 3/3 (100%) | 0.054 |
| `TestApproval::test_infinite_allowance_is_not_decremented` | stable-pass | 3/3 (100%) | 0.072 |
| `TestApproval::test_transfer_from_beyond_allowance_reverts` | stable-pass | 3/3 (100%) | 0.055 |
| `TestApproval::test_transfer_from_consumes_allowance` | stable-pass | 3/3 (100%) | 0.071 |
| `TestApproval::test_transfer_from_without_approval_reverts` | stable-pass | 3/3 (100%) | 0.040 |
| `TestAutoMineDisabled::test_balance_unchanged_until_mined` | stable-pass | 3/3 (100%) | 0.030 |
| `TestAutoMineDisabled::test_mine_blocks_applies_pending_and_advances` | stable-pass | 3/3 (100%) | 0.046 |
| `TestAutoMineDisabled::test_receipt_is_unavailable_before_mining` | stable-pass | 3/3 (100%) | 0.029 |
| `TestAutoMineDisabled::test_send_does_not_advance_block` | stable-pass | 3/3 (100%) | 0.033 |
| `TestChainLifecycle::test_disable_then_enable_auto_mine` | stable-pass | 3/3 (100%) | 0.050 |
| `TestChainLifecycle::test_reset_to_genesis_clears_state` | stable-pass | 3/3 (100%) | 0.035 |
| `TestConservationLaw::test_self_transfer_costs_only_gas` | stable-pass | 3/3 (100%) | 0.659 |
| `TestConservationLaw::test_total_balance_only_drops_by_gas` | stable-pass | 3/3 (100%) | 1.482 |
| `TestContract::test_contract_call_does_not_mine_a_block` | stable-pass | 3/3 (100%) | 0.034 |
| `TestContract::test_deployed_code_is_stored_on_chain` | stable-pass | 3/3 (100%) | 0.031 |
| `TestContract::test_minimal_contract_returns_42` | stable-pass | 3/3 (100%) | 0.034 |
| `TestEmitterContract::test_double_arg_event_payload` | stable-pass | 3/3 (100%) | 0.047 |
| `TestEmitterContract::test_indexed_argument_lands_in_topics` | stable-pass | 3/3 (100%) | 0.046 |
| `TestEmitterContract::test_no_argument_event` | stable-pass | 3/3 (100%) | 0.049 |
| `TestEmitterContract::test_single_arg_event_payload` | stable-pass | 3/3 (100%) | 0.048 |
| `TestEmitterContract::test_successful_call_without_events_has_no_logs` | stable-pass | 3/3 (100%) | 0.048 |
| `TestFailureAccounting::test_revert_burns_gas_but_transfers_nothing` | stable-pass | 3/3 (100%) | 0.055 |
| `TestFailureAccounting::test_validation_failure_has_zero_side_effects` | stable-pass | 3/3 (100%) | 0.255 |
| `TestFeeHistoryWindow::test_fee_history_returns_requested_window_size` | stable-pass | 3/3 (100%) | 0.017 |
| `TestFilters::test_block_filter_tracks_new_blocks` | stable-pass | 3/3 (100%) | 0.024 |
| `TestFilters::test_delete_filter_makes_it_unusable` | stable-pass | 3/3 (100%) | 0.014 |
| `TestGasBurnerContract::test_gas_estimate_tracks_block_number` | stable-pass | 3/3 (100%) | 0.256 |
| `TestGasBurnerContract::test_gas_used_grows_with_block_number` | stable-pass | 3/3 (100%) | 0.111 |
| `TestInvariants::test_allowance_never_exceeds_what_was_approved` | stable-pass | 3/3 (100%) | 1.125 |
| `TestInvariants::test_sum_of_balances_always_equals_total_supply` | stable-pass | 3/3 (100%) | 1.622 |
| `TestInvariants::test_total_supply_never_changes` | stable-pass | 3/3 (100%) | 0.089 |
| `TestMathContract::test_add_returns_sum[0-0-0]` | stable-pass | 3/3 (100%) | 0.033 |
| `TestMathContract::test_add_returns_sum[1000000000000000000-1-1000000000000000001]` | stable-pass | 3/3 (100%) | 0.033 |
| `TestMathContract::test_add_returns_sum[3-4-7]` | stable-pass | 3/3 (100%) | 0.036 |
| `TestMathContract::test_counter_starts_at_zero` | stable-pass | 3/3 (100%) | 0.033 |
| `TestMathContract::test_increment_is_monotonic` | stable-pass | 3/3 (100%) | 0.104 |
| `TestMathContract::test_multiply7` | stable-pass | 3/3 (100%) | 0.032 |
| `TestMathContract::test_return13_is_stable_across_calls` | stable-pass | 3/3 (100%) | 0.033 |
| `TestMetadataAndInitialAllocation::test_deployer_holds_the_entire_supply` | stable-pass | 3/3 (100%) | 0.058 |
| `TestMetadataAndInitialAllocation::test_metadata` | stable-pass | 3/3 (100%) | 0.042 |
| `TestMetadataAndInitialAllocation::test_total_supply_is_fixed_at_deploy` | stable-pass | 3/3 (100%) | 0.036 |
| `TestMockBackend::test_accounts_and_balances_are_available` | stable-pass | 3/3 (100%) | 0.002 |
| `TestMockBackend::test_call_is_not_implemented` | stable-pass | 3/3 (100%) | 0.001 |
| `TestMockBackend::test_contract_deployment_yields_no_address` | stable-pass | 3/3 (100%) | 0.002 |
| `TestMockBackend::test_get_code_returns_empty` | stable-pass | 3/3 (100%) | 0.001 |
| `TestNativeTransfer::test_backend_validation_error_type_differs_from_public_exception` | stable-pass | 3/3 (100%) | 0.032 |
| `TestNativeTransfer::test_native_transfer_updates_receiver_balance` | stable-pass | 3/3 (100%) | 0.026 |
| `TestNativeTransfer::test_sender_is_charged_value_plus_gas` | stable-pass | 3/3 (100%) | 0.032 |
| `TestNativeTransfer::test_transfer_larger_than_balance_is_rejected` | stable-pass | 3/3 (100%) | 0.023 |
| `TestNativeTransfer::test_transfer_to_zero_address_is_allowed_by_the_evm` | stable-pass | 3/3 (100%) | 0.034 |
| `TestNonceAndReadOnly::test_call_has_no_side_effects` | stable-pass | 3/3 (100%) | 0.051 |
| `TestNonceAndReadOnly::test_nonce_is_monotonic` | stable-pass | 3/3 (100%) | 1.125 |
| `TestQueryApi::test_get_fee_history_returns_series` | stable-pass | 3/3 (100%) | 0.030 |
| `TestQueryApi::test_get_logs_filters_by_address` | stable-pass | 3/3 (100%) | 0.054 |
| `TestQueryApi::test_get_nonce_increments_after_transaction` | stable-pass | 3/3 (100%) | 0.031 |
| `TestQueryApi::test_get_storage_at_reads_counter_slot` | stable-pass | 3/3 (100%) | 0.050 |
| `TestQueryApi::test_get_storage_at_requires_hex_slot` | stable-pass | 3/3 (100%) | 0.031 |
| `TestQueryApi::test_time_travel_shifts_block_timestamp` | stable-pass | 3/3 (100%) | 0.015 |
| `TestReceiptContract::test_receipt_type_is_present_on_the_receipt` | stable-pass | 3/3 (100%) | 0.032 |
| `TestSnapshotIdempotence::test_revert_is_idempotent` | stable-pass | 3/3 (100%) | 0.111 |
| `TestSnapshotIsolation::test_revert_also_rolls_back_contract_deployment` | stable-pass | 3/3 (100%) | 0.030 |
| `TestSnapshotIsolation::test_snapshot_revert_restores_balance` | stable-pass | 3/3 (100%) | 0.025 |
| `TestStorageSlotSemantics::test_get_storage_at_distinguishes_slots` | stable-pass | 3/3 (100%) | 0.051 |
| `TestThrowsContract::test_failed_call_does_not_change_stored_state` | stable-pass | 3/3 (100%) | 0.066 |
| `TestThrowsContract::test_initial_value_is_one` | stable-pass | 3/3 (100%) | 0.031 |
| `TestThrowsContract::test_revert_contract_covers_both_branches` | stable-pass | 3/3 (100%) | 0.068 |
| `TestThrowsContract::test_set_value_persists` | stable-pass | 3/3 (100%) | 0.049 |
| `TestThrowsContract::test_will_throw_yields_failed_receipt_instead_of_exception` | stable-pass | 3/3 (100%) | 0.046 |
| `TestTransactionReceipt::test_eip1559_transaction_is_typed_0x2` | stable-pass | 3/3 (100%) | 0.030 |
| `TestTransactionReceipt::test_gas_estimate_for_plain_transfer_is_21000` | stable-pass | 3/3 (100%) | 0.014 |
| `TestTransactionReceipt::test_receipt_has_required_fields` | stable-pass | 3/3 (100%) | 0.030 |
| `TestTransfer::test_self_transfer_keeps_balance_and_emits` | stable-pass | 3/3 (100%) | 0.059 |
| `TestTransfer::test_transfer_emits_transfer_event_with_decoded_args` | stable-pass | 3/3 (100%) | 0.054 |
| `TestTransfer::test_transfer_more_than_balance_reverts_with_custom_error` | stable-pass | 3/3 (100%) | 0.037 |
| `TestTransfer::test_transfer_moves_value` | stable-pass | 3/3 (100%) | 0.063 |
| `TestTransfer::test_transfer_returns_true` | stable-pass | 3/3 (100%) | 0.038 |
| `TestTransfer::test_transfer_to_zero_address_is_allowed_by_the_contract` | stable-pass | 3/3 (100%) | 0.054 |
| `TestTransfer::test_zero_value_transfer_is_allowed_and_emits` | stable-pass | 3/3 (100%) | 0.056 |

## 失败证据

无失败用例。
