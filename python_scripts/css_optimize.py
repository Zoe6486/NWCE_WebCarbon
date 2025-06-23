import os
import sys
import json
import csv
import subprocess
import shutil
import tempfile
import re
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import CSS_OPTI_DIR


# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python css_optimize.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

SOURCE_CSS_DIR = CSS_OPTI_DIR / "css_original" / PROJECT_NAME
SUGGESTIONS_DIR = CSS_OPTI_DIR / "css_llm_suggestions" / PROJECT_NAME
RESULT_DIR = CSS_OPTI_DIR / "css_optimized" / PROJECT_NAME
REPORT_DIR = CSS_OPTI_DIR / "optimization_report" / PROJECT_NAME

SUGGESTIONS_FILE = SUGGESTIONS_DIR / f"css_suggestions.json"
REPORT_FILE = REPORT_DIR / f"css_optimization_report.json"
CSV_REPORT_FILE = REPORT_DIR / f"css_optimization_summary.csv"

# --- 辅助函数：检查 Node.js 和 PostCSS ---
def check_postcss():
    node_path = shutil.which("node")
    if not node_path:
        print("错误：Node.js 未安装或未在 PATH 中。请安装 Node.js（建议版本 v16 或更高）：https://nodejs.org/")
        sys.exit(1)

    npm_path = shutil.which("npm")
    if not npm_path:
        print("警告：npm 未检测到。请确保 npm 与 Node.js 一起安装，或运行 'npm install -g npm'")
    
    project_node_modules = os.path.join(os.path.dirname(__file__), "node_modules")
    global_node_modules = os.path.join(os.path.dirname(node_path), "node_modules")
    node_modules_path = project_node_modules if os.path.exists(project_node_modules) else global_node_modules
    if not os.path.exists(node_modules_path):
        print(f"警告：node_modules 未找到。请运行 'npm install postcss postcss-safe-parser postcss-preset-env cssnano autoprefixer'")
    
    return node_path, node_modules_path

# --- 辅助函数：统计 CSS 文件信息（使用 PostCSS 和简单正则） ---
def get_css_stats(css_path):
    """
    统计 CSS 文件的详细信息，包括规则数、选择器数、重复样式等。
    使用 PostCSS 解析 CSS，并结合正则表达式统计信息。
    """
    node_path, node_modules_path = check_postcss()
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            temp_output = temp_file.name

        css_path_escaped = css_path.replace('\\', '\\\\')
        temp_output_escaped = temp_output.replace('\\', '\\\\')

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.js') as temp_js:
            temp_js_path = temp_js.name
            require_path = os.path.join(node_modules_path).replace('\\', '\\\\')
            js_content = f"""
                process.env.NODE_PATH = '{require_path}';
                require('module').Module._initPaths();
                const postcss = require('postcss');
                const presetEnv = require('postcss-preset-env');
                const safeParser = require('postcss-safe-parser');

                postcss([presetEnv, safeParser])
                    .process(require('fs').readFileSync('{css_path_escaped}', 'utf8'), {{ from: '{css_path_escaped}', to: '{temp_output_escaped}', map: {{ inline: false }} }})
                    .then(result => {{
                        require('fs').writeFileSync('{temp_output_escaped}', JSON.stringify(result.root.toJSON(), null, 2));
                    }})
                    .catch(error => {{
                        console.error(error.stack);
                        process.exit(1);
                    }});
            """
            temp_js.write(js_content)

        subprocess.run(
            [node_path, temp_js_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            check=True
        )

        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()

        rule_count = len(re.findall(r'\{[^}]*\}', css_content))
        selectors = re.findall(r'([^{]+)\{', css_content)
        selector_count = sum(len(sel.split(',')) for sel in selectors if sel.strip())

        selector_depths = []
        for sel in selectors:
            for s in sel.split(','):
                s = s.strip()
                depth = s.count(' ') + s.count('>') + s.count('.')
                selector_depths.append(depth)
        avg_selector_depth = round(sum(selector_depths) / len(selector_depths) if selector_depths else 0, 2)

        style_blocks = re.findall(r'\{([^}]*)\}', css_content)
        style_signatures = {}
        duplicate_styles = 0
        for style in style_blocks:
            style = style.strip()
            if style in style_signatures:
                style_signatures[style] += 1
                if style_signatures[style] == 2:
                    duplicate_styles += 1
            else:
                style_signatures[style] = 1

        file_size_bytes = os.path.getsize(css_path)

        if os.path.exists(temp_output):
            os.remove(temp_output)
        if os.path.exists(temp_js_path):
            os.remove(temp_js_path)

        return {
            "rule_count": rule_count,
            "selector_count": selector_count,
            "avg_selector_depth": avg_selector_depth,
            "duplicate_styles": duplicate_styles,
            "file_size_bytes": file_size_bytes,
            "file_size_kb": round(file_size_bytes / 1024, 2)
        }
    except Exception as e:
        if 'temp_js_path' in locals() and os.path.exists(temp_js_path):
            os.remove(temp_js_path)
        if 'temp_output' in locals() and os.path.exists(temp_output):
            os.remove(temp_output)
        return {
            "rule_count": 0,
            "selector_count": 0,
            "avg_selector_depth": 0.0,
            "duplicate_styles": 0,
            "file_size_bytes": os.path.getsize(css_path) if os.path.exists(css_path) else 0,
            "file_size_kb": 0.0,
            "error": str(e)
        }

# --- 辅助函数：使用 PostCSS 应用优化 ---
def apply_optimization_with_postcss(css_path, suggestion_data, output_path):
    """
    使用 PostCSS 应用优化建议，并生成优化后的 CSS 文件。
    """
    node_path, node_modules_path = check_postcss()
    try:
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
    except Exception as e:
        print(f"读取 CSS 文件 '{css_path}' 失败: {e}")
        return [], [], False

    modifications = []
    suggestion_results = []

    current_suggestions = suggestion_data.get("llm_api_call_details", {}).get("suggestion_data", {})
    if not current_suggestions or "optimizations" not in current_suggestions:
        print(f"警告：无有效的 CSS 优化建议，将仅执行基本压缩。")
        current_suggestions = {"optimizations": []}

    filtered_suggestions = {
        "remove_unused_style": [s for s in current_suggestions["optimizations"] if s.get("type") == "remove_unused_style" and s.get("original_selector_or_property")],
        "consolidate_duplicate_style": [s for s in current_suggestions["optimizations"] if s.get("type") == "consolidate_duplicate_style" and s.get("original_selector_or_property")],
        "use_shorthand_properties": [s for s in current_suggestions["optimizations"] if s.get("type") == "use_shorthand_properties" and s.get("original_selector_or_property")],
        "remove_redundant_units": [s for s in current_suggestions["optimizations"] if s.get("type") == "remove_redundant_units_or_values" and s.get("original_selector_or_property")]
    }

    def process_suggestions(suggestions_list, action_type, process_func):
        priority_order = {'high': 1, 'medium': 2, 'low': 3, None: 3}
        sorted_suggestions = sorted(suggestions_list, key=lambda x: (priority_order.get(x.get('priority', 'low'), 3), suggestions_list.index(x)))

        for suggestion in sorted_suggestions:
            selector = suggestion["original_selector_or_property"]
            reason = suggestion.get("reason", "N/A")
            priority_val = suggestion.get("priority", "low")
            confidence = suggestion.get("confidence", "low")
            requires_testing = suggestion.get("requires_testing", "yes") == "yes"
            if confidence == "low" or requires_testing:
                print(f"    警告：建议 '{action_type}' ('{selector}') 置信度低或需要测试，谨慎执行。")
                suggestion_results.append({
                    "type": action_type,
                    "selector": selector,
                    "status": "skipped",
                    "details": "Skipped due to low confidence or requires testing"
                })
                continue
            try:
                new_css_content = process_func(css_content, suggestion)
                if new_css_content != css_content:
                    changed_count = 1
                    modifications.append(f"{action_type} (Priority: {priority_val}, Count: {changed_count}): '{selector}' - {reason}")
                else:
                    changed_count = 0
                css_content = new_css_content
                suggestion_results.append({
                    "type": action_type,
                    "selector": selector,
                    "status": "success" if changed_count > 0 else "skipped",
                    "details": f"Modified {changed_count} rules" if changed_count > 0 else "No matching rules found"
                })
            except Exception as e:
                print(f"    处理 {action_type} '{selector}' 时发生错误: {e}")
                suggestion_results.append({
                    "type": action_type,
                    "selector": selector,
                    "status": "failed",
                    "details": str(e)
                })

    def remove_unused_style(css_content, suggestion):
        selector = suggestion["original_selector_or_property"]
        pattern = rf'{re.escape(selector)}\s*\{{[^}}]*\}}'
        new_content, _ = re.subn(pattern, '', css_content)
        return new_content

    process_suggestions(filtered_suggestions["remove_unused_style"], "Removed unused style", remove_unused_style)

    def consolidate_duplicate_style(css_content, suggestion):
        selectors = suggestion["original_selector_or_property"].split(", ")
        pattern = rf'({"|".join(map(re.escape, selectors))})\s*\{{([^}}]*)\}}'
        matches = re.findall(pattern, css_content)
        if len(matches) > 1:
            style = matches[0][1]
            if all(m[1] == style for m in matches[1:]):
                for sel, _ in matches:
                    css_content = re.sub(rf'{re.escape(sel)}\s*\{{[^}}]*\}}', '', css_content)
                css_content += f"\n{', '.join(selectors)} {{{style}}}"
                return css_content
        return css_content

    process_suggestions(filtered_suggestions["consolidate_duplicate_style"], "Consolidated duplicate styles", consolidate_duplicate_style)

    def use_shorthand_properties(css_content, suggestion):
        selector = suggestion["original_selector_or_property"]
        pattern = rf'({re.escape(selector)})\s*\{{([^}}]*)\}}'
        matches = re.finditer(pattern, css_content)
        changed_content = css_content
        changed_count = 0
        for match in matches:
            sel, style_block = match.groups()
            style_lines = style_block.split(';')
            margins = {}
            new_styles = []
            for line in style_lines:
                line = line.strip()
                if not line:
                    continue
                if ':' in line:
                    prop, val = map(str.strip, line.split(':', 1))
                    if prop in ['margin-top', 'margin-right', 'margin-bottom', 'margin-left']:
                        margins[prop.replace('margin-', '')] = val
                    else:
                        new_styles.append(line)
            if len(margins) == 4:
                margin_val = f"{margins['top']} {margins['right']} {margins['bottom']} {margins['left']}"
                new_styles.append(f"margin: {margin_val}")
                new_style_block = '; '.join(new_styles)
                changed_content = changed_content.replace(match.group(0), f"{sel} {{{new_style_block}}}")
                changed_count += 1
        return changed_content if changed_count > 0 else css_content

    process_suggestions(filtered_suggestions["use_shorthand_properties"], "Used shorthand properties", use_shorthand_properties)

    def remove_redundant_units(css_content, suggestion):
        selector = suggestion["original_selector_or_property"]
        pattern = rf'({re.escape(selector)})\s*\{{([^}}]*)\}}'
        matches = re.finditer(pattern, css_content)
        changed_content = css_content
        changed_count = 0
        for match in matches:
            sel, style_block = match.groups()
            style_lines = style_block.split(';')
            new_styles = []
            for line in style_lines:
                line = line.strip()
                if not line:
                    continue
                if ':' in line:
                    prop, val = map(str.strip, line.split(':', 1))
                    if val.endswith('0px') or val.endswith('0em') or val.endswith('0%'):
                        val = val[:-2]
                        changed_count += 1
                    new_styles.append(f"{prop}: {val}")
            new_style_block = '; '.join(new_styles)
            changed_content = changed_content.replace(match.group(0), f"{sel} {{{new_style_block}}}")
        return changed_content if changed_count > 0 else css_content

    process_suggestions(filtered_suggestions["remove_redundant_units"], "Removed redundant units", remove_redundant_units)

    temp_output_path = os.path.join(RESULT_DIR, f"{PROJECT_NAME}_style_temp.css")
    try:
        os.makedirs(RESULT_DIR, exist_ok=True)
        with open(temp_output_path, 'w', encoding='utf-8') as f:
            f.write(css_content)
    except Exception as e:
        print(f"写入临时 CSS 文件 '{temp_output_path}' 失败: {e}")
        shutil.copy2(css_path, output_path)
        return modifications, suggestion_results, False

    try:
        temp_output_path_escaped = temp_output_path.replace('\\', '\\\\')
        output_path_escaped = output_path.replace('\\', '\\\\')

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.js') as temp_js:
            temp_js_path = temp_js.name
            require_path = os.path.join(node_modules_path).replace('\\', '\\\\')
            js_content = f"""
                process.env.NODE_PATH = '{require_path}';
                require('module').Module._initPaths();
                const postcss = require('postcss');
                const cssnano = require('cssnano');
                const autoprefixer = require('autoprefixer');
                const presetEnv = require('postcss-preset-env');

                postcss([cssnano, autoprefixer, presetEnv])
                    .process(require('fs').readFileSync('{temp_output_path_escaped}', 'utf8'), {{ from: '{temp_output_path_escaped}', to: '{output_path_escaped}', map: {{ inline: false }} }})
                    .then(result => {{
                        require('fs').writeFileSync('{output_path_escaped}', result.css);
                    }})
                    .catch(error => {{
                        console.error(error.stack);
                        process.exit(1);
                    }});
            """
            temp_js.write(js_content)

        subprocess.run(
            [node_path, temp_js_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            check=True
        )

        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        if os.path.exists(temp_js_path):
            os.remove(temp_js_path)

        return modifications, suggestion_results, True

    except Exception as e:
        print(f"优化 CSS '{css_path}' 时发生错误: {e}")
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        if os.path.exists(temp_js_path):
            os.remove(temp_js_path)
        shutil.copy2(css_path, output_path)
        return modifications, suggestion_results, False

# --- 优化函数 ---
def optimize_css(css_path, suggestion_data):
    try:
        before_stats = get_css_stats(css_path)

        output_path = os.path.join(RESULT_DIR, "style.css")
        modifications, suggestion_results, cssnano_applied = apply_optimization_with_postcss(css_path, suggestion_data, output_path)

        after_stats = {}
        if os.path.exists(output_path):
            after_stats = get_css_stats(output_path)
        else:
            print(f"警告：优化后的 CSS 文件 '{output_path}' 未生成，无法统计优化后信息。")
            after_stats = {"error": "Optimized CSS file not generated"}

        changes = {
            "rules_reduced": after_stats.get("rule_count", 0) - before_stats.get("rule_count", 0),
            "selectors_reduced": after_stats.get("selector_count", 0) - before_stats.get("selector_count", 0),
            "avg_selector_depth_reduced": round(after_stats.get("avg_selector_depth", 0) - before_stats.get("avg_selector_depth", 0), 2),
            "duplicate_styles_reduced": after_stats.get("duplicate_styles", 0) - before_stats.get("duplicate_styles", 0),
            "size_reduction_bytes": after_stats.get("file_size_bytes", 0) - before_stats.get("file_size_bytes", 0),
            "size_reduction_percent": round(
                (after_stats.get("file_size_bytes", 0) - before_stats.get("file_size_bytes", 0)) / (before_stats.get("file_size_bytes", 1) or 1) * 100, 2
            ) if before_stats.get("file_size_bytes", 0) > 0 else 0
        }

        return {
            "status": "success" if cssnano_applied else "partial_success",
            "before_optimization": before_stats,
            "after_optimization": after_stats,
            "changes": changes,
            "modifications": modifications,
            "suggestion_results": suggestion_results,
            "cssnano_applied": cssnano_applied
        }
    except Exception as e:
        print(f"优化 CSS '{css_path}' 时发生严重错误: {e}")
        import traceback
        traceback.print_exc()
        cs = {}
        try:
            if os.path.exists(css_path):
                cs = get_css_stats(css_path)
        except:
            pass
        return {
            "status": "failed",
            "before_optimization": cs or {"error": f"Could not retrieve stats for {css_path}"},
            "after_optimization": {},
            "changes": {},
            "modifications": [],
            "suggestion_results": [],
            "cssnano_applied": False,
            "error": str(e)
        }

# --- 主逻辑 ---
def main():
    if not os.path.exists(SOURCE_CSS_DIR):
        print(f"错误：源 CSS 目录 '{SOURCE_CSS_DIR}' 不存在。")
        return

    css_file_name = "style.css"
    css_path = os.path.join(SOURCE_CSS_DIR, css_file_name)
    if not os.path.exists(css_path):
        print(f"错误：CSS 文件 '{css_path}' 不存在。")
        return

    if not os.path.exists(SUGGESTIONS_FILE):
        print(f"警告：优化建议文件 '{SUGGESTIONS_FILE}' 不存在。将使用默认的基本压缩。")
        loaded_suggestions = {"llm_api_call_details": {"suggestion_data": {"optimizations": []}}}
    else:
        try:
            with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
                loaded_suggestions = json.load(f)[0]
            if "error" in loaded_suggestions and loaded_suggestions["error"]:
                print(f"警告：优化建议文件包含错误：{loaded_suggestions['error']}. 将尝试使用其余建议。")
        except Exception as e:
            print(f"错误：无法读取优化建议文件 '{SUGGESTIONS_FILE}'：{e}. 将使用默认的基本压缩。")
            loaded_suggestions = {"llm_api_call_details": {"suggestion_data": {"optimizations": []}}}

    if os.path.exists(RESULT_DIR):
        for file in os.listdir(RESULT_DIR):
            file_path = os.path.join(RESULT_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"警告: 清理文件 {file_path} 时出错: {e}")

    print(f"\n开始优化 CSS for project: {PROJECT_NAME} (File: {css_file_name})")
    check_postcss()
    result = optimize_css(css_path, loaded_suggestions)

    report = {
        "project_name": PROJECT_NAME,
        "css_file": css_file_name,
        "optimization_status": result["status"],
        "before_optimization": result["before_optimization"],
        "after_optimization": result["after_optimization"],
        "changes": result["changes"],
        "modifications": result["modifications"],
        "suggestion_results": result["suggestion_results"],
        "cssnano_applied": result["cssnano_applied"],
        "error": result.get("error", "")
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f_report:
        json.dump(report, f_report, indent=4, ensure_ascii=False)
    print(f"优化报告已保存到 {REPORT_FILE}")

    # 生成 CSV 报告
    csv_data = [["Metric", "Before Optimization", "After Optimization", "Change (Units)"]]
    metrics = [
        ("rule_count", "rules_reduced", ""),
        ("selector_count", "selectors_reduced", ""),
        ("avg_selector_depth", "avg_selector_depth_reduced", ""),
        ("duplicate_styles", "duplicate_styles_reduced", ""),
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