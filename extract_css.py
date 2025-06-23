import os
import shutil
import argparse

def extract_css(project_name):
    # 源路径
    src_css = os.path.join("original_sites", project_name, "assets", "css", "style.css")
    # 目标路径ff
    dst_dir = os.path.join("css_optimizer", "css_original", project_name)
    dst_css = os.path.join(dst_dir, "style.css")

    if not os.path.exists(src_css):
        print(f"❌ 找不到源 CSS 文件: {src_css}")
        return

    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(src_css, dst_css)
    print(f"✅ 已将 CSS 拷贝到: {dst_css}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 original_sites 中提取 style.css 到 css_optimizer/css_original")
    parser.add_argument("project_name", help="项目名，例如 site3")
    args = parser.parse_args()

    extract_css(args.project_name)
