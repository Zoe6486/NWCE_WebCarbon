import os
import sys
import shutil
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 现在可以正常导入 paths 模块
from paths import WEBSITES_ORIGINAL_DIR, HTML_OPTI_DIR

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python html_replace.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

# 源项目目录：websites_original/<project_name>
SOURCE_PROJECT_DIR = WEBSITES_ORIGINAL_DIR / PROJECT_NAME
# 优化后的 HTML 目录：1_html_opti_results/html_optimized/<project_name>
SOURCE_HTML_DIR = HTML_OPTI_DIR / "html_optimized" / PROJECT_NAME
# 目标目录：1_html_opti_results/websites_optimized/<project_name>
RESULT_DIR = HTML_OPTI_DIR / "websites_optimized" / PROJECT_NAME

# --- 主逻辑 ---
def main():
    """
    将优化后的 HTML 文件替换回项目目录。
    """
    if not os.path.exists(SOURCE_PROJECT_DIR):
        print(f"错误：源项目目录 '{SOURCE_PROJECT_DIR}' 不存在。")
        return

    if not os.path.exists(SOURCE_HTML_DIR):
        print(f"错误：优化后的 HTML 目录 '{SOURCE_HTML_DIR}' 不存在。")
        return

    html_path = SOURCE_HTML_DIR / "index.html"
    if not os.path.exists(html_path):
        print(f"错误：优化后的 HTML 文件 '{html_path}' 不存在。")
        return

    # 复制整个项目目录
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
    shutil.copytree(SOURCE_PROJECT_DIR, RESULT_DIR)
    print(f"已复制项目从 {SOURCE_PROJECT_DIR} 到 {RESULT_DIR}")

    # 替换 HTML 文件
    dest_html_path = RESULT_DIR / "index.html"
    shutil.copy2(html_path, dest_html_path)
    print(f"已替换 HTML 文件到 {dest_html_path}")

if __name__ == "__main__":
    main()