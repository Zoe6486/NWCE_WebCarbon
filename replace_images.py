import os
import shutil
import argparse
from pathlib import Path
from bs4 import BeautifulSoup
import re

def replace_image_references(project_name, base_input_dir="original_sites", base_output_dir="images_ai/websites_opti_img", compressed_images_dir="images_ai/images_optimized"):
    # Define source and destination project directories
    src_project_dir = os.path.join(base_input_dir, project_name)
    # dest_project_dir = os.path.join(base_output_dir, project_name)
    dest_project_dir = os.path.join(base_output_dir, f"{project_name}_i")


    # Check if source project directory exists
    if not os.path.exists(src_project_dir):
        print(f"Source project directory not found: {src_project_dir}")
        return

    # Remove destination directory if it exists, then copy the entire project
    if os.path.exists(dest_project_dir):
        shutil.rmtree(dest_project_dir)
    shutil.copytree(src_project_dir, dest_project_dir)
    print(f"Copied project from {src_project_dir} to {dest_project_dir}")

    # Path to the HTML file in the destination directory
    html_file = os.path.join(dest_project_dir, "index.html")
    if not os.path.exists(html_file):
        print(f"HTML file not found: {html_file}")
        return

    # Read the HTML file
    with open(html_file, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    # Directory containing compressed images
    compressed_project_images_dir = os.path.join(compressed_images_dir, project_name)

    # Function to replace image extension and copy the compressed image
    def replace_image_path(src):
        if not src or src.startswith(('http://', 'https://')):
            return src, False

        # Get the image filename (e.g., hero-slider-1.jpg)
        img_name = os.path.basename(src)
        # Convert to WebP filename
        webp_name = f"{Path(img_name).stem}.webp"
        # Path to the compressed image
        compressed_img_path = os.path.join(compressed_project_images_dir, webp_name)

        if os.path.exists(compressed_img_path):
            # Construct the new path by replacing the original extension with .webp
            new_src = src.rsplit('.', 1)[0] + '.webp'
            # Copy the compressed image to the destination project
            original_img_dir = os.path.dirname(os.path.join(dest_project_dir, src))
            new_img_path = os.path.join(original_img_dir, webp_name)
            os.makedirs(original_img_dir, exist_ok=True)
            shutil.copy2(compressed_img_path, new_img_path)
            print(f"Copied compressed image: {new_img_path}")

            # Remove the original image file if it exists
            original_img_base_dir = os.path.dirname(os.path.join(dest_project_dir, src))
            original_img_base_name = Path(img_name).stem
            original_removed = False
            for fname in os.listdir(original_img_base_dir):
                if fname.lower().startswith(original_img_base_name.lower()) and fname.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    original_img_path = os.path.join(original_img_base_dir, fname)
                    if os.path.exists(original_img_path):
                        os.remove(original_img_path)
                        print(f"Removed original image: {original_img_path}")
                        original_removed = True
            if not original_removed:
                print(f"No matching original image found for: {img_name}")

            return new_src, True
        else:
            print(f"Compressed image not found: {compressed_img_path}")
            return src, False

    # 1. Replace images in <img> tags
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            new_src, updated = replace_image_path(src)
            if updated:
                img['src'] = new_src

    # 2. Replace images in <link> tags with as="image"
    for link in soup.find_all('link', {'as': 'image'}):
        href = link.get('href')
        if href:
            new_href, updated = replace_image_path(href)
            if updated:
                link['href'] = new_href

    # 3. Replace images in <picture> tags (if any)
    for picture in soup.find_all('picture'):
        for source in picture.find_all('source'):
            srcset = source.get('srcset')
            if srcset:
                # Handle simple srcset (single image, no descriptors)
                new_srcset, updated = replace_image_path(srcset)
                if updated:
                    source['srcset'] = new_srcset

    # 4. Replace images in style attributes (e.g., background-image)
    for tag in soup.find_all(True):  # Find all tags
        style = tag.get('style')
        if style and 'background-image' in style:
            # Extract the URL from background-image
            match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
            if match:
                old_url = match.group(1)
                new_url, updated = replace_image_path(old_url)
                if updated:
                    # Replace the URL in the style attribute
                    new_style = style.replace(old_url, new_url)
                    tag['style'] = new_style
                    print(f"Updated style attribute: {old_url} to {new_url}")

    # 5. Replace images in <style> tags
    for style_tag in soup.find_all('style'):
        css_content = style_tag.string
        if css_content:
            new_css_content = css_content
            matches = re.findall(r'url\([\'"]?(.*?)[\'"]?\)', css_content)
            for src in matches:
                if not src.startswith(('http://', 'https://')):
                    new_src, updated = replace_image_path(src)
                    if updated:
                        new_css_content = new_css_content.replace(src, new_src)
                        print(f"Updated <style> tag: {src} to {new_src}")
            style_tag.string = new_css_content

    # 6. Replace images in external CSS files
    css_links = soup.find_all('link', rel='stylesheet')
    for link in css_links:
        css_href = link.get('href')
        if css_href and not css_href.startswith(('http://', 'https://')):
            css_path = os.path.join(dest_project_dir, css_href)
            if os.path.exists(css_path):
                with open(css_path, 'r', encoding='utf-8') as css_file:
                    css_content = css_file.read()
                new_css_content = css_content
                matches = re.findall(r'url\([\'"]?(.*?)[\'"]?\)', css_content)
                for src in matches:
                    if not src.startswith(('http://', 'https://')):
                        new_src, updated = replace_image_path(src)
                        if updated:
                            new_css_content = new_css_content.replace(src, new_src)
                            print(f"Updated CSS file {css_path}: {src} to {new_src}")
                with open(css_path, 'w', encoding='utf-8') as css_file:
                    css_file.write(new_css_content)
    # 7. 替换本地 JS 文件中的图片路径
    js_links = [tag.get('src') for tag in soup.find_all('script', src=True) if tag.get('src') and not tag['src'].startswith(('http://', 'https://'))]
    for js_href in js_links:
        js_path = os.path.join(dest_project_dir, js_href)
        if os.path.exists(js_path):
            with open(js_path, 'r', encoding='utf-8') as js_file:
                js_content = js_file.read()
            new_js_content = js_content
            matches = re.findall(r'[\'"]([^\'"]+\.(?:png|jpg|jpeg|gif|bmp))[\'"]', js_content)
            for src in matches:
                new_src, updated = replace_image_path(src)
                if updated:
                    new_js_content = new_js_content.replace(src, new_src)
                    print(f"Updated JS file {js_path}: {src} -> {new_src}")
            with open(js_path, 'w', encoding='utf-8') as js_file:
                js_file.write(new_js_content)

    # Save the modified HTML file
    with open(html_file, 'w', encoding='utf-8') as file:
        file.write(str(soup))
    print(f"Updated HTML file: {html_file}")

if __name__ == "__main__":
    # Set up argument parser for command-line input
    parser = argparse.ArgumentParser(description="Copy project and replace images with compressed versions.")
    parser.add_argument("project_name", help="Name of the project folder (e.g., 'site3')")
    args = parser.parse_args()

    # Run the replacement process
    replace_image_references(args.project_name)