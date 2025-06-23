import os
import subprocess
import sys

ORIGINAL_DIR = "original_sites"

python_executable = sys.executable  # 当前运行脚本的 Python 路径

site_list = [d for d in os.listdir(ORIGINAL_DIR) if os.path.isdir(os.path.join(ORIGINAL_DIR, d))]

for site in site_list:
    print(f"\n🔄 正在处理网站: {site}")

    # 依次运行三个脚本，参数是当前site名
    subprocess.run([python_executable, "images_ai/extract_images.py", site], check=True)
    subprocess.run([python_executable, "images_ai/compress_image.py", site], check=True)
    subprocess.run([python_executable, "images_ai/replace_images.py", site], check=True)
