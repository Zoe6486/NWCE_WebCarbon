import os
import sys
import json
import csv
import requests
import time
import re
import subprocess
from bs4 import BeautifulSoup
import shutil
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import ROOT_DIR, CSS_OPTI_DIR, API_BASE_URL, API_KEY

# --- 配置区域 ---
# API_BASE_URL = "https://api.chatanywhere.org/v1"
# API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = "gpt-4o-mini"
API_CALL_DELAY_SECONDS = 5

# --- 动态获取项目名称 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python css_get_llm_suggestions.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

# --- 目录配置 ---
SOURCE_DIR = CSS_OPTI_DIR / "css_original" / PROJECT_NAME
SUGGESTIONS_DIR = CSS_OPTI_DIR / "css_llm_suggestions" / PROJECT_NAME
SUGGESTIONS_FILE_PATH = SUGGESTIONS_DIR / f"css_suggestions.json"
CSV_REPORT_FILE_PATH = SUGGESTIONS_DIR / f"css_suggestions_summary.csv"

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

# --- 辅助函数：使用 postcss 提取 CSS 文件统计信息和规则 ---
def get_css_stats_and_rules(css_content):
    stats = {
        "line_count": css_content.count('\n') + 1,
        "size_kb": round(len(css_content.encode('utf-8')) / 1024, 2),
        "selectors": [],
        "rules": {},
        "rules_count": 0,
        "selector_depths": [],
        "duplicate_properties": {},
        "approx_rule_count": 0,
        "approx_selector_count": 0,
        "avg_selector_depth": 0.0
    }

    # 写入临时 CSS 文件到根目录
    temp_css_path = os.path.join(ROOT_DIR, "temp.css")
    with open(temp_css_path, "w", encoding="utf-8") as f:
        f.write(css_content)

    # 使用 postcss 解析 CSS 文件
    postcss_script = """
    const postcss = require('postcss');
    const fs = require('fs');

    const css = fs.readFileSync('temp.css', 'utf8');

    try {
        const result = postcss.parse(css, { from: 'temp.css' });
        const rules = [];
        result.walkRules(rule => {
            const selectors = rule.selector;
            const declarations = rule.nodes
                .filter(node => node.type === 'decl')
                .map(decl => `${decl.prop}: ${decl.value}`)
                .join('; ');
            rules.push({ selector: selectors, declarations: declarations });
        });
        console.log(JSON.stringify(rules));
    } catch (err) {
        console.error('PostCSS Error:', err.message);
        process.exit(1);
    }
    """

    # 写入临时 Node.js 脚本到根目录
    temp_js_path = os.path.join(ROOT_DIR, "temp_postcss.js")
    with open(temp_js_path, "w", encoding="utf-8") as f:
        f.write(postcss_script)

    # 检查 Node.js 是否可用
    if shutil.which("node") is None:
        print("  错误：Node.js 未找到，请确保 Node.js 已安装并配置在 PATH 中。")
        return stats

    # 调用 Node.js 运行 postcss 解析，使用根目录作为工作目录
    try:
        result = subprocess.run(
            ["node", temp_js_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=ROOT_DIR  # 确保工作目录为根目录
        )
        if result.returncode != 0:
            print(f"  错误：PostCSS 解析失败: {result.stderr}")
            return stats

        rules_data = json.loads(result.stdout)
        for rule in rules_data:
            selector_text = rule["selector"]
            declaration_block = rule["declarations"]
            stats["selectors"].append(selector_text)
            stats["rules"][selector_text] = declaration_block
            stats["rules_count"] += 1

            depth = selector_text.count(' ') + selector_text.count('>') + selector_text.count('.')
            stats["selector_depths"].append(depth)

            properties = [prop.split(':')[0].strip() for prop in declaration_block.split(';') if prop]
            prop_counts = {}
            for prop in properties:
                prop_counts[prop] = prop_counts.get(prop, 0) + 1
            for prop, count in prop_counts.items():
                if count > 1:
                    stats["duplicate_properties"][prop] = count

        stats["approx_rule_count"] = stats["rules_count"]
        stats["approx_selector_count"] = len(stats["selectors"])
        stats["avg_selector_depth"] = round(sum(stats["selector_depths"]) / len(stats["selector_depths"]) if stats["selector_depths"] else 0, 2)

    except subprocess.CalledProcessError as e:
        print(f"  错误：PostCSS 解析失败: {e.stderr}")
    except FileNotFoundError:
        print("  错误：Node.js 或相关模块未找到，请确保 Node.js 和 postcss 已安装。")
    except Exception as e:
        print(f"  错误：调用 PostCSS 时发生未知错误: {e}")
    finally:
        # 清理临时文件
        for file in [temp_css_path, temp_js_path]:
            if os.path.exists(file):
                os.remove(file)

    return stats

# --- LLM 调用函数 ---
def get_css_optimization_suggestion(css_filename, css_content, html_classes_and_ids=None):
    stats = get_css_stats_and_rules(css_content)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    user_prompt_for_css = f"""
    You are a professional front-end engineer specializing in CSS optimization for static websites. Your task is to analyze a CSS file and provide comprehensive, actionable, and safe optimization suggestions to reduce file size, improve rendering performance, and enhance maintainability, while preserving functionality and layout.

    ### CSS File Context
    - **Filename**: {css_filename}
    - **CSS Statistics**:
      - Line count: {stats['line_count']}
      - Rule count: {stats['approx_rule_count']}
      - Selector count: {stats['approx_selector_count']}
      - Average selector depth: {stats['avg_selector_depth']}
      - File size (KB): {stats['size_kb']}
      - Duplicate properties: {json.dumps(stats['duplicate_properties'])}
    - **All Selectors and Rules**:
      ```css
      {json.dumps(stats['rules'], indent=2)}
      ```

    ### HTML Context
    - **Classes found in HTML**: {json.dumps(html_classes_and_ids['classes'] if html_classes_and_ids else 'Not provided')}
    - **IDs found in HTML**: {json.dumps(html_classes_and_ids['ids'] if html_classes_and_ids else 'Not provided')}

    ### Optimization Goals
    Provide suggestions focusing on the following areas, ordered by priority:
    1. **Remove Unused Styles**:
       - Identify CSS rules or selectors that are definitely unused by comparing with the provided HTML classes and IDs.
       - Consider nested selectors (e.g., '.parent .child') and check if the parent and child classes exist in HTML context.
       - Flag selectors with medium confidence if they might be used by JavaScript.
    2. **Consolidate Duplicate Styles**:
       - Find identical or very similar rule sets applied to different selectors and suggest merging them.
    3. **Use Shorthand Properties**:
       - Where multiple longhand properties are used (e.g., `margin-top`, `margin-right`), suggest using shorthand (e.g., `margin`).
    4. **Optimize Selectors**:
       - Suggest improvements for overly complex or inefficient selectors (e.g., `div#main ul li a` might be simplified).
    5. **Remove Redundant Units or Values**:
       - E.g., `0px` can be `0`, `color: #aabbcc` can be `color: #abc`.
    6. **Identify Overrides**:
       - Point out rules that are immediately overridden by subsequent rules within the same selector block or cascade.

    ### Constraints
    - Use the provided HTML classes and IDs to determine unused styles. If a class or ID in the CSS does not appear in the HTML, it is likely unused, but flag it with medium confidence unless it's a clear anti-pattern.
    - Do NOT suggest removing styles if they might be used by JavaScript unless they are clearly redundant.
    - Prioritize safe changes. Flag risky changes as requiring careful testing.
    - The goal is to provide suggestions that can be applied (semi-)automatically or reviewed by a human.

    ### Output Format
    Return your suggestions in a structured JSON format:
    {{
      "suggestions_for_file": "{css_filename}",
      "optimizations": [
        {{
          "type": "string", // e.g., "remove_unused_style", "consolidate_duplicate_style"
          "original_selector_or_property": "string",
          "original_declaration_block_snippet": "string",
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
            {"role": "system", "content": "You are a professional front-end engineer specializing in CSS optimization. Provide concise, actionable, and safe advice in structured JSON format."},
            {"role": "user", "content": user_prompt_for_css}
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    print(f"  [LLM] 正在为 CSS 文件 {css_filename} 获取优化建议 (Model: {LLM_MODEL}, Temp: {data['temperature']})...")
    llm_call_log = {
        "status": "api_call_pending",
        "request_payload_summary": {"model": data["model"], "css_filename": css_filename, "temperature": data["temperature"], "system_message_used": data["messages"][0]["content"]},
        "suggestion_data": None,
        "raw_api_response_text": None,
        "error_details": None
    }

    # 如果 CSS 解析失败，跳过 LLM 调用
    if stats["rules_count"] == 0:
        print("  警告：CSS 解析失败，跳过 LLM 调用。")
        llm_call_log["status"] = "skipped_due_to_css_parse_failure"
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
        print(f"错误：源目录 '{SOURCE_DIR}' 不存在。请先运行 'css_extract.py'。")
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
        print(f"警告：未找到 HTML 文件 '{html_path}'，将仅基于 CSS 文件进行分析。")

    os.makedirs(SUGGESTIONS_DIR, exist_ok=True)

    all_files_suggestions_log = []

    print(f"\n开始为项目 '{PROJECT_NAME}' 的 CSS 文件生成优化建议...")
    print(f"CSS 和 HTML 文件来源目录: {SOURCE_DIR}")
    print(f"建议将保存至: {SUGGESTIONS_FILE_PATH}")

    css_files = [f for f in os.listdir(SOURCE_DIR) if f.lower().endswith(".css")]

    if not css_files:
        print(f"在目录 '{SOURCE_DIR}' 中没有找到 CSS 文件。")
        with open(SUGGESTIONS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(all_files_suggestions_log, f, indent=4, ensure_ascii=False)
        print(f"已保存空的 CSS 建议文件到: {SUGGESTIONS_FILE_PATH}")
        return

    for css_filename in css_files:
        css_file_path = os.path.join(SOURCE_DIR, css_filename)
        print(f"\n处理 CSS 文件: {css_filename}")
        
        file_log_entry = {
            "project_name": PROJECT_NAME,
            "css_filename": css_filename,
            "llm_api_call_details": None
        }

        try:
            with open(css_file_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            
            if not css_content.strip():
                print(f"  CSS 文件 '{css_filename}' 为空，跳过 LLM 调用。")
                file_log_entry["llm_api_call_details"] = {"status": "skipped_empty_css"}
            else:
                api_call_result = get_css_optimization_suggestion(css_filename, css_content, html_classes_and_ids)
                file_log_entry["llm_api_call_details"] = api_call_result
                if api_call_result["status"] in ["success", "success_from_markdown"]:
                    suggestion_data = api_call_result.get("suggestion_data", {})
                else:
                    suggestion_data = None  # 明确设置为空，避免后续错误

        except Exception as e:
            print(f"  读取或处理 CSS 文件 '{css_filename}' 时发生错误: {e}")
            file_log_entry["llm_api_call_details"] = {"status": "error_reading_css", "error_details": str(e)}
        
        all_files_suggestions_log.append(file_log_entry)

    try:
        with open(SUGGESTIONS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(all_files_suggestions_log, f, indent=4, ensure_ascii=False)
        print(f"\n所有 CSS 文件的优化建议（及调用日志）已收集并保存到: {SUGGESTIONS_FILE_PATH}")

        # 生成 CSV 报告
        csv_data = [["Type", "Selector/Property", "Original Code", "Suggested Action", "Reason", "Priority", "Confidence"]]
        for entry in all_files_suggestions_log:
            llm_details = entry.get("llm_api_call_details", {})
            suggestion_data = llm_details.get("suggestion_data", {})
            if suggestion_data and "optimizations" in suggestion_data:  # 仅当 suggestion_data 存在且包含 optimizations 时处理
                optimizations = suggestion_data.get("optimizations", [])
                for opt in optimizations:
                    csv_data.append([
                        opt.get("type", ""),
                        opt.get("original_selector_or_property", ""),
                        opt.get("original_declaration_block_snippet", ""),
                        opt.get("suggested_change_or_action", ""),
                        opt.get("reason", ""),
                        opt.get("priority", ""),
                        opt.get("confidence", "")
                    ])
        
        # 如果没有任何建议，添加一行提示
        if len(csv_data) == 1:
            csv_data.append(["No suggestions", "", "", "", "", "", ""])

        with open(CSV_REPORT_FILE_PATH, 'w', newline='', encoding='utf-8') as f_csv:
            writer = csv.writer(f_csv)
            writer.writerows(csv_data)
        print(f"CSS 建议报告已保存到: {CSV_REPORT_FILE_PATH}")

    except IOError as e:
        print(f"错误：无法写入 CSS 建议文件 '{SUGGESTIONS_FILE_PATH}' 或 CSV 报告: {e}")

if __name__ == "__main__":
    try:
        import bs4
    except ImportError:
        print("错误：缺少依赖库。请运行 'pip install beautifulsoup4'")
        sys.exit(1)
    main()