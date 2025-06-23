import os
import sys
import shutil
import argparse
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import FULL_OPTI_DIR

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python css_replace.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

# 路径统一变量定义

SOURCE_TEMP_DIR= FULL_OPTI_DIR / "temp" /PROJECT_NAME/ "css"

# 1. 被替换的项目来源
SOURCE_PROJECT_DIR = FULL_OPTI_DIR / "temp" /PROJECT_NAME/ "html" / "websites_optimized"
# 2 .用来替换的优化后的css文件
OPTIMIZED_CSS_PATH = SOURCE_TEMP_DIR / "css_optimized"  / "style.css"
# 3. 完成替换后的网页项目
RESULT_DIR = SOURCE_TEMP_DIR / "websites_optimized" 



def replace_css_references(project_name):
    """
    复制原始项目目录到目标目录，并用优化后的 CSS 文件替换目标目录中的原始 CSS 文件。
    """
    # 检查源项目目录是否存在
    if not os.path.exists(SOURCE_PROJECT_DIR):
        print(f"错误：源项目目录 '{SOURCE_PROJECT_DIR}' 不存在。")
        return

    # 检查优化后的 CSS 文件是否存在
    if not os.path.exists(OPTIMIZED_CSS_PATH):
        print(f"错误：优化后的 CSS 文件 '{OPTIMIZED_CSS_PATH}' 不存在。")
        return

    # 复制整个项目目录
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
        print(f"已删除旧目标目录: {RESULT_DIR}")
    shutil.copytree(SOURCE_PROJECT_DIR, RESULT_DIR)
    print(f"已复制项目：{SOURCE_PROJECT_DIR} → {RESULT_DIR}")

    # 查找并替换目标目录中的所有 CSS 文件
    css_files_replaced = 0
    for root, _, files in os.walk(RESULT_DIR):
        for file in files:
            if file.endswith('.css'):
                source_css_path = os.path.join(root, file)
                # 替换为优化后的 CSS 文件
                shutil.copy2(OPTIMIZED_CSS_PATH, source_css_path)
                print(f"已替换 CSS 文件: {source_css_path} → {OPTIMIZED_CSS_PATH}")
                css_files_replaced += 1

    if css_files_replaced == 0:
        print(f"警告：目标目录 '{RESULT_DIR}' 中未找到任何 CSS 文件。")
    else:
        print(f"总共替换了 {css_files_replaced} 个 CSS 文件。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="复制项目并替换为优化后的 CSS 文件。")
    parser.add_argument("project_name", help="项目文件夹名称 (如 'crafti')")
    args = parser.parse_args()

    replace_css_references(args.project_name)