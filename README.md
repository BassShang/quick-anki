# Anki LLM Vocabulary Auto-Importer

这是一个利用大语言模型（LLM）将原生文本整理并自动导入 Anki 的自动化工具。

核心逻辑：**Raw Text -> LLM (提取/清洗) -> Check Anki (查重) -> Import (制卡)**。

## ✨ 功能特性

*   **智能清洗**：利用 LLM (Doubao/Volcengine) 从 Vocabulary.com 等来源的杂乱文本中提取单词、IPA 音标、语境解释（Blurb）和释义。
*   **第0步检查**：脚本启动时自动检查 AnkiConnect 接口连通性以及目标 Deck 是否存在（不存在则自动创建）。
*   **智能查重**：在插入卡片前，自动查询当前 Deck 中是否已包含该单词，避免重复制卡。
*   **日志系统**：按日期（`YYYY_mm_dd.log`）生成独立日志，详细记录输入、LLM 响应、查重结果及报错信息。

## 🛠️ 前置要求

1.  **Anki Desktop**: 请确保已安装 Anki 桌面版并保持后台运行。
2.  **AnkiConnect**: 必须安装 Anki 插件 [AnkiConnect](https://ankiweb.net/shared/info/2055492159) (代码: `2055492159`)。
    *   *注意：安装后需重启 Anki。*
3.  **Python 3.8+**
4.  **API Key**: 拥有火山引擎（Doubao）或其他兼容 OpenAI SDK 的 API Key。

## 📦 安装指南

1.  **克隆或下载本项目**

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```
    *`requirements.txt` 内容应包含：`openai`, `python-dotenv`, `requests`*

3.  **配置文件**
    在项目根目录下创建一个 `.env` 文件，并填入以下内容：

    ```ini
    # --- LLM 配置 (火山引擎示例) ---
    ARK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx      # 您的 API Key
    ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
    ARK_MODEL_ID=doubao-1-5-pro-32k-250115       # 您的推理接入点 ID

    # --- Anki 配置 ---
    ANKI_CONNECT_URL=http://127.0.0.1:8765       # AnkiConnect 默认地址
    ANKI_DECK_NAME=Vocabulary                    # 目标牌组名称
    ANKI_MODEL_NAME=Basic                        # 笔记类型 (Basic/Front and Back)

    # --- 日志配置 ---
    LOG_ENABLED=True
    LOG_DIR=./logs
    ```

## 🚀 使用方法

### 1. 直接运行 (测试)

您可以直接运行 `main.py` 来测试功能。请先修改 `main.py` 底部 `if __name__ == "__main__":` 中的 `sample_text` 为您想测试的文本。

```bash
python main.py
```

### 2. 作为模块调用 (集成)

在您的其他 Python 脚本中引入并调用核心函数：

```python
from main import process_vocabulary

raw_text = """
ephemeral
/əˈfem(ə)rəl/
Something that is fleeting or short-lived is ephemeral...
"""

# 这将自动执行：检查环境 -> 调用LLM -> 查重 -> 插入Anki
process_vocabulary(raw_text)
```

## 📂 项目结构

```text
.
├── main.py              # 核心逻辑脚本
├── .env                 # 配置文件 (需手动创建)
├── requirements.txt     # Python 依赖库
├── README.md            # 项目说明
└── logs/                # 日志目录 (自动生成)
    ├── 2023_10_27.log
    └── ...
```

## 📝 日志说明

每次运行都会在 `logs/` 目录下生成或追加当天的日志文件。日志包含以下关键信息：

*   **INFO**: 接口连接状态、Deck 状态、单词查重结果（存在/不存在）、插入结果。
*   **ERROR**: 网络错误、API 调用失败、JSON 解析错误等。

**日志示例：**
```text
2023-10-27 10:00:01 - INFO - >>> 开始环境检查 (Step 0)
2023-10-27 10:00:01 - INFO - AnkiConnect 连接成功, API版本: 6
2023-10-27 10:00:01 - INFO - Deck 'Vocabulary' 存在。
2023-10-27 10:00:02 - INFO - LLM 调用成功
2023-10-27 10:00:02 - INFO - 查询单词 'spurious' 是否存在: 是
2023-10-27 10:00:02 - INFO - 单词 'spurious' 已存在于 Deck 'Vocabulary' 中。跳过插入。
```

## ⚠️ 常见问题

1.  **ConnectionRefusedError / 无法连接 AnkiConnect**
    *   检查 Anki 是否已打开。
    *   检查 AnkiConnect 配置（`工具` -> `附加组件` -> `AnkiConnect` -> `配置`）中 `webBindAddress` 是否为 `127.0.0.1`。

2.  **LLM 返回格式错误**
    *   脚本内置了 JSON 提取器，可以处理 LLM 偶尔包裹 markdown 代码块的情况。如果依然报错，请检查 `logs` 中的 `LLM 原始返回`，可能需要微调 Prompt。

3.  **Deck 不存在**
    *   脚本会自动尝试创建 Deck。如果创建失败，请检查 AnkiConnect 权限或手动在 Anki 中创建同名牌组。