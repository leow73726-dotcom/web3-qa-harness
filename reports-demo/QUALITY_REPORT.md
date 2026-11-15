# Web3 链上回归 · 质量门禁报告

- 生成时间（UTC）：2026-11-15T14:11:21+00:00
- 执行轮次：3
- 用例总数：1
- 稳定通过：0
- 不稳定（flaky）：0
- 稳定失败：1

## 判定规则

| 结论 | 条件 | 处置 |
| --- | --- | --- |
| stable-pass | 每轮都通过 | 可进 CI 门禁 |
| flaky | 部分轮次通过 | 不得进门禁，先定位不确定性来源 |
| stable-fail | 每轮都失败 | 转缺陷单，阻断合入 |

## 用例明细

| 用例 | 结论 | 通过率 | 平均耗时(s) |
| --- | --- | --- | --- |
| `test_doc_style::test_doc_style_validation_error_is_caught` | stable-fail | 0/3 (0%) | 0.032 |

## 失败证据

### test_doc_style::test_doc_style_validation_error_is_caught

- 结论：stable-fail，通过率 0/3
- 失败信息：eth_utils.exceptions.ValidationError: Sender does not have enough balance to cover transaction value and gas (has 1000000000000000000000000, needs 2000000000021000000000000)

