import os
from pathlib import Path
from bs4 import BeautifulSoup
import shutil
import urllib.request
import argparse
import re
import cssutils

# 配置 cssutils 忽略警告
cssutils.log.setLevel('ERROR')
cssutils.ser.prefs.useMinified()

def extract_images_from_html(html_path, project_name, base_output_dir="images_ai/images_original"):
    output_dir = os.path.join(base_output_dir, project_name)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(html_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    extracted_images = set()

    def process_image(src):
        if not src:
            return

        src = src.split('?')[0].split('#')[0]
        img_name = os.path.basename(src)
        if img_name in extracted_images:
            print(f"Skipping duplicate: {img_name}")
            return

        if src.startswith(('http://', 'https://')):
            print(f"Skipping remote image: {src}")
            return

        src_path = os.path.join(os.path.dirname(html_path), src)
        actual_path = None
        for fname in os.listdir(os.path.dirname(src_path)):
            if fname.lower() == os.path.basename(src_path).lower():
                actual_path = os.path.join(os.path.dirname(src_path), fname)
                break
        if actual_path and os.path.exists(actual_path):
            output_path = os.path.join(output_dir, img_name)
            shutil.copy2(actual_path, output_path)
            print(f"Copied: {img_name} to {output_path}")
            extracted_images.add(img_name)
        else:
            print(f"Local image not found: {src_path}")

    # 1. Extract from <img> tags
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            process_image(src)

    # 2. Extract from <link> tags with as="image"
    for link in soup.find_all('link', {'as': 'image'}):
        href = link.get('href')
        if href:
            process_image(href)

    # 3. Extract from <picture> tags
    for picture in soup.find_all('picture'):
        for source in picture.find_all('source'):
            srcset = source.get('srcset')
            if srcset:
                for entry in srcset.split(','):
                    img_url = entry.strip().split(' ')[0]
                    process_image(img_url)

    # 4. Extract from inline style attributes
    for tag in soup.find_all(True):
        style = tag.get('style')
        if style and 'background-image' in style:
            match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
            if match:
                img_url = match.group(1)
                process_image(img_url)

    # 5. Extract from <style> tags
    for style_tag in soup.find_all('style'):
        css_content = style_tag.string
        if css_content:
            try:
                sheet = cssutils.parseString(css_content, validate=False)
                for rule in sheet:
                    if rule.type == rule.STYLE_RULE:
                        for prop in rule.style:
                            if prop.name in ('background', 'background-image'):
                                match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', prop.value)
                                if match:
                                    img_url = match.group(1)
                                    process_image(img_url)
            except Exception as e:
                print(f"Error parsing <style> tag CSS: {e}")

    # 6. Extract from local CSS files only
    css_links = soup.find_all('link', rel='stylesheet')
    for link in css_links:
        css_href = link.get('href')
        if css_href:
            if css_href.startswith(('http://', 'https://')):
                print(f"Skipping remote CSS file: {css_href}")
                continue
            css_path = os.path.join(os.path.dirname(html_path), css_href)
            if not os.path.exists(css_path):
                print(f"CSS file not found: {css_path}")
                continue
            try:
                with open(css_path, 'r', encoding='utf-8') as css_file:
                    css_content = css_file.read()
                sheet = cssutils.parseString(css_content, validate=False)
                for rule in sheet:
                    if rule.type == rule.STYLE_RULE:
                        for prop in rule.style:
                            if prop.name in ('background', 'background-image'):
                                match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', prop.value)
                                if match:
                                    img_url = match.group(1)
                                    process_image(img_url)
            except Exception as e:
                print(f"Error parsing CSS file {css_path}: {e}")

    # 7. Enhanced extraction from JavaScript
    def extract_from_js_content(js_content):
        if not js_content:
            return

        # 匹配直接引用的图片URL
        matches = re.findall(r'[\'"]([^\'"]*\.(?:png|jpg|jpeg|gif|bmp))[\'"]', js_content, re.IGNORECASE)
        for img_url in matches:
            process_image(img_url)

        # 匹配包含 /assets/images/ 的路径（可能动态拼接）
        path_matches = re.findall(r'[\'"]([^\'"]*/assets/images/[^\'"]*)[\'"]', js_content, re.IGNORECASE)
        for path in path_matches:
            if path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                process_image(path)
            else:
                local_path = os.path.join(os.path.dirname(html_path), path)
                if os.path.exists(local_path) and os.path.isdir(local_path):
                    for fname in os.listdir(local_path):
                        if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                            process_image(os.path.join(path, fname))

        # 尝试匹配变量名或拼接的图片名（针对缺失的图片）
        possible_filenames = re.findall(r'[\'"]([^\'"]*(?:contacting1|video_thumbnail|world-book-day)[^\'"]*)[\'"]', js_content, re.IGNORECASE)
        for fname in possible_filenames:
            potential_path = f"./assets/images/{fname}.png"
            process_image(potential_path)
            potential_path = f"./assets/images/{fname}.jpg"
            process_image(potential_path)

        # 匹配任何可能是图片文件名的字符串（不带路径），并尝试补全路径
        filename_matches = re.findall(r'[\'"]([^\'"/]+\.(?:png|jpg|jpeg|gif|bmp))[\'"]', js_content, re.IGNORECASE)
        for fname in filename_matches:
            potential_path = f"./assets/images/{fname}"
            process_image(potential_path)

    # 7.1 Extract from inline <script> tags
    script_tags = soup.find_all('script')
    for script_tag in script_tags:
        script_content = script_tag.string
        extract_from_js_content(script_content)

    # 7.2 Extract from local JavaScript files
    for script in soup.find_all('script', src=True):
        src = script.get('src')
        if src:
            if src.startswith(('http://', 'https://')):
                print(f"Skipping remote JavaScript file: {src}")
                continue
            js_path = os.path.join(os.path.dirname(html_path), src)
            if not os.path.exists(js_path):
                print(f"JavaScript file not found: {js_path}")
                continue
            try:
                with open(js_path, 'r', encoding='utf-8') as js_file:
                    js_content = js_file.read()
                extract_from_js_content(js_content)
            except Exception as e:
                print(f"Error parsing JavaScript file {js_path}: {e}")

    if not extracted_images:
        print("No images found in the HTML file, <style> tags, CSS files, or JavaScript.")
    return extracted_images

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract images from a static HTML file.")
    parser.add_argument("project_name", help="Name of the project folder (e.g., 'site3')")
    args = parser.parse_args()

    html_file = os.path.join("original_sites", args.project_name, "index.html")
    
    if not os.path.exists(html_file):
        print(f"HTML file not found: {html_file}")
    else:
        extract_images_from_html(html_file, args.project_name, base_output_dir="images_ai/images_original")