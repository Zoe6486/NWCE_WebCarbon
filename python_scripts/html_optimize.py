import os
import sys
import json
import csv
from bs4 import BeautifulSoup, Comment
from lxml import html
import subprocess
import shutil

from pathlib import Path
# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import  HTML_OPTI_DIR

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python html_optimize.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

SOURCE_HTML_DIR = os.path.join(HTML_OPTI_DIR, "html_original", PROJECT_NAME)
SUGGESTIONS_DIR = os.path.join(HTML_OPTI_DIR, "html_llm_suggestions", PROJECT_NAME)
RESULT_DIR = os.path.join(HTML_OPTI_DIR, "html_optimized", PROJECT_NAME)
REPORT_DIR = os.path.join(HTML_OPTI_DIR, "optimization_report", PROJECT_NAME)

SUGGESTIONS_FILE = os.path.join(SUGGESTIONS_DIR, "html_optimization_suggestions.json")
REPORT_FILE = os.path.join(REPORT_DIR, "optimization_report.json")
CSV_REPORT_FILE = os.path.join(REPORT_DIR, "optimization_summary.csv")

# --- 辅助函数：统计 HTML 文件信息 ---
def get_html_stats(html_path):
    """
    使用 lxml 统计 HTML 文件的详细信息，包含空标签调试信息。
    """
    try:
        with open(html_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        parser = html.HTMLParser(encoding='utf-8')
        tree = html.fromstring(content, parser=parser)

        total_tags = len(tree.xpath('//*')) + 1  # 包含根节点
        comments = len(tree.xpath('//comment()'))

        def get_max_depth(element):
            children = element.xpath('./*')
            if not children:
                return 1
            return 1 + max(get_max_depth(child) for child in children)
        max_depth = get_max_depth(tree) if tree.xpath('//*') else 0

        actual_empty_tag_count = 0
        void_elements = ['br', 'hr', 'img', 'input', 'meta', 'link', 'base', 'col', 'embed', 'keygen', 'param', 'source', 'track', 'wbr']
        
        for elem in tree.xpath('//*'):
            is_empty = (elem.tag not in void_elements and
                        not elem.xpath('./*') and
                        not (elem.text and elem.text.strip()) and
                        not (elem.tail and elem.tail.strip()))
            if is_empty:
                actual_empty_tag_count += 1

        total_attributes = sum(len(elem.attrib) for elem in tree.xpath('//*'))

        return {
            "total_tags": total_tags,
            "comment_count": comments,
            "max_nesting_depth": max_depth,
            "empty_tag_count": actual_empty_tag_count,
            "total_attributes": total_attributes,
            "file_size_bytes": os.path.getsize(html_path)
        }
    except Exception as e:
        print(f"    统计 HTML 文件信息 '{html_path}' 时发生错误: {e}")
        return {
            "total_tags": 0, "comment_count": 0, "max_nesting_depth": 0,
            "empty_tag_count": 0, "total_attributes": 0,
            "file_size_bytes": os.path.getsize(html_path) if os.path.exists(html_path) else 0
        }

# --- 辅助函数：检查 html-minifier ---
def check_html_minifier():
    html_minifier_path = shutil.which("html-minifier")
    if not html_minifier_path:
        print("警告：html-minifier 未安装或未在 PATH 中。请运行 'npm install -g html-minifier' 并确保 Node.js 已安装。")
    return html_minifier_path

# --- 辅助函数：使用 html-minifier ---
def minify_html_with_html_minifier(input_path, output_path):
    html_minifier_path = check_html_minifier()
    if not html_minifier_path:
        print(f"html-minifier 不可用，将跳过压缩步骤，直接复制文件。")
        shutil.copy2(input_path, output_path)
        return False
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        command = [
            html_minifier_path, "--collapse-whitespace", "--remove-comments",
            "--conservative-collapse", "--keep-closing-slash", "--collapse-boolean-attributes",
            input_path, "-o", output_path
        ]
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=(sys.platform == "win32"))
        print(f"使用 html-minifier 进一步压缩 HTML 文件: {output_path}")
        if result.stdout: print(f"html-minifier 输出: {result.stdout}")
        if result.stderr: print(f"html-minifier 错误流输出: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"html-minifier 压缩失败: {e}\n错误输出: {e.stderr}\n标准输出: {e.stdout}")
        shutil.copy2(input_path, output_path)
        return False
    except Exception as e:
        print(f"html-minifier 压缩过程中发生未知错误: {e}")
        shutil.copy2(input_path, output_path)
        return False

# --- 全局常量和辅助函数 ---
BS4_VOID_ELEMENTS = {'br', 'hr', 'img', 'input', 'meta', 'link', 'base', 'col', 'embed', 'keygen', 'param', 'source', 'track', 'wbr'}
PROTECTED_TAGS_WHEN_EMPTY_PARENT_CHECK = BS4_VOID_ELEMENTS.union({'html', 'head', 'body', 'script', 'style', 'title', 'template'})

def is_safe_to_remove_empty_tag(tag_element):
    """判断一个标签是否为空且移除它是安全的（不破坏CSS/JS钩子）"""
    if tag_element.name in BS4_VOID_ELEMENTS:
        return False

    is_structurally_empty = not tag_element.find_all(recursive=False) and not tag_element.get_text(strip=True)
    if not is_structurally_empty:
        return False

    critical_attributes = ['id', 'class', 'style', 'name']
    for attr in critical_attributes:
        if tag_element.has_attr(attr):
            return False
    
    for attr_name in tag_element.attrs.keys():
        attr_name_lower = attr_name.lower()
        if attr_name_lower.startswith('data-') or \
           attr_name_lower.startswith('on') or \
           attr_name_lower in ['role', 'value'] or \
           attr_name_lower.startswith('aria-'):
            return False
    return True

def is_critical_attribute_for_removal(attr_name_str):
    """判断一个属性是否为关键属性，不应轻易移除"""
    attr_name_lower = attr_name_str.lower()
    critical_set = {
        'id', 'class', 'style', 'name', 'href', 'src', 'action', 'method', 'value', 'type', 
        'placeholder', 'alt', 'title', 'role', 'for', 'rel', 'target', 'media', 'charset', 'lang',
        'disabled', 'readonly', 'required', 'checked', 'selected', 'multiple', 'pattern',
        'min', 'max', 'step', 'novalidate', 'autocomplete', 'autofocus', 'contenteditable'
    }
    if attr_name_lower in critical_set or \
       attr_name_lower.startswith('data-') or \
       attr_name_lower.startswith('on') or \
       attr_name_lower.startswith('aria-'):
        return True
    return False

# --- 优化函数 ---
def optimize_html(html_path, suggestion_data):
    try:
        before_stats = get_html_stats(html_path)
        with open(html_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'html.parser')
        
        modifications = []
        current_suggestions = suggestion_data

        filtered_suggestion_actions = {
            "remove_comments": current_suggestions.get("remove_comments", False),
            "remove_redundant_tags": [s for s in current_suggestions.get("remove_redundant_tags", []) if s.get("selector") and soup.select_one(s.get("selector"))],
            "simplify_nested_structures": [s for s in current_suggestions.get("simplify_nested_structures", []) if s.get("selector") and soup.select_one(s.get("selector"))],
            "remove_unused_attributes": [s for s in current_suggestions.get("remove_unused_attributes", []) if s.get("selector") and s.get("attribute") and soup.select_one(s.get("selector"))],
            "replace_tags": [s for s in current_suggestions.get("replace_tags", []) if s.get("selector") and s.get("new_tag") and soup.select_one(s.get("selector"))]
        }

        def process_suggestions(suggestions_list, action_type, process_func, current_soup_obj):
            priority_order = {'high': 1, 'medium': 2, 'low': 3, None: 3}
            sorted_suggestions = sorted(suggestions_list, key=lambda x: (priority_order.get(x.get('priority', 'low'), 3), suggestions_list.index(x)))

            for suggestion_item in sorted_suggestions:
                selector = suggestion_item["selector"]
                reason = suggestion_item.get("reason", "N/A")
                priority_val = suggestion_item.get("priority", "low")
                try:
                    changed_count = process_func(suggestion_item, current_soup_obj)
                    if changed_count > 0:
                        modifications.append(f"{action_type} (Priority: {priority_val}, Count: {changed_count}): '{selector}' - {reason}")
                except Exception as e:
                    print(f"    处理 {action_type} '{selector}' 时发生错误: {e}")

        if filtered_suggestion_actions.get("remove_comments"):
            comments_found = soup.find_all(string=lambda text: isinstance(text, Comment))
            num_comments_removed = 0
            for comment_node in comments_found:
                comment_node.extract()
                num_comments_removed += 1
            if num_comments_removed > 0:
                modifications.append(f"Removed {num_comments_removed} HTML comment(s) (Priority: high)")

        def remove_redundant_tag_suggested(tag_info, current_soup):
            selector = tag_info["selector"]
            tags_found = current_soup.select(selector)
            removed_count = 0
            for tag in tags_found:
                if is_safe_to_remove_empty_tag(tag):
                    parent = tag.parent
                    tag.decompose()
                    removed_count += 1
                    while parent and parent.name not in PROTECTED_TAGS_WHEN_EMPTY_PARENT_CHECK:
                        if is_safe_to_remove_empty_tag(parent):
                            grandparent = parent.parent
                            parent.decompose()
                            parent = grandparent
                        else: break
            return removed_count
        process_suggestions(filtered_suggestion_actions.get("remove_redundant_tags", []), "Removed redundant tag (suggested)", remove_redundant_tag_suggested, soup)

        def remove_all_empty_tags_conservative(current_soup):
            tags_removed_this_pass = 0
            processed_tags_in_pass = set()

            for _ in range(10):
                empty_tags_found_this_iteration = []
                for tag_candidate in current_soup.find_all(True):
                    if id(tag_candidate) in processed_tags_in_pass or not tag_candidate.parent:
                        continue
                    if is_safe_to_remove_empty_tag(tag_candidate):
                        empty_tags_found_this_iteration.append(tag_candidate)
                
                if not empty_tags_found_this_iteration:
                    break

                for tag_to_remove in empty_tags_found_this_iteration:
                    if not tag_to_remove.parent: continue

                    parent = tag_to_remove.parent
                    tag_to_remove.decompose()
                    tags_removed_this_pass += 1
                    processed_tags_in_pass.add(id(tag_to_remove))

                    while parent and parent.name not in PROTECTED_TAGS_WHEN_EMPTY_PARENT_CHECK:
                        if is_safe_to_remove_empty_tag(parent):
                            grandparent = parent.parent
                            parent.decompose()
                            processed_tags_in_pass.add(id(parent))
                            parent = grandparent
                        else:
                            break 
            return tags_removed_this_pass
        
        cleaned_count = remove_all_empty_tags_conservative(soup)
        if cleaned_count > 0:
            modifications.append(f"General cleanup: Removed {cleaned_count} inherently empty and safe tag(s)")

        def simplify_structure_suggested(simplify_info, current_soup):
            selector = simplify_info["selector"]
            action = simplify_info.get("action")
            tags_found = current_soup.select(selector)
            changed_count = 0
            if action == "unwrap":
                for tag in tags_found:
                    original_parent = tag.parent
                    tag.unwrap()
                    changed_count += 1
                    if original_parent and original_parent.name not in PROTECTED_TAGS_WHEN_EMPTY_PARENT_CHECK:
                        if is_safe_to_remove_empty_tag(original_parent):
                            original_parent.decompose()
            return changed_count
        process_suggestions(filtered_suggestion_actions.get("simplify_nested_structures", []), "Simplified nested structure (suggested)", simplify_structure_suggested, soup)

        def remove_attribute_suggested(attr_info, current_soup):
            selector = attr_info["selector"]
            attribute_to_remove = attr_info["attribute"]
            tags_found = current_soup.select(selector)
            changed_count = 0
            for tag in tags_found:
                if tag.has_attr(attribute_to_remove):
                    if is_critical_attribute_for_removal(attribute_to_remove) and \
                       not attr_info.get("force_remove_critical", False):
                        continue
                    
                    del tag[attribute_to_remove]
                    changed_count += 1
            return changed_count
        process_suggestions(filtered_suggestion_actions.get("remove_unused_attributes", []), "Removed attribute (suggested)", remove_attribute_suggested, soup)
        
        def replace_tag_suggested(replace_info, current_soup):
            selector = replace_info["selector"]
            new_tag_name = replace_info["new_tag"]
            tags_found = current_soup.select(selector)
            changed_count = 0
            for old_tag in tags_found:
                new_tag_obj = current_soup.new_tag(new_tag_name)
                new_tag_obj.attrs = old_tag.attrs
                for child in list(old_tag.contents):
                    new_tag_obj.append(child)
                old_tag.replace_with(new_tag_obj)
                changed_count += 1
                if is_safe_to_remove_empty_tag(new_tag_obj):
                    new_tag_obj.decompose()
            return changed_count
        process_suggestions(filtered_suggestion_actions.get("replace_tags", []), "Replaced tag (suggested)", replace_tag_suggested, soup)

        os.makedirs(RESULT_DIR, exist_ok=True)
        temp_output_path = os.path.join(RESULT_DIR, f"{PROJECT_NAME}_index_temp.html")
        with open(temp_output_path, 'w', encoding='utf-8') as file:
            file.write(str(soup))
        
        temp_stats = get_html_stats(temp_output_path)

        minified_output_path = os.path.join(RESULT_DIR, "index.html")
        minified_success = minify_html_with_html_minifier(temp_output_path, minified_output_path)
        
        if os.path.exists(temp_output_path):
            try: os.remove(temp_output_path)
            except OSError as e: print(f"警告: 无法删除临时文件 {temp_output_path}: {e}")

        after_stats = get_html_stats(minified_output_path)
        changes = {
            "tags_reduced": after_stats.get("total_tags", 0) - before_stats.get("total_tags", 0),
            "comments_reduced": after_stats.get("comment_count", 0) - before_stats.get("comment_count", 0),
            "max_depth_reduced": after_stats.get("max_nesting_depth", 0) - before_stats.get("max_nesting_depth", 0),
            "empty_tags_reduced": after_stats.get("empty_tag_count", 0) - before_stats.get("empty_tag_count", 0),
            "attributes_reduced": after_stats.get("total_attributes", 0) - before_stats.get("total_attributes", 0),
            "size_reduction_bytes": after_stats.get("file_size_bytes", 0) - before_stats.get("file_size_bytes", 0),
            "size_reduction_percent": round(
                (after_stats.get("file_size_bytes", 0) - before_stats.get("file_size_bytes", 0)) / (before_stats.get("file_size_bytes", 1) or 1) * 100, 2
            ) if before_stats.get("file_size_bytes", 0) > 0 else 0
        }
        return {
            "status": "success", "before_optimization": before_stats, "after_optimization": after_stats,
            "changes": changes, "modifications": modifications, "html_minifier_applied": minified_success
        }
    except Exception as e:
        print(f"    优化 HTML {html_path} 时发生严重错误: {e}")
        import traceback
        traceback.print_exc()
        bs = {}
        try:
            if os.path.exists(html_path): bs = get_html_stats(html_path)
        except: pass
        return {
            "status": "failed", "before_optimization": bs or {"error": f"Could not retrieve stats for {html_path}"},
            "after_optimization": {}, "changes": {}, "modifications": modifications,
            "html_minifier_applied": False, "error": str(e)
        }

# --- 主逻辑 ---
def main():
    if not os.path.exists(SOURCE_HTML_DIR):
        print(f"错误：源 HTML 目录 '{SOURCE_HTML_DIR}' 不存在。")
        return

    if not os.path.exists(SUGGESTIONS_FILE):
        print(f"警告：优化建议文件 '{SUGGESTIONS_FILE}' 不存在。将使用默认的基本清理。")
        loaded_suggestions = {"remove_comments": True}
    else:
        try:
            with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
                loaded_suggestions = json.load(f)
            if "error" in loaded_suggestions and loaded_suggestions["error"]:
                print(f"警告：优化建议文件包含错误：{loaded_suggestions['error']}. 将尝试使用其余建议。")
        except Exception as e:
            print(f"错误：无法读取优化建议文件 '{SUGGESTIONS_FILE}'：{e}. 将使用默认的基本清理。")
            loaded_suggestions = {"remove_comments": True}

    html_file_name = "index.html"
    html_path = os.path.join(SOURCE_HTML_DIR, html_file_name)
    if not os.path.exists(html_path):
        print(f"错误：HTML 文件 '{html_path}' 不存在。")
        return

    # 清理之前的优化结果
    if os.path.exists(RESULT_DIR):
        for file in os.listdir(RESULT_DIR):
            file_path = os.path.join(RESULT_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"清理旧文件: {file_path}")
            except Exception as e:
                print(f"警告: 清理文件 {file_path} 时出错: {e}")

    print(f"\n开始优化 HTML for project: {PROJECT_NAME} (File: {html_file_name})")
    result = optimize_html(html_path, loaded_suggestions)

    report = {
        "project_name": PROJECT_NAME, "html_file": html_file_name,
        "optimization_status": result["status"],
        "before_optimization": result["before_optimization"],
        "after_optimization": result["after_optimization"],
        "changes": result["changes"], "modifications": result["modifications"],
        "html_minifier_applied": result["html_minifier_applied"],
        "error": result.get("error", "")
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f_report:
        json.dump(report, f_report, indent=4, ensure_ascii=False)
    print(f"优化报告已保存到 {REPORT_FILE}")

    # 生成 CSV 文件
    csv_data = [
        ["Metric", "Before Optimization", "After Optimization", "Change"],
        ["total_tags", result["before_optimization"].get("total_tags", 0), result["after_optimization"].get("total_tags", 0), result["changes"].get("tags_reduced", 0)],
        ["comment_count", result["before_optimization"].get("comment_count", 0), result["after_optimization"].get("comment_count", 0), result["changes"].get("comments_reduced", 0)],
        ["max_nesting_depth", result["before_optimization"].get("max_nesting_depth", 0), result["after_optimization"].get("max_nesting_depth", 0), result["changes"].get("max_depth_reduced", 0)],
        ["empty_tag_count", result["before_optimization"].get("empty_tag_count", 0), result["after_optimization"].get("empty_tag_count", 0), result["changes"].get("empty_tags_reduced", 0)],
        ["total_attributes", result["before_optimization"].get("total_attributes", 0), result["after_optimization"].get("total_attributes", 0), result["changes"].get("attributes_reduced", 0)],
        ["file_size_bytes", result["before_optimization"].get("file_size_bytes", 0), result["after_optimization"].get("file_size_bytes", 0), result["changes"].get("size_reduction_bytes", 0)]
    ]
    with open(CSV_REPORT_FILE, 'w', newline='', encoding='utf-8') as f_csv:
        writer = csv.writer(f_csv)
        writer.writerows(csv_data)
    print(f"CSV 优化报告已保存到 {CSV_REPORT_FILE}")

if __name__ == "__main__":
    try:
        import bs4
        import lxml
    except ImportError as e:
        missing_module = str(e).split("No module named ")[-1].strip("'")
        print(f"错误：缺少必要的库 {missing_module}。请运行 'pip install beautifulsoup4 lxml'")
        sys.exit(1)
    main()