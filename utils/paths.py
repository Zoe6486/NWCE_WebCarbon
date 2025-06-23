import os
from pathlib import Path

# --- 配置区域 ---
# 使用 OpenAI 官方 API 端点
API_BASE_URL = "https://api.openai.com/v1"  
API_KEY = os.getenv("OPENAI_API_KEY") # 使bought from OpenAI website

# 写死根目录（基于之前的截图）
ROOT_DIR = Path("C:/Users/user/Desktop/web_carbon")

# 定义常用路径
PYTHON_SCRIPTS_DIR = ROOT_DIR / "python_scripts"
VENV_DIR = ROOT_DIR / "venv"
NODE_MODULES_DIR = ROOT_DIR / "node_modules"

# 输入输出目录
# HTML 优化目录
HTML_OPTI_DIR = ROOT_DIR / "1_html_opti_results"


# CSS 优化目录
CSS_OPTI_DIR = ROOT_DIR / "2_css_opti_results"


# JS 优化目录（子目录与 HTML 和 CSS 一致）
JS_OPTI_DIR = ROOT_DIR / "3_js_opti_results"


# Image 优化目录（子目录与 HTML 和 CSS 一致）
IMAGE_OPTI_DIR = ROOT_DIR / "4_image_opti_results"


# 其他目录
ACTION_CALC_DIR = ROOT_DIR / "5_action_carbon_results"
FULL_OPTI_DIR = ROOT_DIR / "6_full_opti_results"
WEBSITES_ORIGINAL_DIR = ROOT_DIR / "websites_original"
FULL_CARBON_DIR = ROOT_DIR / "7_full_carbon_report"
CUSTOM_SCRIPT_DIR= ROOT_DIR / "scripts"
DATA_DIR= ROOT_DIR / "data"

# test dir
WT_OR = ROOT_DIR / "wt_or"
WT_OT = ROOT_DIR / "wt_ot"

# 确保路径存在
def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

# 初始化所有输出目录
def init_dirs():
    for directory in [
        API_BASE_URL,API_KEY,ROOT_DIR, PYTHON_SCRIPTS_DIR, VENV_DIR, NODE_MODULES_DIR, HTML_OPTI_DIR,
        CSS_OPTI_DIR, JS_OPTI_DIR, IMAGE_OPTI_DIR, ACTION_CALC_DIR, FULL_OPTI_DIR,
        WEBSITES_ORIGINAL_DIR, FULL_CARBON_DIR, WT_OR, WT_OT,CUSTOM_SCRIPT_DIR,DATA_DIR
    ]:
        ensure_dir(directory)
        