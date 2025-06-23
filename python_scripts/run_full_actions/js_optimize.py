import os
import sys
import json
import csv
import subprocess
import shutil
import re
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import  FULL_OPTI_DIR

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python js_optimize.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

SOURCE_TEMP_DIR= FULL_OPTI_DIR / "temp" /PROJECT_NAME/ "js"

SOURCE_JS_DIR = SOURCE_TEMP_DIR / "js_original"

SUGGESTIONS_DIR = SOURCE_TEMP_DIR / "js_llm_suggestions"
RESULT_DIR = SOURCE_TEMP_DIR / "js_optimized"
REPORT_DIR = SOURCE_TEMP_DIR / "optimization_report"

SUGGESTIONS_FILE = os.path.join(SUGGESTIONS_DIR, f"js_suggestions.json")
REPORT_FILE = os.path.join(REPORT_DIR, f"js_optimization_report.json")
CSV_REPORT_FILE = os.path.join(REPORT_DIR, f"js_optimization_summary.csv")

# --- 辅助函数：检查 Node.js 和 UglifyJS ---
def check_uglifyjs():
    node_path = shutil.which("node")
    if not node_path:
        print("错误：Node.js 未安装或未在 PATH 中。请安装 Node.js（建议版本 v16 或更高）：https://nodejs.org/")
        sys.exit(1)

    uglifyjs_path = shutil.which("uglifyjs")
    if not uglifyjs_path:
        print("警告：UglifyJS 未安装或未在 PATH 中。请运行 'npm install -g uglify-js' 并确保 Node.js 已安装。")
    return uglifyjs_path

# --- 辅助函数：统计 JS 文件信息 ---
def get_js_stats(js_path):
    """
    统计 JS 文件的详细信息，包括行数、函数数、变量数等。
    """
    try:
        with open(js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()
        line_count = js_content.count('\n') + 1
        function_count = len(re.findall(r'function\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(', js_content))
        variable_count = len(re.findall(r'var|let|const\s+[a-zA-Z_][a-zA-Z0-9_]*', js_content))
        file_size_bytes = os.path.getsize(js_path)
        return {
            "line_count": line_count,
            "function_count": function_count,
            "variable_count": variable_count,
            "file_size_bytes": file_size_bytes,
            "file_size_kb": round(file_size_bytes / 1024, 2)
        }
    except Exception as e:
        print(f"    统计 JS 文件信息 '{js_path}' 时发生错误: {e}")
        return {
            "line_count": 0,
            "function_count": 0,
            "variable_count": 0,
            "file_size_bytes": os.path.getsize(js_path) if os.path.exists(js_path) else 0,
            "file_size_kb": 0.0
        }

# --- 辅助函数：使用 UglifyJS 压缩 JS ---
def minify_js_with_uglifyjs(input_path, output_path):
    uglifyjs_path = check_uglifyjs()
    if not uglifyjs_path:
        print(f"UglifyJS 不可用，将跳过压缩步骤，直接复制文件。")
        shutil.copy2(input_path, output_path)
        return False
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        command = [
            uglifyjs_path, "--compress", "--mangle", "--output", output_path, input_path
        ]
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"使用 UglifyJS 压缩 JS 文件: {output_path}")
        if result.stdout: print(f"UglifyJS 输出: {result.stdout}")
        if result.stderr: print(f"UglifyJS 错误流输出: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"UglifyJS 压缩失败: {e}\n错误输出: {e.stderr}\n标准输出: {e.stdout}")
        shutil.copy2(input_path, output_path)
        return False
    except Exception as e:
        print(f"UglifyJS 压缩过程中发生未知错误: {e}")
        shutil.copy2(input_path, output_path)
        return False

# --- 优化函数 ---
def optimize_js(js_path, suggestion_data):
    try:
        before_stats = get_js_stats(js_path)
        modifications = []

        # 加载建议数据
        all_suggestions = suggestion_data
        current_suggestions = []
        for entry in all_suggestions:
            if entry.get("js_filename") == os.path.basename(js_path) and entry.get("llm_api_call_details", {}).get("suggestion_data"):
                current_suggestions = entry["llm_api_call_details"]["suggestion_data"]["optimizations"]
                break

        if not current_suggestions:
            print(f"警告：无有效的 JS 优化建议，将仅执行基本压缩。")
            current_suggestions = []

        # 处理建议
        def process_suggestion(suggestion, js_content):
            changed = False
            try:
                # 验证 suggestion["original_code_snippet"] 是否存在且为字符串
                if not isinstance(suggestion.get("original_code_snippet"), str):
                    print(f"警告：无效的 original_code_snippet: {suggestion.get('original_code_snippet')}")
                    return js_content, False

                # 转义 original_code_snippet 中的特殊字符
                snippet = re.escape(suggestion["original_code_snippet"])
                
                # 检查 snippet 是否包含无效字符范围（例如 v-l）
                if re.search(r'\[\w+-\w+\]', snippet):
                    print(f"警告：original_code_snippet 包含无效字符范围: {suggestion['original_code_snippet']}")
                    return js_content, False

                if suggestion["type"] == "remove_unused_variable":
                    # 使用转义后的 snippet 构造正则表达式
                    pattern = re.compile(rf'\b{snippet}\b(?!\s*=)')
                    # 检查变量是否未被使用且未被重新赋值
                    if not re.search(pattern, js_content) and not re.search(rf'\b{snippet}\s*=', js_content):
                        js_content = re.sub(pattern, '', js_content)
                        changed = True
                elif suggestion["type"] == "minimize_redundant_code":
                    # 同样转义 original_code_snippet 和 suggested_change_or_action
                    original = re.escape(suggestion["original_code_snippet"])
                    replacement = suggestion.get("suggested_change_or_action", "")
                    if isinstance(replacement, str):
                        replacement = re.escape(replacement)
                    js_content = re.sub(original, replacement, js_content, count=1)
                    changed = True
            except re.error as e:
                print(f"正则表达式错误：{e}，跳过建议：{suggestion}")
                changed = False
            except Exception as e:
                print(f"处理建议时发生未知错误：{e}，跳过建议：{suggestion}")
                changed = False
            return js_content, changed

        with open(js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()

        for suggestion in current_suggestions:
            js_content, changed = process_suggestion(suggestion, js_content)
            if changed:
                modifications.append(f"{suggestion['type']} (Priority: {suggestion.get('priority', 'low')}): {suggestion['original_code_snippet']} → {suggestion.get('suggested_change_or_action', 'removed')} - {suggestion['reason']}")

        os.makedirs(RESULT_DIR, exist_ok=True)
        temp_output_path = os.path.join(RESULT_DIR, f"{PROJECT_NAME}_script_temp.js")
        with open(temp_output_path, 'w', encoding='utf-8') as f:
            f.write(js_content)

        minified_output_path = os.path.join(RESULT_DIR, "script.js")
        minified_success = minify_js_with_uglifyjs(temp_output_path, minified_output_path)

        if os.path.exists(temp_output_path):
            try: os.remove(temp_output_path)
            except OSError as e: print(f"警告: 无法删除临时文件 {temp_output_path}: {e}")

        after_stats = get_js_stats(minified_output_path)
        changes = {
            "lines_reduced": after_stats.get("line_count", 0) - before_stats.get("line_count", 0),
            "functions_reduced": after_stats.get("function_count", 0) - before_stats.get("function_count", 0),
            "variables_reduced": after_stats.get("variable_count", 0) - before_stats.get("variable_count", 0),
            "size_reduction_bytes": after_stats.get("file_size_bytes", 0) - before_stats.get("file_size_bytes", 0),
            "size_reduction_percent": round(
                (after_stats.get("file_size_bytes", 0) - before_stats.get("file_size_bytes", 0)) / (before_stats.get("file_size_bytes", 1) or 1) * 100, 2
            ) if before_stats.get("file_size_bytes", 0) > 0 else 0
        }

        return {
            "status": "success" if minified_success else "partial_success",
            "before_optimization": before_stats,
            "after_optimization": after_stats,
            "changes": changes,
            "modifications": modifications,
            "uglifyjs_applied": minified_success
        }
    except Exception as e:
        print(f"    优化 JS {js_path} 时发生严重错误: {e}")
        import traceback
        traceback.print_exc()
        js = {}
        try:
            if os.path.exists(js_path): js = get_js_stats(js_path)
        except: pass
        return {
            "status": "failed",
            "before_optimization": js or {"error": f"Could not retrieve stats for {js_path}"},
            "after_optimization": {},
            "changes": {},
            "modifications": modifications,
            "uglifyjs_applied": False,
            "error": str(e)
        }

# --- 主逻辑 ---
def main():
    if not os.path.exists(SOURCE_JS_DIR):
        print(f"错误：源 JS 目录 '{SOURCE_JS_DIR}' 不存在。")
        return

    js_file_name = "script.js"
    js_path = os.path.join(SOURCE_JS_DIR, js_file_name)
    if not os.path.exists(js_path):
        print(f"错误：JS 文件 '{js_path}' 不存在。")
        return

    if not os.path.exists(SUGGESTIONS_FILE):
        print(f"警告：优化建议文件 '{SUGGESTIONS_FILE}' 不存在。将使用默认的基本压缩。")
        loaded_suggestions = [{"js_filename": js_file_name, "llm_api_call_details": {"suggestion_data": {"optimizations": []}}}]
    else:
        try:
            with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
                loaded_suggestions = json.load(f)
            if any("error" in entry.get("llm_api_call_details", {}) and entry["llm_api_call_details"]["error"] for entry in loaded_suggestions):
                print(f"警告：优化建议文件包含错误。")
        except Exception as e:
            print(f"错误：无法读取优化建议文件 '{SUGGESTIONS_FILE}'：{e}. 将使用默认的基本压缩。")
            loaded_suggestions = [{"js_filename": js_file_name, "llm_api_call_details": {"suggestion_data": {"optimizations": []}}}]

    if os.path.exists(RESULT_DIR):
        for file in os.listdir(RESULT_DIR):
            file_path = os.path.join(RESULT_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"清理旧文件: {file_path}")
            except Exception as e:
                print(f"警告: 清理文件 {file_path} 时出错: {e}")

    print(f"\n开始优化 JS for project: {PROJECT_NAME} (File: {js_file_name})")
    check_uglifyjs()
    result = optimize_js(js_path, loaded_suggestions)

    report = {
        "project_name": PROJECT_NAME,
        "js_file": js_file_name,
        "optimization_status": result["status"],
        "before_optimization": result["before_optimization"],
        "after_optimization": result["after_optimization"],
        "changes": result["changes"],
        "modifications": result["modifications"],
        "uglifyjs_applied": result["uglifyjs_applied"],
        "error": result.get("error", "")
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f_report:
        json.dump(report, f_report, indent=4, ensure_ascii=False)
    print(f"优化报告已保存到 {REPORT_FILE}")

    # 生成 CSV 报告
    csv_data = [["Metric", "Before Optimization", "After Optimization", "Change (Units)"]]
    metrics = [
        ("line_count", "lines_reduced", ""),
        ("function_count", "functions_reduced", ""),
        ("variable_count", "variables_reduced", ""),
        ("file_size_bytes", "size_reduction_bytes", "size_reduction_percent")
    ]
    for metric, change_key, extra_field in metrics:
        before = result["before_optimization"].get(metric, "N/A")
        after = result["after_optimization"].get(metric, "N/A")
        change_value = result["changes"].get(change_key, "N/A")
        if metric == "file_size_bytes" and change_value != "N/A":
            percent = result["changes"].get("size_reduction_percent", 0)
            change_display = f"{change_value} ({percent}%)"
        else:
            change_display = change_value
        csv_data.append([metric, str(before), str(after), str(change_display)])

    with open(CSV_REPORT_FILE, 'w', newline='', encoding='utf-8') as f_csv:
        writer = csv.writer(f_csv)
        writer.writerows(csv_data)
    print(f"优化报告 CSV 已保存到 {CSV_REPORT_FILE}")

if __name__ == "__main__":
    main()