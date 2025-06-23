import os
import shutil
import argparse
import sys
import glob
from bs4 import BeautifulSoup
import re
from pathlib import Path
# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import WEBSITES_ORIGINAL_DIR, IMAGE_OPTI_DIR

# 依赖检查
try:
    import bs4
except ImportError:
    print("错误：beautifulsoup4 库未安装。请运行 'pip install beautifulsoup4'")
    sys.exit(1)

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python image_optimize.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

# ===== 路径统一变量定义 =====

SOURCE_PROJECT_DIR = os.path.join(WEBSITES_ORIGINAL_DIR, PROJECT_NAME)
SOURCE_IMAGES_DIR = os.path.join(IMAGE_OPTI_DIR, "images_optimized", PROJECT_NAME)
RESULT_DIR = os.path.join(IMAGE_OPTI_DIR, "websites_optimized", PROJECT_NAME)

SOURCE_HTML_PATH = os.path.join(RESULT_DIR, "index.html")

def replace_image_references(project_name):
    print(f"调试: 源项目目录: {SOURCE_PROJECT_DIR}")
    print(f"调试: 目标项目目录: {RESULT_DIR}")

    if not os.path.exists(SOURCE_PROJECT_DIR):
        print(f"源项目目录不存在: {SOURCE_PROJECT_DIR}")
        return

    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
        print(f"已删除旧目标目录: {RESULT_DIR}")
    shutil.copytree(SOURCE_PROJECT_DIR, RESULT_DIR)
    print(f"已复制项目：{SOURCE_PROJECT_DIR} → {RESULT_DIR}")

    
    if not os.path.exists(SOURCE_HTML_PATH):
        print(f"HTML 文件不存在: {SOURCE_HTML_PATH}")
        return

    with open(SOURCE_HTML_PATH, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    def replace_image_path(src):
        if not src or src.startswith(('http://', 'https://')):
            return src, False

        img_name = os.path.basename(src)
        base_name = Path(img_name).stem
        compressed_img_pattern = os.path.join(SOURCE_IMAGES_DIR, f"{base_name}.*")
        matched_files = glob.glob(compressed_img_pattern)

        if matched_files:
            compressed_file = matched_files[0]
            new_ext = os.path.splitext(compressed_file)[1]
            new_img_name = f"{base_name}{new_ext}"
            new_src = src.rsplit('.', 1)[0] + new_ext

            original_img_dir = os.path.dirname(os.path.join(RESULT_DIR, src))
            new_img_path = os.path.join(original_img_dir, new_img_name)
            os.makedirs(original_img_dir, exist_ok=True)
            shutil.copy2(compressed_file, new_img_path)
            print(f"复制压缩图像: {new_img_path}")

            original_img_path = os.path.join(RESULT_DIR, src)
            if os.path.exists(original_img_path):
                os.remove(original_img_path)
                print(f"已删除原始图像: {original_img_path}")

            return new_src, True
        else:
            print(f"未找到压缩图像: {img_name}")
            return src, False

    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            new_src, updated = replace_image_path(src)
            if updated:
                img['src'] = new_src

    for link in soup.find_all('link', {'as': 'image'}):
        href = link.get('href')
        if href:
            new_href, updated = replace_image_path(href)
            if updated:
                link['href'] = new_href

    for picture in soup.find_all('picture'):
        for source in picture.find_all('source'):
            srcset = source.get('srcset')
            if srcset:
                new_srcset, updated = replace_image_path(srcset)
                if updated:
                    source['srcset'] = new_srcset

    for tag in soup.find_all(True):
        style = tag.get('style')
        if style and 'background-image' in style:
            match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
            if match:
                old_url = match.group(1)
                new_url, updated = replace_image_path(old_url)
                if updated:
                    tag['style'] = style.replace(old_url, new_url)
                    print(f"更新 style 属性: {old_url} → {new_url}")

    with open(SOURCE_HTML_PATH, 'w', encoding='utf-8') as file:
        file.write(str(soup))
    print(f"已更新 HTML 文件: {SOURCE_HTML_PATH}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="复制项目并替换为压缩图片。")
    parser.add_argument("project_name", help="项目文件夹名称 (如 'grilli')")
    args = parser.parse_args()

    replace_image_references(args.project_name)