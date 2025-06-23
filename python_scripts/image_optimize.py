import os
import json
import sys
import csv
from wand.image import Image
from wand.resource import limits
from wand.color import Color # Import Color for explicit transparent background

from pathlib import Path
# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils") # Ensure this path is correct for your setup
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import IMAGE_OPTI_DIR


# 限制 ImageMagick 内存使用
limits['memory'] = 1024 * 1024 * 1024  # 1GB

# --- 配置区域 ---
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python image_optimize.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

# ===== 路径统一变量定义 =====

SOURCE_IMAGES_DIR = os.path.join(IMAGE_OPTI_DIR, "images_original", PROJECT_NAME)
SUGGESTIONS_FILE = os.path.join(IMAGE_OPTI_DIR, "image_llm_suggestions", PROJECT_NAME, "image_optimization_suggestions.json")

RESULT_DIR = os.path.join(IMAGE_OPTI_DIR, "images_optimized", PROJECT_NAME)
REPORT_FILE = os.path.join(IMAGE_OPTI_DIR, "optimization_report", PROJECT_NAME, "optimization_report.json")
CSV_REPORT_FILE = os.path.join(IMAGE_OPTI_DIR, "optimization_report", PROJECT_NAME, "optimization_summary.csv")

# --- 优化函数 ---
def optimize_image(image_path, suggestion):
    """
    根据 LLM 建议优化图片。
    """
    print(f"调试: 开始优化图片 {image_path}")
    try:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"原始图片文件不存在: {image_path}")

        # 获取原始图片信息
        original_has_alpha = False
        with Image(filename=image_path) as img_check:
            original_size = os.path.getsize(image_path)
            original_format = img_check.format.lower()
            original_width = img_check.width
            original_height = img_check.height
            original_has_alpha = img_check.alpha_channel # <<< Detect original alpha

        llm_suggestion = suggestion.get("llm_suggestion", {})
        if not llm_suggestion:
            raise ValueError("LLM 建议为空，无法优化")

        recommended_format = llm_suggestion.get("recommended_format", original_format).lower()
        params = llm_suggestion.get("parameters", {})
        quality = params.get("quality", 75)
        lossless = params.get("lossless", False)
        resize = params.get("resize", {})
        advanced_options = params.get("advanced_options", {})

        print(f"    应用 LLM 建议: format={recommended_format}, quality={quality}, lossless={lossless}, resize={resize}, advanced_options={advanced_options}, original_has_alpha={original_has_alpha}")

        filename = os.path.basename(image_path)
        base_name, _ = os.path.splitext(filename)
        # Ensure output filename uses the *recommended_format* extension
        output_filename = f"{base_name}.{recommended_format}"
        output_path = os.path.join(RESULT_DIR, output_filename)

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                print(f"    清理旧优化文件: {output_path}")
            except Exception as e:
                print(f"    警告: 无法删除旧文件 {output_path}: {e}")

        os.makedirs(RESULT_DIR, exist_ok=True)

        with Image(filename=image_path) as img:
            # If original image has transparency, set background to transparent
            # This is important before operations like resize.
            if original_has_alpha:
                img.background_color = Color('transparent')
                img.alpha_channel = 'set' # Ensure alpha channel is active

            if resize and "width" in resize and "height" in resize:
                new_width = int(resize["width"])
                new_height = int(resize["height"])
                print(f"    调试: Resizing to {new_width}x{new_height}")
                img.resize(new_width, new_height)
                # Re-assert alpha properties if they were reset by resize (sometimes happens)
                if original_has_alpha:
                    img.alpha_channel = 'set'

            # Set target format
            img.format = recommended_format.upper()

            # Apply quality AFTER format conversion and alpha setup
            img.quality = quality # General quality, mapping depends on format

            if recommended_format == "webp":
                img.compression_quality = quality # Specific for WebP
                if original_has_alpha:
                    img.type = 'truecoloralpha'
                    if lossless:
                        img.options['webp:lossless'] = 'true'
                    # For lossy WebP with alpha, you might want to control alpha quality/compression
                    # e.g., img.options['webp:alpha-quality'] = '100'
                    # e.g., img.options['webp:alpha-compression'] = '1' # 1 for lossless alpha compression
                else:
                    img.type = 'truecolor'
                    if lossless:
                        img.options['webp:lossless'] = 'true'
                img.depth = 8
                for key, value in advanced_options.items():
                    img.options[key] = str(value)

            elif recommended_format == "avif":
                img.compression_quality = quality # Specific for AVIF
                # AVIF respects img.alpha_channel. If original_has_alpha, it should be preserved.
                if not original_has_alpha and img.alpha_channel:
                     # If source wasn't alpha but AVIF somehow implies it, turn off
                    img.alpha_channel = 'off'
                for key, value in advanced_options.items():
                    img.options[key] = str(value)

            elif recommended_format == "jpeg":
                img.background_color = Color('white')
                img.alpha_channel = 'off'  # 移除透明通道
                if original_has_alpha:
                    img.composite(img, 0, 0)  # 展平到白色背景
                img.depth = 8

            elif recommended_format == "png":
                # PNG supports transparency.
                # img.alpha_channel = 'set' (if original_has_alpha) should handle it.
                # Wand's 'quality' for PNG can be tricky. It often relates to compression level (0-9)
                # and filter type. For example, quality // 10 could be compression level.
                # img.compression = 6 # A common default (0=none, 9=max)
                if not original_has_alpha and img.alpha_channel:
                    img.alpha_channel = 'off'
                # If 'lossless' is True for PNG, it implies no quality degradation,
                # which is default for PNG structure but compression level still matters.

            img.strip()  # Remove metadata
            img.save(filename=output_path)

        optimized_size = os.path.getsize(output_path)

        with Image(filename=output_path) as optimized_img:
            expected_width = resize.get("width", original_width)
            expected_height = resize.get("height", original_height)
            # Convert to int for comparison if they come from JSON as strings
            if (optimized_img.width, optimized_img.height) != (int(expected_width), int(expected_height)):
                print(f"    警告：优化后图片尺寸从 {expected_width}x{expected_height} 变为 {optimized_img.width}x{optimized_img.height}")
                # os.remove(output_path) # Decide if this is a critical failure
                # For now, let's report it but not fail the optimization entirely for this reason
                # return { ... failure status ... }

        size_reduction = original_size - optimized_size
        size_reduction_percent = (size_reduction / original_size * 100) if original_size > 0 else 0

        print(f"    调试: 优化完成，输出到 {output_path}")
        return {
            "status": "success",
            "original_size_bytes": original_size,
            "optimized_size_bytes": optimized_size,
            "size_reduction_bytes": size_reduction,
            "size_reduction_percent": round(size_reduction_percent, 2),
            "optimized_format": recommended_format,
            "optimized_path": output_path,
            "final_quality": quality,
            "lossless": lossless,
            "advanced_options": advanced_options,
            "original_had_alpha": original_has_alpha # Add this for reporting
        }

    except FileNotFoundError as e:
        print(f"    优化图片 {image_path} 时文件未找到: {e}")
        return {
            "status": "failed",
            "original_size_bytes": 0,
            "optimized_size_bytes": 0,
            "error": str(e)
        }
    except ValueError as e: # Catch specific ValueError from LLM suggestion
        print(f"    优化图片 {image_path} 时配置错误: {e}")
        return {
            "status": "failed",
            "original_size_bytes": os.path.getsize(image_path) if os.path.exists(image_path) else 0,
            "optimized_size_bytes": 0,
            "error": str(e)
        }
    except Exception as e:
        print(f"    优化图片 {image_path} 时发生错误: {type(e).__name__} {e}")
        # Try to get original size even if optimization fails mid-way
        current_original_size = 0
        if 'original_size' in locals():
            current_original_size = original_size
        elif os.path.exists(image_path):
            current_original_size = os.path.getsize(image_path)

        return {
            "status": "failed",
            "original_size_bytes": current_original_size,
            "optimized_size_bytes": 0,
            "error": str(e)
        }

# --- 主逻辑 ---
def main():
    """
    主函数，根据优化建议执行图片优化，并生成对比报告。
    """
    print(f"调试: 启动脚本，项目: {PROJECT_NAME}")
    if not os.path.exists(SOURCE_IMAGES_DIR):
        print(f"错误：源图片目录 '{SOURCE_IMAGES_DIR}' 不存在。")
        return

    if not os.path.exists(SUGGESTIONS_FILE):
        print(f"错误：优化建议文件 '{SUGGESTIONS_FILE}' 不存在。")
        return

    try:
        with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
            suggestions = json.load(f)
    except Exception as e:
        print(f"错误：无法读取优化建议文件 '{SUGGESTIONS_FILE}'：{e}")
        return

    print(f"调试: 检查并清理 {RESULT_DIR}")
    if os.path.exists(RESULT_DIR):
        for file_item in os.listdir(RESULT_DIR): # Renamed 'file' to 'file_item' to avoid conflict
            file_path = os.path.join(RESULT_DIR, file_item)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"清理旧文件: {file_path}")
            except Exception as e:
                print(f"警告: 清理文件 {file_path} 时出错: {e}")
    else:
        os.makedirs(RESULT_DIR, exist_ok=True) # Ensure RESULT_DIR exists

    print(f"\n开始优化图片 for project: {PROJECT_NAME}")
    optimization_report = {}

    total_original_size = 0
    total_optimized_size = 0
    successful_optimizations = 0

    for image_file, suggestion_data in suggestions.items(): # Renamed 'suggestion' to 'suggestion_data'
        print(f"调试: 处理图片 {image_file}")
        image_path = os.path.join(SOURCE_IMAGES_DIR, image_file)
        if not os.path.exists(image_path):
            print(f"    跳过：图片文件 '{image_path}' 不存在")
            optimization_report[image_file] = {
                "status": "skipped",
                "error": "原始图片文件不存在"
            }
            continue

        print(f"\n正在优化图片: {image_file}")
        # Pass suggestion_data which contains the "llm_suggestion" dict
        result = optimize_image(image_path, suggestion_data)


        # Populate report with details from suggestion_data for original info
        original_info = suggestion_data.get("original_info", {}) # If you have this structure
        llm_sugg_info = suggestion_data.get("llm_suggestion", {})


        optimization_report[image_file] = {
            "original_filename": image_file,
            "original_format": original_info.get("format", result.get("original_format","N/A")), # Get from original info if available
            "original_width": original_info.get("width", result.get("original_width",0)),
            "original_height": original_info.get("height", result.get("original_height",0)),
            "original_had_alpha": result.get("original_had_alpha", False), # Added for report
            "optimization_status": result["status"],
            "original_size_bytes": result["original_size_bytes"],
            "optimized_size_bytes": result.get("optimized_size_bytes", 0),
            "size_reduction_bytes": result.get("size_reduction_bytes", 0),
            "size_reduction_percent": result.get("size_reduction_percent", 0),
            "optimized_format": result.get("optimized_format", llm_sugg_info.get("recommended_format", "")),
            "optimized_path": result.get("optimized_path", ""),
            "error": result.get("error", ""),
            "final_quality": result.get("final_quality", llm_sugg_info.get("parameters", {}).get("quality")),
            "lossless": result.get("lossless", llm_sugg_info.get("parameters", {}).get("lossless")),
            "advanced_options": result.get("advanced_options", llm_sugg_info.get("parameters", {}).get("advanced_options"))
        }

        if result["status"] == "success":
            total_original_size += result["original_size_bytes"]
            total_optimized_size += result["optimized_size_bytes"]
            successful_optimizations += 1
        else:
            print(f"    优化失败：{result.get('error', '未知错误')}")
            # Even if failed, original size might be known if error happened after reading it
            if result["original_size_bytes"] > 0 and result.get("status") != "skipped":
                 # only add to total_original_size if it's a processing failure, not a skip
                 # This logic might need refinement based on how you want to count failures
                 pass


    total_images = len(suggestions)
    total_size_reduction = total_original_size - total_optimized_size
    total_size_reduction_percent = (total_size_reduction / total_original_size * 100) if total_original_size > 0 else 0

    optimization_report["summary"] = {
        "total_images_to_process": total_images, # Total images from suggestions file
        "successfully_optimized_images": successful_optimizations,
        "total_original_size_bytes_of_successful": total_original_size, # Corresponds to successfully optimized images
        "total_optimized_size_bytes_of_successful": total_optimized_size, # Corresponds to successfully optimized images
        "total_size_reduction_bytes_on_successful": total_size_reduction,
        "total_size_reduction_percent_on_successful": round(total_size_reduction_percent, 2)
    }

    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(optimization_report, f, indent=4, ensure_ascii=False)
    print(f"\n优化报告已保存到 {REPORT_FILE}")

    # 生成 CSV 报告
    csv_data = [["Filename", "Original Format", "Original Dimensions", "Original Had Alpha", "Original Size (Bytes)", "Optimized Format", "Optimized Size (Bytes)", "Size Reduction (Bytes)", "Size Reduction (%)", "Final Quality", "Lossless", "Advanced Options", "Status", "Error"]]
    for image_file, data in optimization_report.items():
        if image_file == "summary":
            continue
        original_format_csv = data.get("original_format", "N/A")
        original_dimensions_csv = f"{data.get('original_width', 0)}x{data.get('original_height', 0)}" if data.get("original_width") and data.get("original_height") else "N/A"
        original_had_alpha_csv = str(data.get("original_had_alpha", "N/A"))
        original_size_csv = str(data.get("original_size_bytes", "N/A"))
        optimized_format_csv = data.get("optimized_format", "N/A")
        optimized_size_csv = str(data.get("optimized_size_bytes", "N/A"))
        size_reduction_bytes_csv = str(data.get("size_reduction_bytes", "N/A"))
        size_reduction_percent_csv = f"{data.get('size_reduction_percent', 0)}%" if data.get("size_reduction_percent") is not None else "N/A"
        final_quality_csv = str(data.get("final_quality", "N/A"))
        lossless_csv = str(data.get("lossless", "N/A"))
        advanced_options_csv = ", ".join([f"{k}={v}" for k, v in data.get("advanced_options", {}).items()]) if data.get("advanced_options") else "N/A"
        status_csv = data.get("optimization_status", "N/A")
        error_csv = data.get("error", "")


        csv_data.append([
            image_file,
            original_format_csv,
            original_dimensions_csv,
            original_had_alpha_csv,
            original_size_csv,
            optimized_format_csv,
            optimized_size_csv,
            size_reduction_bytes_csv,
            size_reduction_percent_csv,
            final_quality_csv,
            lossless_csv,
            advanced_options_csv,
            status_csv,
            error_csv
        ])
    
    os.makedirs(os.path.dirname(CSV_REPORT_FILE), exist_ok=True) # Ensure directory exists
    with open(CSV_REPORT_FILE, 'w', newline='', encoding='utf-8') as f_csv:
        writer = csv.writer(f_csv)
        writer.writerows(csv_data)
    print(f"优化报告 CSV 已保存到 {CSV_REPORT_FILE}")

    summary_data = optimization_report.get("summary", {})
    print("\n--- 优化总结 ---")
    print(f"计划处理图片总数: {summary_data.get('total_images_to_process', 0)}")
    print(f"成功优化图片数: {summary_data.get('successfully_optimized_images', 0)}")
    print(f"成功优化图片原始总大小: {summary_data.get('total_original_size_bytes_of_successful', 0)} 字节")
    print(f"成功优化图片优化后总大小: {summary_data.get('total_optimized_size_bytes_of_successful', 0)} 字节")
    print(f"成功优化图片总大小减少: {summary_data.get('total_size_reduction_bytes_on_successful', 0)} 字节 ({summary_data.get('total_size_reduction_percent_on_successful', 0):.2f}%)")


if __name__ == "__main__":
    wand_available = False
    try:
        from wand.image import Image
        from wand.color import Color # Ensure Color is imported here if optimize_image is called directly
        wand_available = True
    except ImportError:
        print("错误：Wand 库未安装。请运行 'pip install Wand' 并确保 ImageMagick 已安装")
        sys.exit(1)

    imagemagick_available = False
    if wand_available: # Only check ImageMagick if Wand imported successfully
        try:
            # A more robust way to check ImageMagick presence linked with Wand
            with Image(width=1, height=1) as _: # Try a minimal Wand operation
                pass 
            print("ImageMagick 似乎已正确配置并可供 Wand 使用。")
            imagemagick_available = True
        except Exception as e:
            print(f"警告：无法通过 Wand 验证 ImageMagick 功能: {e}")
            print("请确保 ImageMagick 已正确安装，配置了 delegates (例如对于 webp, png, jpeg)，并在系统 PATH 中，或者 Wand 知道如何找到它。")
            print("在某些系统上，您可能需要设置 MAGICK_HOME 环境变量。")
            # Optionally, you can still try os.system as a fallback check
            try:
                # This checks if the 'convert' command is callable, not if Wand can use it.
                if os.system("convert -version > nul 2>&1" if os.name == 'nt' else "convert -version > /dev/null 2>&1") == 0:
                    print("ImageMagick 'convert' 命令在 PATH 中可执行。")
                else:
                    print("ImageMagick 'convert' 命令在 PATH 中未找到或执行失败。")
            except Exception as ose:
                print(f"尝试执行 'convert -version' 时出错: {ose}")


    if wand_available and imagemagick_available:
        main()
    elif wand_available and not imagemagick_available:
        print("Wand 库已加载，但 ImageMagick 可能未正确设置。脚本可能无法处理图片。尝试继续...")
        # You might choose to exit here if ImageMagick is critical and unconfirmed
        # sys.exit(1)
        main() # Or attempt to run main anyway
    else:
        # Wand import failed earlier, message already printed.
        sys.exit(1)