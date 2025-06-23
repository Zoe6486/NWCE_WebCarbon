import os
import sys
import json
import csv
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from openai import OpenAI  # 引入 OpenAI 的官方 Python SDK

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 现在可以正常导入 paths 模块
from paths import HTML_OPTI_DIR, API_BASE_URL, API_KEY

# --- 配置区域 ---
# 使用 OpenAI 官方 API 端点
# API_BASE_URL = "https://api.openai.com/v1"  
# API_KEY = os.getenv("OPENAI_API_KEY")


# 使用 chatanywhere 端点
# API_BASE_URL = "https://api.chatanywhere.org/v1"  # 请替换为实际有效的 API 端点
# API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = "gpt-4o-mini"

if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python html_suggestions.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

SOURCE_DIR = HTML_OPTI_DIR / "html_original" / PROJECT_NAME
RESULT_DIR = HTML_OPTI_DIR / "html_llm_suggestions" / PROJECT_NAME
SUGGESTIONS_FILE = RESULT_DIR / "html_optimization_suggestions.json"
CSV_REPORT_FILE = RESULT_DIR / "html_suggestions_summary.csv"

# --- 辅助函数：提取 HTML 统计信息 ---
def get_html_stats(html_content):
    """
    提取 HTML 文件的统计信息，提供给 LLM 作为上下文。
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 统计标签数量
    total_tags = len(soup.find_all())
    
    # 统计注释数量
    comments = len(soup.find_all(string=lambda string: isinstance(string, str) and string.strip().startswith('<!--')))
    
    # 统计嵌套深度
    def get_max_depth(element, current_depth=0):
        children = [child for child in element.children if hasattr(child, 'children')]
        if not children:
            return current_depth
        return max(get_max_depth(child, current_depth + 1) for child in children)
    
    max_depth = get_max_depth(soup)
    
    # 统计空标签
    empty_tags = len([tag for tag in soup.find_all() if not tag.contents and not tag.string and tag.name not in ['br', 'hr', 'img', 'input']])
    
    # 提取关键部分（例如 <head> 和 <body> 的前 200 字符）
    head_snippet = str(soup.head)[:200] if soup.head else "No <head> tag"
    body_snippet = str(soup.body)[:200] if soup.body else "No <body> tag"
    
    return {
        "total_tags": total_tags,
        "comment_count": comments,
        "max_nesting_depth": max_depth,
        "empty_tag_count": empty_tags,
        "head_snippet": head_snippet,
        "body_snippet": body_snippet
    }

# --- LLM 调用函数 ---
def get_html_optimization_suggestion(html_content):
    """
    调用 LLM 获取 HTML 优化建议，返回结构化的 JSON 格式。
    """
    # 提取 HTML 统计信息
    stats = get_html_stats(html_content)
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
    You are a professional front-end engineer specializing in HTML optimization for static websites. Your task is to analyze an HTML file and provide comprehensive, actionable, and safe optimization suggestions to reduce file size, improve loading performance, and enhance maintainability while preserving functionality, layout, and accessibility.

    ### HTML Context
    - **First 500 characters of HTML**:
      ```
      {html_content[:500]}
      ```
    - **HTML Statistics**:
      - Total number of tags: {stats['total_tags']}
      - Number of comments: {stats['comment_count']}
      - Maximum nesting depth: {stats['max_nesting_depth']}
      - Number of empty tags: {stats['empty_tag_count']}
      - Head snippet (first 200 characters): `{stats['head_snippet']}`
      - Body snippet (first 200 characters): `{stats['body_snippet']}`

    ### Optimization Goals
    Provide suggestions focusing on the following areas, ordered by priority:
    1. **Remove Redundant Tags**:
       - Identify empty or purposeless tags (e.g., <div> or <span> with no content, styling, or functionality).
       - Avoid removing tags that may have event listeners or are required for JavaScript functionality.
    2. **Remove HTML Comments**:
       - Suggest removing all HTML comments unless they are critical for debugging or documentation (e.g., comments marking conditional sections for legacy browsers).
    3. **Simplify Nested Structures**:
       - Identify and suggest unwrapping or merging unnecessarily nested structures (e.g., <div><div>content</div></div> can become <div>content</div> if the outer div has no purpose).
       - Prioritize reducing nesting depth where it exceeds 5 levels.
    4. **Remove Unused Attributes**:
       - Identify and suggest removing empty or unused attributes (e.g., class="", id="", style="").
       - Ensure attributes like 'alt' on images or 'aria-' attributes are preserved for accessibility.
    5. **Replace Tags for Semantics**:
       - Suggest replacing generic tags (e.g., <div>) with semantic HTML5 tags (e.g., <section>, <article>, <main>) where appropriate.
       - Ensure replacements do not break CSS or JavaScript functionality.

    ### Constraints
    - Do not suggest changes that could break the layout, functionality, or accessibility of the website.
    - Do not remove tags or attributes that might be used by JavaScript (e.g., tags with event listeners or specific IDs/classes).
    - Prioritize suggestions that have the most significant impact on file size or performance.

    ### Output Format
    Return your suggestions in a structured JSON format with the following structure:
    {{
      "remove_comments": boolean, // whether to remove all HTML comments
      "remove_redundant_tags": [
        {{
          "tag": "string", // e.g., "div", "span"
          "selector": "string", // CSS selector to identify the tag, e.g., "div#some-id", "div.empty-class"
          "reason": "string", // e.g., "empty tag", "no styling or functionality"
          "priority": "high|medium|low" // priority of this suggestion
        }}
      ],
      "simplify_nested_structures": [
        {{
          "selector": "string", // CSS selector for the parent tag
          "action": "string", // e.g., "unwrap", "merge"
          "reason": "string", // e.g., "unnecessary nesting"
          "priority": "high|medium|low"
        }}
      ],
      "remove_unused_attributes": [
        {{
          "tag": "string", // e.g., "div", "span"
          "selector": "string", // CSS selector
          "attribute": "string", // e.g., "class", "id", "style"
          "reason": "string", // e.g., "empty class", "unused id"
          "priority": "high|medium|low"
        }}
      ],
      "replace_tags": [
        {{
          "selector": "string", // CSS selector
          "original_tag": "string", // e.g., "div"
          "new_tag": "string", // e.g., "section"
          "reason": "string", // e.g., "semantic improvement"
          "priority": "high|medium|low"
        }}
      ]
    }}

    ### Example Response
    {{
      "remove_comments": true,
      "remove_redundant_tags": [
        {{"tag": "div", "selector": "div#empty-div", "reason": "empty tag with no purpose", "priority": "high"}},
        {{"tag": "span", "selector": "span.no-content", "reason": "span with no content or styling", "priority": "medium"}}
      ],
      "simplify_nested_structures": [
        {{"selector": "div.wrapper", "action": "unwrap", "reason": "unnecessary nesting, depth reduced from 6 to 5", "priority": "high"}},
        {{"selector": "div.inner-container", "action": "merge", "reason": "can merge with parent div", "priority": "medium"}}
      ],
      "remove_unused_attributes": [
        {{"tag": "span", "selector": "span.some-class", "attribute": "class", "reason": "empty class", "priority": "medium"}},
        {{"tag": "div", "selector": "div#unused-id", "attribute": "id", "reason": "id not referenced in CSS or JS", "priority": "low"}}
      ],
      "replace_tags": [
        {{"selector": "div.main-content", "original_tag": "div", "new_tag": "main", "reason": "semantic improvement for better SEO", "priority": "high"}},
        {{"selector": "div.article-section", "original_tag": "div", "new_tag": "article", "reason": "semantic improvement", "priority": "medium"}}
      ]
    }}

    Provide your suggestions in the above JSON format, ensuring each suggestion is actionable, safe, and prioritized based on its impact.
    """

    data = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a professional front-end engineer specializing in HTML optimization. Provide concise, actionable, and safe advice in JSON format."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    print(f"\n[LLM] 正在为 HTML 文件获取优化建议...")

    try:
        response = requests.post(f"{API_BASE_URL}/chat/completions", headers=headers, data=json.dumps(data), timeout=60)
        response.raise_for_status()
        
        response_json = response.json()
        assistant_response_content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not assistant_response_content:
            print(f"[LLM Error] 模型返回了空的建议内容。")
            return None

        try:
            suggestion = json.loads(assistant_response_content)
            print(f"[LLM Success] 成功获取并解析建议: {suggestion}")
            return suggestion
        except json.JSONDecodeError as e:
            print(f"[LLM Error] 无法解析模型返回的JSON建议: {assistant_response_content}, 错误: {e}")
            return None
        except ValueError as e:
            print(f"[LLM Error] 模型返回的建议格式不正确: {e}")
            return None

    except requests.exceptions.HTTPError as http_err:
        print(f"[API Error] HTTP错误: {http_err}")
        print(f"           响应状态码: {response.status_code}")
        print(f"           响应内容: {response.text}")
    except requests.exceptions.Timeout:
        print(f"[API Error] 请求超时。")
    except requests.exceptions.RequestException as req_err:
        print(f"[API Error] 请求错误: {req_err}")
    except Exception as e:
        print(f"[Error] 调用LLM时发生未知错误: {e}")
    return None

# --- 主逻辑 ---
def main():
    """
    从提取的 HTML 文件获取 LLM 优化建议并保存。
    """
    if not os.path.exists(SOURCE_DIR):
        print(f"错误：源目录 '{SOURCE_DIR}' 不存在。")
        return

    html_path = SOURCE_DIR / "index.html"
    if not os.path.exists(html_path):
        print(f"错误：HTML 文件 '{html_path}' 不存在。")
        return

    # 读取 HTML 文件
    with open(html_path, 'r', encoding='utf-8') as file:
        html_content = file.read()

    # 获取 LLM 建议
    suggestion = get_html_optimization_suggestion(html_content)

    # 保存建议
    os.makedirs(RESULT_DIR, exist_ok=True)
    with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(suggestion if suggestion else {"error": "未能获取优化建议"}, f, indent=4, ensure_ascii=False)
    print(f"优化建议已保存到 {SUGGESTIONS_FILE}")

    # 生成 CSV 报告
    if suggestion and "error" not in suggestion:
        csv_data = [["Category", "Selector", "Tag", "Action/Attribute/New Tag", "Reason", "Priority"]]
        
        # 处理 remove_redundant_tags
        for item in suggestion.get("remove_redundant_tags", []):
            csv_data.append([
                "remove_redundant_tags",
                item.get("selector", ""),
                item.get("tag", ""),
                "remove",
                item.get("reason", ""),
                item.get("priority", "")
            ])
        
        # 处理 simplify_nested_structures
        for item in suggestion.get("simplify_nested_structures", []):
            csv_data.append([
                "simplify_nested_structures",
                item.get("selector", ""),
                "",  # Tag 字段不适用
                item.get("action", ""),
                item.get("reason", ""),
                item.get("priority", "")
            ])
        
        # 处理 remove_unused_attributes
        for item in suggestion.get("remove_unused_attributes", []):
            csv_data.append([
                "remove_unused_attributes",
                item.get("selector", ""),
                item.get("tag", ""),
                item.get("attribute", ""),
                item.get("reason", ""),
                item.get("priority", "")
            ])
        
        # 处理 replace_tags
        for item in suggestion.get("replace_tags", []):
            csv_data.append([
                "replace_tags",
                item.get("selector", ""),
                item.get("original_tag", ""),
                item.get("new_tag", ""),
                item.get("reason", ""),
                item.get("priority", "")
            ])
        
        # 如果没有任何建议，添加一行提示
        if len(csv_data) == 1:
            csv_data.append(["No suggestions", "", "", "", "", ""])
        
        with open(CSV_REPORT_FILE, 'w', newline='', encoding='utf-8') as f_csv:
            writer = csv.writer(f_csv)
            writer.writerows(csv_data)
        print(f"CSV 建议报告已保存到 {CSV_REPORT_FILE}")
    else:
        print(f"警告：未能生成 CSV 报告，因为优化建议无效或为空。")

if __name__ == "__main__":
    try:
        import bs4
    except ImportError:
        print("错误：beautifulsoup4 库未安装。请运行 'pip install beautifulsoup4'")
        sys.exit(1)
    main()