import os
import sys
import shutil
import urllib.request
import urllib.parse
import argparse
import re
from bs4 import BeautifulSoup
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import WEBSITES_ORIGINAL_DIR, FULL_OPTI_DIR

# ===== 命令行参数检查 =====
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python extract_images.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

# ===== 路径统一变量定义 =====

SOURCE_TEMP_DIR= FULL_OPTI_DIR / "temp" /PROJECT_NAME/ "image"
SOURCE_PROJECT_DIR = os.path.join(WEBSITES_ORIGINAL_DIR, PROJECT_NAME)
HTML_FILE_PATH = os.path.join(SOURCE_PROJECT_DIR, "index.html")
RESULT_DIR = os.path.join(SOURCE_TEMP_DIR, "images_original",)

# ===== 工具函数 =====
def sanitize_filename(filename):
    filename = filename.split('?')[0].split('#')[0]
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return filename[:200]

def extract_images_from_site():
    if not os.path.exists(HTML_FILE_PATH):
        print(f"HTML 文件未找到: {HTML_FILE_PATH}")
        return

    os.makedirs(RESULT_DIR, exist_ok=True)
    print(f"输出目录: {RESULT_DIR}")

    processed_image_urls = set()

    def process_image(src_url, reference_base_path):
        if not src_url or src_url.lower().startswith('data:'):
            return

        original_src_for_log = src_url
        src_url = src_url.strip()

        if src_url.lower().endswith(".svg"):
            print(f"  跳过 SVG 图像: {original_src_for_log}")
            return

        if src_url in processed_image_urls:
            return

        img_name_from_url = os.path.basename(urllib.parse.unquote(src_url.split('?')[0].split('#')[0]))
        if not img_name_from_url:
            return
        if img_name_from_url.lower().endswith(".svg"):
            print(f"  跳过 SVG 图像（基于文件名）: {original_src_for_log}")
            return

        sanitized_img_name = sanitize_filename(img_name_from_url)
        output_path = os.path.join(RESULT_DIR, sanitized_img_name)

        if src_url.startswith(('http://', 'https://')):
            try:
                print(f"  下载远程图片: {src_url}")
                urllib.request.urlretrieve(src_url, output_path)
                print(f"    下载完成: {output_path}")
                processed_image_urls.add(src_url)
            except Exception as e:
                print(f"    下载失败 {src_url}: {e}")
        else:
            relative_src_path = os.path.normpath(os.path.join(os.path.dirname(reference_base_path), src_url))
            abs_src_path = os.path.join(SOURCE_PROJECT_DIR, relative_src_path)

            if not os.path.exists(abs_src_path):
                abs_src_path = os.path.normpath(os.path.join(os.path.dirname(HTML_FILE_PATH), src_url))

            if os.path.exists(abs_src_path) and os.path.isfile(abs_src_path):
                try:
                    print(f"  拷贝本地图片: {original_src_for_log} → {abs_src_path}")
                    shutil.copy2(abs_src_path, output_path)
                    print(f"    拷贝成功: {output_path}")
                    processed_image_urls.add(src_url)
                except Exception as e:
                    print(f"    拷贝失败 {abs_src_path}: {e}")
            else:
                print(f"    本地图片未找到或无效: {abs_src_path}（源: '{original_src_for_log}' from '{reference_base_path}'）")

    # --- HTML 图片提取 ---
    print(f"\n处理 HTML 文件: {HTML_FILE_PATH}")
    with open(HTML_FILE_PATH, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    for img_tag in soup.find_all('img'):
        if img_tag.get('src'):
            process_image(img_tag['src'], HTML_FILE_PATH)
        if img_tag.get('srcset'):
            for s_item in img_tag['srcset'].split(','):
                s_url = s_item.strip().split(' ')[0]
                if s_url:
                    process_image(s_url, HTML_FILE_PATH)

    for link_tag in soup.find_all('link', href=True):
        rels = link_tag.get('rel', [])
        if any(r in rels for r in ['icon', 'shortcut icon', 'apple-touch-icon', 'preload']) or \
           link_tag.get('as') == 'image':
            process_image(link_tag['href'], HTML_FILE_PATH)

    for picture_tag in soup.find_all('picture'):
        for source_tag in picture_tag.find_all('source'):
            srcset = source_tag.get('srcset')
            if srcset:
                s_url = srcset.strip().split(' ')[0]
                process_image(s_url, HTML_FILE_PATH)
        img_fallback = picture_tag.find('img')
        if img_fallback and img_fallback.get('src'):
            process_image(img_fallback['src'], HTML_FILE_PATH)

    for tag in soup.find_all(style=True):
        style_attr = tag['style']
        matches = re.findall(r'url\s*\((?![\'"]?data:)([^)]+)\)', style_attr, re.IGNORECASE)
        for match_group in matches:
            img_url = match_group.strip(' \'"')
            if img_url:
                process_image(img_url, HTML_FILE_PATH)

    for link_tag in soup.find_all('link', rel='stylesheet', href=True):
        css_href = link_tag['href']
        if css_href.startswith(('http://', 'https://')):
            continue

        css_path = os.path.normpath(os.path.join(os.path.dirname(HTML_FILE_PATH), css_href))
        if os.path.exists(css_path):
            print(f"\n处理 CSS 文件: {css_path}")
            try:
                with open(css_path, 'r', encoding='utf-8') as css_file:
                    css_content = css_file.read()
                css_img_urls = re.findall(r'url\s*\((?![\'"]?data:)([^)]+)\)', css_content, re.IGNORECASE)
                for img_url in css_img_urls:
                    img_url = img_url.strip(' \'"')
                    if img_url:
                        process_image(img_url, css_path)
            except Exception as e:
                print(f"  CSS 处理失败 {css_path}: {e}")
        else:
            print(f"  CSS 文件未找到: {css_path}（href='{css_href}'）")

    if not processed_image_urls:
        print(f"未提取到图片（非 SVG）: {PROJECT_NAME}")
    else:
        print(f"\n图片提取完成: {PROJECT_NAME}，共提取 {len(processed_image_urls)} 张图片。")

# ===== 主程序入口 =====
if __name__ == "__main__":
    extract_images_from_site()
