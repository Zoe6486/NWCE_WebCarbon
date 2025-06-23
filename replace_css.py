import os
import shutil
import argparse

def replace_and_copy_site(project_name, group):
    original_dir = os.path.join("original_sites", project_name)
    optimized_css_path = os.path.join("css_optimizer","css_optimized", project_name, group, "style.css")
    output_dir = os.path.join("css_optimizer","websites_opti_css", project_name, group)

    # 路径验证
    if not os.path.exists(original_dir):
        print(f"❌ 原始目录不存在: {original_dir}")
        return
    if not os.path.exists(optimized_css_path):
        print(f"❌ 优化后的 style.css 不存在: {optimized_css_path}")
        return

    # 拷贝整个目录
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    shutil.copytree(original_dir, output_dir)
    print(f"📁 已复制 {original_dir} 到 {output_dir}")

    # 替换 CSS 文件
    target_css_path = os.path.join(output_dir, "assets", "css", "style.css")
    if os.path.exists(target_css_path):
        shutil.copyfile(optimized_css_path, target_css_path)
        print(f"✅ 已用优化后的 CSS 替换：{target_css_path}")
    else:
        print(f"⚠️ 目标 CSS 文件不存在：{target_css_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="复制原始站点并替换优化后的 CSS")
    parser.add_argument("project_name", help="项目名，如 site3")
    parser.add_argument("--group", default="cleancss", help="优化方式文件夹名，默认是 cleancss")
    args = parser.parse_args()

    replace_and_copy_site(args.project_name, args.group)
