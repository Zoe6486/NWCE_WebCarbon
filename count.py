# import os
# import csv
# from collections import Counter

# def count_image_formats(folder):
#     exts = []
#     for root, _, files in os.walk(folder):
#         for f in files:
#             ext = os.path.splitext(f)[1].lower()
#             if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']:
#                 exts.append(ext)
#     return Counter(exts)

# def batch_count(root_folder, output_csv):
#     project_folders = [f for f in os.listdir(root_folder) if os.path.isdir(os.path.join(root_folder, f))]
#     with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
#         fieldnames = ['project', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']
#         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#         writer.writeheader()

#         for project in project_folders:
#             folder_path = os.path.join(root_folder, project)
#             counts = count_image_formats(folder_path)
#             row = {'project': project}
#             for ext in fieldnames[1:]:
#                 row[ext] = counts.get(ext, 0)
#             writer.writerow(row)
#     print(f"统计结果已保存到 {output_csv}")

# if __name__ == "__main__":
#     root_original = "images_ai/images_original"  # 这里改成你的原始图片根目录
#     root_optimized = "images_ai/images_optimized"  # 这里改成你的优化后图片根目录

#     batch_count(root_original, "original_images_count.csv")
#     batch_count(root_optimized, "optimized_images_count.csv")
import os
import csv
from collections import defaultdict

def count_image_formats_and_size(folder):
    data = defaultdict(lambda: {'count': 0, 'size_kb': 0})
    for root, _, files in os.walk(folder):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']:
                path = os.path.join(root, f)
                size_kb = os.path.getsize(path) / 1024
                data[ext]['count'] += 1
                data[ext]['size_kb'] += size_kb
    return data

def batch_count_with_size(root_folder, output_csv):
    project_folders = [f for f in os.listdir(root_folder) if os.path.isdir(os.path.join(root_folder, f))]
    # 所有关注的图片格式，顺序固定，方便写入表头
    extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        # 列头：项目名 + 每种格式的数量和大小（KB）
        fieldnames = ['project']
        for ext in extensions:
            fieldnames.append(f'{ext}_count')
            fieldnames.append(f'{ext}_size_kb')
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for project in project_folders:
            folder_path = os.path.join(root_folder, project)
            counts_and_sizes = count_image_formats_and_size(folder_path)
            row = {'project': project}
            for ext in extensions:
                row[f'{ext}_count'] = counts_and_sizes.get(ext, {}).get('count', 0)
                row[f'{ext}_size_kb'] = round(counts_and_sizes.get(ext, {}).get('size_kb', 0), 2)
            writer.writerow(row)
    print(f"统计（数量+大小）结果已保存到 {output_csv}")

if __name__ == "__main__":
    root_original = "images_ai/images_original"  # 修改成你的原始图片根目录
    root_optimized = "images_ai/images_optimized"  # 修改成你的优化后图片根目录

    batch_count_with_size(root_original, "original_images_stats.csv")
    batch_count_with_size(root_optimized, "optimized_images_stats.csv")
