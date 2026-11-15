"""pytest 插件：按环境变量 ETH_QA_MUTANT 在会话开始前注入一个变异体。

由 `eth_qa.mutation` 通过子进程调用：
    ETH_QA_MUTANT=<name> python -m pytest tests -p eth_qa.mutant_plugin
"""

from __future__ import annotations

import os

from eth_qa.mutants import apply_mutant


def pytest_configure(config):  # noqa: ARG001
    name = os.environ.get("ETH_QA_MUTANT")
    if name:
        apply_mutant(name)
