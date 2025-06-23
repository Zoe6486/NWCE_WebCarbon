import torch
from compressai.zoo import bmshj2018_factorized
from PIL import Image
import numpy as np
import os
from pathlib import Path
import argparse

def compress_image(image_path, output_dir, format="webp", quality=50):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = bmshj2018_factorized(quality=3, pretrained=True).eval().to(device)
    
    # 读取原始图像，转换为 RGB
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"Error opening {image_path}: {e}")
        return None
    
    img_tensor = torch.from_numpy(np.array(img)).permute(2, 0, 1).float() / 255.0
    img_tensor = img_tensor.unsqueeze(0).to(device)
    
    with torch.no_grad():
        # 压缩并解码
        compressed = model.compress(img_tensor)
        decompressed = model.decompress(compressed["strings"], compressed["shape"])
    
    # 处理重建图像
    decompressed_img = decompressed["x_hat"].squeeze(0).cpu()
    decompressed_img = torch.clamp(decompressed_img, 0, 1) * 255.0
    decompressed_img = decompressed_img.byte().permute(1, 2, 0).numpy()
    
    # 生成输出路径，保留原文件名，改为 WebP 格式
    file_name = Path(image_path).stem  # 获取文件名（不含扩展名）
    output_image_path = os.path.join(output_dir, f"{file_name}.webp")
    
    # 保存为 WebP
    Image.fromarray(decompressed_img).save(output_image_path, "WEBP", quality=quality)
    
    return output_image_path

def compress_all_images(project_name, base_input_dir="images_ai/images_original", base_output_dir="images_ai/images_optimized", quality=50):
    # Define project-specific input and output directories
    input_dir = os.path.join(base_input_dir, project_name)
    output_dir = os.path.join(base_output_dir, project_name)
    
    # 创建输出文件夹
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 支持的图片格式
    supported_extensions = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
    
    # 遍历输入文件夹中的所有文件
    for file_name in os.listdir(input_dir):
        input_path = os.path.join(input_dir, file_name)
        if os.path.isfile(input_path) and file_name.lower().endswith(supported_extensions):
            print(f"Processing: {input_path}")
            output_path = compress_image(input_path, output_dir, format="webp", quality=quality)
            if output_path:
                original_size = os.path.getsize(input_path) / 1024
                compressed_size = os.path.getsize(output_path) / 1024
                print(f"Original size: {original_size:.2f} KB")
                print(f"Compressed WebP size: {compressed_size:.2f} KB")
                print(f"Compressed WebP saved at: {output_path}")
            else:
                print(f"Failed to compress: {input_path}")
            print("-" * 50)

if __name__ == "__main__":
    # Set up argument parser for command-line input
    parser = argparse.ArgumentParser(description="Compress images from a project folder.")
    parser.add_argument("project_name", help="Name of the project folder (e.g., 'grilli')")
    args = parser.parse_args()

    # Define input directory based on project name
    input_dir = os.path.join("images_ai/images_original", args.project_name)
    
    if not os.path.exists(input_dir) or not os.listdir(input_dir):
        print(f"Please place images in the '{input_dir}' folder.")
    else:
        compress_all_images(args.project_name, quality=50)