"""把 repo 根目录加入 sys.path，并注册 eth_qa 作为 pytest 插件。

这样 `python -m pytest` 在**不安装包**的情况下也能直接跑，clone 下来即可用。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest_plugins = ["eth_qa.plugin"]
