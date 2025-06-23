import os
import sys
import shutil
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import WEBSITES_ORIGINAL_DIR, FULL_OPTI_DIR

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python css_extract.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

SOURCE_TEMP_DIR= FULL_OPTI_DIR / "temp" /PROJECT_NAME/ "css"

# 源 CSS 文件通常在 assets/css/ 目录下
SOURCE_CSS_PARENT_DIR = WEBSITES_ORIGINAL_DIR / PROJECT_NAME / "assets" / "css"
# 源 HTML 文件在项目根目录下
SOURCE_HTML_PARENT_DIRS = WEBSITES_ORIGINAL_DIR / PROJECT_NAME  # 根目录
# 目标目录，用于存放提取的原始 CSS 和 HTML 文件
RESULT_DIR = SOURCE_TEMP_DIR / "css_original" 

# --- 辅助函数：提取文件 ---
def extract_files(source_dirs, target_dir, file_extension):
    """
    从指定源目录提取指定扩展名的文件到目标目录。
    Args:
        source_dirs (list): 源目录列表
        target_dir (str): 目标目录
        file_extension (str): 文件扩展名（如 ".css" 或 ".html"）
    Returns:
        int: 提取的文件数量
    """
    files_found = 0
    os.makedirs(target_dir, exist_ok=True)
    print(f"创建/确认目标目录: {target_dir}")

    for source_dir in source_dirs:
        if not os.path.exists(source_dir):
            print(f"警告：源目录 '{source_dir}' 不存在，跳过。")
            continue
        if not os.path.isdir(source_dir):
            print(f"警告：指定的源路径 '{source_dir}' 不是一个目录，跳过。")
            continue

        for item_name in os.listdir(source_dir):
            source_item_path = os.path.join(source_dir, item_name)
            if os.path.isfile(source_item_path) and item_name.lower().endswith(file_extension):
                destination_item_path = os.path.join(target_dir, item_name)
                try:
                    shutil.copy2(source_item_path, destination_item_path)
                    print(f"已提取 {file_extension[1:].upper()} 文件: {item_name} 到 {destination_item_path}")
                    files_found += 1
                except Exception as e:
                    print(f"复制文件 {item_name} 时出错: {e}")

    return files_found

# --- 主逻辑 ---
def main():
    """
    从源项目目录提取所有 CSS 和 HTML 文件并保存到目标目录。
    """
    # 提取 CSS 文件
    css_files_found = extract_files([SOURCE_CSS_PARENT_DIR], RESULT_DIR, ".css")
    if css_files_found == 0:
        print(f"在目录 '{SOURCE_CSS_PARENT_DIR}' 中没有找到 CSS 文件。")
    else:
        print(f"\n共提取 {css_files_found} 个 CSS 文件到 {RESULT_DIR}")

    # 提取 HTML 文件
    html_files_found = extract_files([SOURCE_HTML_PARENT_DIRS], RESULT_DIR, ".html")
    if html_files_found == 0:
        print(f"在目录 '{SOURCE_HTML_PARENT_DIRS}' 中没有找到 HTML 文件。")
    else:
        print(f"\n共提取 {html_files_found} 个 HTML 文件到 {RESULT_DIR}")

if __name__ == "__main__":
    main()