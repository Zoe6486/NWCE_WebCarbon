import os
import sys
import shutil
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 现在可以正常导入 paths 模块
from paths import WEBSITES_ORIGINAL_DIR, FULL_OPTI_DIR

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python html_extract.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

SOURCE_DIR = WEBSITES_ORIGINAL_DIR / PROJECT_NAME

SOURCE_TEMP_DIR= FULL_OPTI_DIR / "temp" /PROJECT_NAME/ "html"

RESULT_DIR = SOURCE_TEMP_DIR / "html_original" 

# --- 主逻辑 ---
def main():
    """
    从源目录提取 HTML 文件并保存到目标目录。
    """
    if not os.path.exists(SOURCE_DIR):
        print(f"错误：源目录 '{SOURCE_DIR}' 不存在。")
        return

    html_path = SOURCE_DIR / "index.html"
    if not os.path.exists(html_path):
        print(f"错误：HTML 文件 '{html_path}' 不存在。")
        return

    # 复制 HTML 文件到目标目录
    os.makedirs(RESULT_DIR, exist_ok=True)
    dest_html_path = RESULT_DIR / "index.html"
    shutil.copy2(html_path, dest_html_path)
    print(f"已提取 HTML 文件到 {dest_html_path}")

if __name__ == "__main__":
    main()