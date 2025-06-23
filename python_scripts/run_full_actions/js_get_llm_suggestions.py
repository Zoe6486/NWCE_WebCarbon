import os
import sys
import json
import requests
import time
import re
import csv
from bs4 import BeautifulSoup
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import FULL_OPTI_DIR, API_BASE_URL, API_KEY

# --- 配置区域 ---
# API_BASE_URL = "https://api.chatanywhere.org/v1"
# # API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = "gpt-4o-mini"
API_CALL_DELAY_SECONDS = 5

# --- 动态获取项目名称 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python js_get_llm_suggestions.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

# --- 目录配置 ---
SOURCE_TEMP_DIR= FULL_OPTI_DIR / "temp" /PROJECT_NAME/ "js"

SOURCE_DIR = SOURCE_TEMP_DIR / "js_original"
SUGGESTIONS_DIR = SOURCE_TEMP_DIR / "js_llm_suggestions"

SUGGESTIONS_FILE_PATH = os.path.join(SUGGESTIONS_DIR, f"js_suggestions.json")
CSV_SUGGESTIONS_FILE_PATH = os.path.join(SUGGESTIONS_DIR, f"js_suggestions_summary.csv")

# --- 辅助函数：提取 HTML 中的类和 ID ---
def extract_html_classes_and_ids(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    classes = set()
    ids = set()

    for tag in soup.find_all():
        class_list = tag.get('class', [])
        if isinstance(class_list, str):
            class_list = class_list.split()
        classes.update(class_list)
        tag_id = tag.get('id', None)
        if tag_id:
            ids.add(tag_id)

    return {"classes": list(classes), "ids": list(ids)}

# --- 辅助函数：统计 JS 文件信息 ---
def get_js_stats(js_content):
    stats = {
        "line_count": js_content.count('\n') + 1,
        "function_count": len(re.findall(r'function\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(', js_content)),
        "variable_count": len(re.findall(r'var|let|const\s+[a-zA-Z_][a-zA-Z0-9_]*', js_content)),
        "size_kb": round(len(js_content.encode('utf-8')) / 1024, 2)
    }
    return stats

# --- LLM 调用函数 ---
def get_js_optimization_suggestion(js_filename, js_content, html_classes_and_ids=None):
    stats = get_js_stats(js_content)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    user_prompt_for_js = f"""
    You are a professional JavaScript developer specializing in optimizing JS files for static websites. Your task is to analyze a JS file and provide comprehensive, actionable, and safe optimization suggestions to reduce file size, improve execution performance, and enhance maintainability, while preserving functionality.

    ### JS File Context
    - **Filename**: {js_filename}
    - **JS Statistics**:
      - Line count: {stats['line_count']}
      - Function count: {stats['function_count']}
      - Variable count: {stats['variable_count']}
      - File size (KB): {stats['size_kb']}
    - **First 500 characters of JS**:
      ```
      {js_content[:500]}
      ```

    ### HTML Context
    - **Classes found in HTML**: {json.dumps(html_classes_and_ids['classes'] if html_classes_and_ids else 'Not provided')}
    - **IDs found in HTML**: {json.dumps(html_classes_and_ids['ids'] if html_classes_and_ids else 'Not provided')}

    ### Optimization Goals
    Provide suggestions focusing on the following areas, ordered by priority:
    1. **Remove Unused Variables and Functions**:
       - Identify variables or functions that are defined but never used.
       - Consider potential usage by event listeners or external scripts, flag with medium confidence if unsure.
    2. **Minimize Redundant Code**:
       - Suggest removing duplicate code blocks or consolidating repeated logic.
    3. **Optimize Loops and Conditionals**:
       - Suggest improvements for inefficient loops (e.g., replace `for` with `forEach` where applicable) or redundant conditionals.
    4. **Reduce DOM Operations**:
       - Identify and suggest batching DOM manipulations or caching DOM queries.
    5. **Remove Comments**:
       - Suggest removing all comments unless critical for documentation.

    ### Constraints
    - Use HTML classes and IDs to determine potential usage by event listeners or DOM manipulation.
    - Do NOT suggest removing code if it might be used by external scripts or event handlers unless clearly redundant.
    - Prioritize safe changes. Flag risky changes as requiring careful testing.

    ### Output Format
    Return your suggestions in a structured JSON format:
    {{
      "suggestions_for_file": "{js_filename}",
      "optimizations": [
        {{
          "type": "string", // e.g., "remove_unused_variable", "minimize_redundant_code"
          "original_code_snippet": "string",
          "suggested_change_or_action": "string",
          "reason": "string",
          "priority": "high|medium|low",
          "confidence": "high|medium|low"
        }}
      ]
    }}
    If no optimizations are found, return an empty "optimizations" list.
    """

    data = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a professional JavaScript developer specializing in JS optimization. Provide concise, actionable, and safe advice in structured JSON format."},
            {"role": "user", "content": user_prompt_for_js}
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    print(f"  [LLM] 正在为 JS 文件 {js_filename} 获取优化建议 (Model: {LLM_MODEL}, Temp: {data['temperature']})...")
    llm_call_log = {
        "status": "api_call_pending",
        "request_payload_summary": {"model": data["model"], "js_filename": js_filename, "temperature": data["temperature"], "system_message_used": data["messages"][0]["content"]},
        "suggestion_data": None,
        "raw_api_response_text": None,
        "error_details": None
    }

    if stats["function_count"] == 0 and stats["variable_count"] == 0:
        print("  警告：JS 文件无有效函数或变量，跳过 LLM 调用。")
        llm_call_log["status"] = "skipped_empty_js"
        return llm_call_log

    try:
        print(f"    等待 {API_CALL_DELAY_SECONDS} 秒后调用 API...")
        time.sleep(API_CALL_DELAY_SECONDS)
        response = requests.post(f"{API_BASE_URL}/chat/completions", headers=headers, data=json.dumps(data), timeout=120)
        llm_call_log["raw_api_response_text"] = response.text
        response.raise_for_status()
        
        response_json = response.json()
        assistant_response_content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not assistant_response_content:
            print(f"    [LLM Error] 模型返回了空的建议内容。")
            llm_call_log["status"] = "llm_empty_content"
            return llm_call_log

        try:
            suggestion = json.loads(assistant_response_content)
            print(f"    [LLM Success] 成功获取并解析建议。")
            llm_call_log["status"] = "success"
            llm_call_log["suggestion_data"] = suggestion
            return llm_call_log
        except json.JSONDecodeError as e:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", assistant_response_content)
            if match:
                try:
                    suggestion = json.loads(match.group(1))
                    print(f"    [LLM Success] 成功从 Markdown 代码块中提取并解析建议。")
                    llm_call_log["status"] = "success_from_markdown"
                    llm_call_log["suggestion_data"] = suggestion
                    return llm_call_log
                except json.JSONDecodeError:
                    pass 
            print(f"    [LLM Error] 无法解析模型返回的 JSON 建议: {assistant_response_content}, 错误: {e}")
            llm_call_log["status"] = "llm_json_decode_error"
            llm_call_log["raw_suggestion_text"] = assistant_response_content
            return llm_call_log

    except requests.exceptions.HTTPError as http_err:
        error_details = f"HTTP 错误: {http_err}"
        if hasattr(http_err, 'response') and http_err.response is not None:
            error_details += f", 状态码: {http_err.response.status_code}"
        print(f"    [API Error] {error_details}")
        llm_call_log["status"] = "api_http_error"
        llm_call_log["error_details"] = error_details
        return llm_call_log
    except requests.exceptions.Timeout:
        print(f"    [API Error] 请求超时。")
        llm_call_log["status"] = "api_timeout"
        return llm_call_log
    except Exception as e:
        print(f"    [Error] 调用 LLM 时发生未知错误: {e}")
        llm_call_log["status"] = "unknown_error_in_llm_call"
        llm_call_log["error_details"] = str(e)
        return llm_call_log

# --- 主逻辑 ---
def main():
    if not os.path.exists(SOURCE_DIR):
        print(f"错误：源目录 '{SOURCE_DIR}' 不存在。请先运行 'js_extract.py'。")
        return
    
    html_path = os.path.join(SOURCE_DIR, "index.html")
    html_classes_and_ids = None
    if os.path.exists(html_path):
        print(f"找到 HTML 文件: {html_path}")
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            html_classes_and_ids = extract_html_classes_and_ids(html_content)
            print(f"成功提取 HTML 中的类和 ID: {html_classes_and_ids}")
        except Exception as e:
            print(f"警告：无法读取或解析 HTML 文件 '{html_path}': {e}")
    else:
        print(f"警告：未找到 HTML 文件 '{html_path}'，将仅基于 JS 文件进行分析。")

    os.makedirs(SUGGESTIONS_DIR, exist_ok=True)

    all_files_suggestions_log = []

    print(f"\n开始为项目 '{PROJECT_NAME}' 的 JS 文件生成优化建议...")
    print(f"JS 和 HTML 文件来源目录: {SOURCE_DIR}")
    print(f"建议将保存至: {SUGGESTIONS_FILE_PATH}")

    js_files = [f for f in os.listdir(SOURCE_DIR) if f.lower().endswith(".js")]

    if not js_files:
        print(f"在目录 '{SOURCE_DIR}' 中没有找到 JS 文件。")
        with open(SUGGESTIONS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(all_files_suggestions_log, f, indent=4, ensure_ascii=False)
        print(f"已保存空的 JS 建议文件到: {SUGGESTIONS_FILE_PATH}")
        return

    for js_filename in js_files:
        js_file_path = os.path.join(SOURCE_DIR, js_filename)
        print(f"\n处理 JS 文件: {js_filename}")
        
        file_log_entry = {
            "project_name": PROJECT_NAME,
            "js_filename": js_filename,
            "llm_api_call_details": None
        }

        try:
            with open(js_file_path, 'r', encoding='utf-8') as f:
                js_content = f.read()
            
            if not js_content.strip():
                print(f"  JS 文件 '{js_filename}' 为空，跳过 LLM 调用。")
                file_log_entry["llm_api_call_details"] = {"status": "skipped_empty_js"}
            else:
                api_call_result = get_js_optimization_suggestion(js_filename, js_content, html_classes_and_ids)
                file_log_entry["llm_api_call_details"] = api_call_result
        
        except Exception as e:
            print(f"  读取或处理 JS 文件 '{js_filename}' 时发生错误: {e}")
            file_log_entry["llm_api_call_details"] = {"status": "error_reading_js", "error_details": str(e)}
        
        all_files_suggestions_log.append(file_log_entry)

    try:
        with open(SUGGESTIONS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(all_files_suggestions_log, f, indent=4, ensure_ascii=False)
        print(f"\n所有 JS 文件的优化建议（及调用日志）已收集并保存到: {SUGGESTIONS_FILE_PATH}")

        # 生成 CSV 报告
        csv_data = [["Type", "Original Code Snippet", "Suggested Action", "Reason", "Priority", "Confidence"]]
        for entry in all_files_suggestions_log:
            llm_details = entry.get("llm_api_call_details", {})
            suggestion_data = llm_details.get("suggestion_data", {})
            optimizations = suggestion_data.get("optimizations", [])
            if not optimizations:
                csv_data.append(["N/A", "No optimizations", "N/A", "No suggestions available", "N/A", "N/A"])
            else:
                for opt in optimizations:
                    csv_data.append([
                        opt.get("type", "N/A"),
                        opt.get("original_code_snippet", "N/A"),
                        opt.get("suggested_change_or_action", "N/A"),
                        opt.get("reason", "N/A"),
                        opt.get("priority", "N/A"),
                        opt.get("confidence", "N/A")
                    ])

        with open(CSV_SUGGESTIONS_FILE_PATH, 'w', newline='', encoding='utf-8') as f_csv:
            writer = csv.writer(f_csv)
            writer.writerows(csv_data)
        print(f"JS 建议 CSV 已保存到: {CSV_SUGGESTIONS_FILE_PATH}")
    except IOError as e:
        print(f"错误：无法写入 JS 建议文件 '{SUGGESTIONS_FILE_PATH}' 或 CSV 文件: {e}")

if __name__ == "__main__":
    try:
        import bs4
    except ImportError:
        print("错误：缺少依赖库。请运行 'pip install beautifulsoup4'")
        sys.exit(1)
    main()