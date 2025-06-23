import os
import sys
import shutil
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import WEBSITES_ORIGINAL_DIR, JS_OPTI_DIR

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python js_replace.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

SOURCE_PROJECT_DIR = os.path.join(WEBSITES_ORIGINAL_DIR, PROJECT_NAME)
SOURCE_JS_DIR = os.path.join(JS_OPTI_DIR, "js_optimized", PROJECT_NAME)
RESULT_DIR = os.path.join(JS_OPTI_DIR, "websites_optimized", PROJECT_NAME)

# --- 主逻辑 ---
def main():
    """
    将优化后的 JS 文件替换回项目目录。
    """
    if not os.path.exists(SOURCE_PROJECT_DIR):
        print(f"错误：源项目目录 '{SOURCE_PROJECT_DIR}' 不存在。")
        return

    if not os.path.exists(SOURCE_JS_DIR):
        print(f"错误：优化后的 JS 目录 '{SOURCE_JS_DIR}' 不存在。")
        return

    js_path = os.path.join(SOURCE_JS_DIR, "script.js")
    if not os.path.exists(js_path):
        print(f"错误：优化后的 JS 文件 '{js_path}' 不存在。")
        return

    # 复制整个项目目录
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
    shutil.copytree(SOURCE_PROJECT_DIR, RESULT_DIR)
    print(f"已复制项目从 {SOURCE_PROJECT_DIR} 到 {RESULT_DIR}")

    # 替换 JS 文件
    dest_js_path = os.path.join(RESULT_DIR, "assets", "js", "script.js")
    os.makedirs(os.path.dirname(dest_js_path), exist_ok=True)
    shutil.copy2(js_path, dest_js_path)
    print(f"已替换 JS 文件到 {dest_js_path}")

if __name__ == "__main__":
    main()