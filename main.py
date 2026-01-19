import os
import json
import requests
import logging
import datetime
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# --- 配置读取 ---
ANKI_URL = os.getenv("ANKI_CONNECT_URL", "http://127.0.0.1:8765")
ANKI_DECK = os.getenv("ANKI_DECK_NAME", "Default")
ANKI_MODEL = os.getenv("ANKI_MODEL_NAME", "Basic")
ARK_API_KEY = os.getenv("ARK_API_KEY")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL_ID = os.getenv("ARK_MODEL_ID")

LOG_ENABLED = os.getenv("LOG_ENABLED", "True").lower() == "true"
LOG_DIR = os.getenv("LOG_DIR", "./logs")

# --- Prompt 模版 ---
PROMPT_TEMPLATE = """
# Role
You are an expert lexicographer, translator, and Anki card designer. Your goal is to process raw vocabulary text into a structured JSON object for Anki, enhancing it for learners who prefer English-English definitions but need auxiliary Chinese support.

# Input Text
{{RAW_TEXT}}

# Processing Rules
1. **Identify the Word**: Find the main headword.
2. **IPA**: Extract the IPA pronunciation (e.g., /.../). **CRITICAL:** If the raw text does not contain an IPA, you MUST generate the standard American English IPA yourself.
3. **The "Blurb" (Context)**: Locate the conversational explanation paragraph (common in Vocabulary.com).
   - **Highlighting**: Analyze the blurb and use `<b>` tags to highlight **key takeaways**, such as core synonyms, defining characteristics, or powerful collocations (e.g., highlight "complicated", "intricate" inside the sentence). Do not bold entire sentences, only the distinct semantic keywords.
4. **Definitions**: Extract the specific definitions (part of speech + meaning).
   - **Translation**: For every English definition, append a **concise** Chinese translation in parentheses.
5. **Clean Data**: Ignore UI elements like "Share", "IPA guide", or repeated headers.

# Output Format (JSON)
Return ONLY a valid JSON object with two keys: "front" and "back".

1. **"front"**: The word itself.
2. **"back"**: A HTML string containing the details.
   - Use `<div class='ipa'>` for the IPA.
   - Use `<div class='blurb'>` for the highlighted conversational explanation.
   - Use `<ul>` and `<li>` for definitions.
   - Format for list items: `<b>pos:</b> English definition (简短中文) <br><i>Synonyms: ...</i>`

# Example JSON Structure
{
  "front": "sophisticated",
  "back": "<div class='ipa'>/səˈfɪstɪkeɪtɪd/</div><br><div class='blurb'>If something is sophisticated, it's <b>complicated</b> and <b>intricate</b>. The inner workings of a computer are <b>sophisticated</b>. It can also refer to <b>having good taste</b>.</div><hr><ul><li><b>adj:</b> complex or intricate (复杂精密的) <br><i>Synonyms: advanced</i></li><li><b>adj:</b> having worldly knowledge and refinement (老练的；富有经验的) <br><i>Synonyms: urbane, cultured</i></li></ul>"
}
"""

# --- 日志设置 ---
def setup_logger():
    if not LOG_ENABLED:
        return logging.getLogger('dummy')
    
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    today_str = datetime.datetime.now().strftime("%Y_%m_%d")
    log_filename = f"{LOG_DIR}/{today_str}.log"
    
    logger = logging.getLogger('AnkiAutoImporter')
    logger.setLevel(logging.INFO)
    
    # 防止重复添加 Handler
    if not logger.handlers:
        # File Handler
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Console Handler (可选，方便调试)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger

logger = setup_logger()

# --- AnkiConnect 工具函数 ---
def invoke_anki(action, **params):
    requestJson = {"action": action, "version": 6}
    if params:
        requestJson["params"] = params
    
    try:
        response = requests.post(ANKI_URL, json=requestJson).json()
    except requests.exceptions.ConnectionError:
        error_msg = "无法连接到 AnkiConnect。请确保 Anki 已打开并安装了 AnkiConnect 插件。"
        logger.error(error_msg)
        raise Exception(error_msg)

    if len(response) != 2:
        raise Exception("AnkiConnect 响应格式错误")
    if "error" not in response:
        raise Exception("AnkiConnect 响应缺少 error 字段")
    if response["error"] is not None:
        raise Exception(f"AnkiConnect 返回错误: {response['error']}")
    
    return response["result"]

# --- 核心逻辑 ---

def check_environment():
    """第0步：检查接口连通性和Deck是否存在"""
    logger.info(">>> 开始环境检查 (Step 0)")
    
    # 1. 检查连接
    try:
        version = invoke_anki("version")
        logger.info(f"AnkiConnect 连接成功, API版本: {version}")
    except Exception as e:
        logger.critical(f"AnkiConnect 连接失败: {str(e)}")
        return False

    # 2. 检查 Deck 是否存在
    try:
        deck_list = invoke_anki("deckNames")
        if ANKI_DECK in deck_list:
            logger.info(f"Deck '{ANKI_DECK}' 存在。")
        else:
            logger.warning(f"Deck '{ANKI_DECK}' 不存在。尝试创建...")
            invoke_anki("createDeck", deck=ANKI_DECK)
            logger.info(f"Deck '{ANKI_DECK}' 创建成功。")
    except Exception as e:
        logger.critical(f"Deck 检查/创建失败: {str(e)}")
        return False
        
    return True

def call_llm(raw_text):
    """调用 LLM 进行数据清洗"""
    logger.info(">>> 开始调用 LLM 处理文本")
    
    if not raw_text or not raw_text.strip():
        logger.error("输入文本为空")
        return None

    client = OpenAI(
        base_url=ARK_BASE_URL,
        api_key=ARK_API_KEY,
    )

    final_prompt = PROMPT_TEMPLATE.replace("{{RAW_TEXT}}", raw_text)

    try:
        completion = client.chat.completions.create(
            model=ARK_MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a helpful assistant specialized in JSON formatting."},
                {"role": "user", "content": final_prompt},
            ],
        )
        content = completion.choices[0].message.content
        logger.info("LLM 调用成功")
        logger.info(f"LLM 原始返回: {content}")
        return content
    except Exception as e:
        logger.error(f"LLM 调用失败: {str(e)}")
        return None

def parse_llm_json(llm_output):
    """解析 LLM 返回的 JSON 字符串（处理 Markdown 代码块）"""
    try:
        # 移除可能的 markdown 代码块标记
        clean_json = llm_output.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.startswith("```"):
            clean_json = clean_json[3:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        
        data = json.loads(clean_json)
        # 简单验证字段
        if "front" not in data or "back" not in data:
            raise ValueError("JSON 缺少 front 或 back 字段")
        
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"数据格式错误: {str(e)}")
        return None

def check_card_exists(front_word):
    """查询单词是否已存在于指定 Deck"""
    # 注意：Anki 查询语法 deck:"Name" front:"Word"
    # 使用双引号包裹以防空格
    query = f'deck:"{ANKI_DECK}" "front:{front_word}"'
    try:
        notes = invoke_anki("findNotes", query=query)
        exists = len(notes) > 0
        logger.info(f"查询单词 '{front_word}' 是否存在: {'是' if exists else '否'} (IDs: {notes})")
        return exists
    except Exception as e:
        logger.error(f"查询笔记失败: {str(e)}")
        return False # 假定不存在以防止逻辑中断，或者根据需求抛出

def add_note_to_anki(front, back):
    """向 Anki 插入新笔记"""
    note = {
        "deckName": ANKI_DECK,
        "modelName": ANKI_MODEL,
        "fields": {
            "Front": front,
            "Back": back
        },
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck"
        },
        "tags": ["auto-imported"]
    }
    
    try:
        note_id = invoke_anki("addNote", note=note)
        logger.info(f"笔记插入成功，ID: {note_id}")
        return True
    except Exception as e:
        logger.error(f"笔记插入失败: {str(e)}")
        return False

def process_vocabulary(raw_input_text):
    """
    主处理函数：对外暴露的接口
    """
    logger.info("=" * 50)
    logger.info("开始处理新输入")
    logger.info(f"Raw Input: {raw_input_text[:100]}..." if len(raw_input_text) > 100 else f"Raw Input: {raw_input_text}")

    # 0. 环境检查 (每次执行都检查)
    if not check_environment():
        logger.error("环境检查未通过，终止操作。")
        return

    # 1. 调用 LLM
    llm_result = call_llm(raw_input_text)
    if not llm_result:
        logger.error("LLM 未返回有效结果，终止操作。")
        return

    # 2. 解析 JSON
    card_data = parse_llm_json(llm_result)
    if not card_data:
        logger.error("无法解析 LLM 结果为 JSON，终止操作。")
        return

    front_word = card_data['front']
    back_html = card_data['back']

    # 3. 检查是否存在
    if check_card_exists(front_word):
        logger.info(f"单词 '{front_word}' 已存在于 Deck '{ANKI_DECK}' 中。跳过插入。")
        return
    else:
        logger.info(f"单词 '{front_word}' 不存在，准备插入。")

    # 4. 插入 Anki
    success = add_note_to_anki(front_word, back_html)
    if success:
        logger.info(f"流程结束: '{front_word}' 处理成功。")
    else:
        logger.error(f"流程结束: '{front_word}' 插入失败。")

# --- 使用示例 ---
if __name__ == "__main__":
    # 模拟从网页复制的文本
    sample_text = """
heretical
Share
/həˈrɛtɪkəl/
IPA guide
Other forms: heretically

Something that departs from normally held beliefs (especially religious, political, or social norms) is heretical. If your family is resistant to change, they may consider your idea of making pancakes for dinner to be completely heretical.

Heretical is the adjective form of the noun heretic, which comes from the Greek word hairetikos, meaning able to choose. What is considered a heretical point of view can change over time. Examples of positions that were once considered heretical but are now accepted as facts include: the Earth is round, the Earth circles the Sun, and a little bit of chocolate is actually good for you.

Definitions of heretical
adjective characterized by departure from accepted beliefs or standards
synonyms:dissident, heterodox
unorthodox
breaking with convention or tradition
    """
    
    process_vocabulary(sample_text)