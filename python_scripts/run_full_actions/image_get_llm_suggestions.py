import os
import json
import requests
import sys
import csv
from PIL import Image  # 用于获取图片元数据
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import FULL_OPTI_DIR, API_BASE_URL, API_KEY

# API_BASE_URL = "https://api.chatanywhere.org/v1"  # 请替换为实际有效的 API 端点
# # API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = "gpt-3.5-turbo"

# ===== 从命令行参数获取项目名称 =====
if len(sys.argv) < 2:
    print("错误：请提供项目名称作为命令行参数，例如：python generate_suggestions.py project_name")
    sys.exit(1)
PROJECT_NAME = sys.argv[1]

# ===== 路径统一变量定义 =====
SOURCE_TEMP_DIR= FULL_OPTI_DIR / "temp" /PROJECT_NAME/ "image"

# ===== 根据项目名称组合具体输入输出路径 =====
SOURCE_IMAGES_DIR = SOURCE_TEMP_DIR / "images_original"
RESULT_DIR = SOURCE_TEMP_DIR / "image_llm_suggestions"
SUGGESTIONS_FILE_PATH = RESULT_DIR / "image_optimization_suggestions.json"
CSV_SUGGESTIONS_FILE_PATH = RESULT_DIR / "image_optimization_summary.csv"

# --- LLM 调用函数 ---
def get_image_optimization_suggestion(image_path, image_format, width, height):
    """
    调用 LLM 获取图片优化建议，返回结构化的 JSON 格式。
    """
    content_type = "photo" if image_format.lower() in ["jpeg", "jpg"] else "graphic"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
    You are an expert in web image optimization. I have an image that needs aggressive optimization to significantly reduce its file size (target: 30-50% reduction) while maintaining acceptable visual quality (e.g., suitable for web display with minimal noticeable degradation).

    Image details:
    - Path: {image_path}
    - Format: {image_format}
    - Width: {width}px
    - Height: {height}px
    - Content type: {content_type} (e.g., photo, illustration, logo, text-based graphic)

    Provide optimization suggestions in a structured JSON format, optimized for ImageMagick processing. Prioritize modern formats like WebP or AVIF when appropriate, and recommend resizing if the image is larger than typical web display sizes (e.g., max width 2000px). Return only the JSON object, with no additional text or explanations.

    The JSON structure must be:
    {{
      "recommended_format": "string", // e.g., "webp", "avif", "jpeg"
      "parameters": {{
        "quality": integer, // compression quality (0-100), aim for aggressive compression (e.g., 50-70 for lossy)
        "lossless": boolean, // use lossless compression for simple graphics (e.g., logos, icons)
        "resize": {{ // include if resizing is recommended to reduce file size
          "width": integer,
          "height": integer
        }},
        "advanced_options": {{ // optional, include ImageMagick-specific options if applicable
          "webp:method": integer, // e.g., 6 for WebP
          "webp:alpha-compression": integer, // e.g., 1
          "avif:compression": string // e.g., "lossy"
        }}
      }}
    }}

    Example response:
    {{
      "recommended_format": "webp",
      "parameters": {{
        "quality": 60,
        "lossless": false,
        "resize": {{
          "width": 800,
          "height": 640
        }},
        "advanced_options": {{
          "webp:method": 6,
          "webp:alpha-compression": 1
        }}
      }}
    }}
    """

    data = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert in web image optimization. Provide concise, actionable advice in JSON format."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    print(f"\n[LLM] 正在为图片 {os.path.basename(image_path)} 获取优化建议...")

    try:
        response = requests.post(f"{API_BASE_URL}/chat/completions", headers=headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        
        response_json = response.json()
        assistant_response_content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not assistant_response_content:
            print(f"[LLM Error] 模型返回了空的建议内容。")
            return None

        try:
            suggestion = json.loads(assistant_response_content)
            if "recommended_format" not in suggestion or "parameters" not in suggestion:
                raise ValueError("缺少必填字段 recommended_format 或 parameters")
            if "quality" not in suggestion["parameters"] or "lossless" not in suggestion["parameters"]:
                raise ValueError("parameters 中缺少必填字段 quality 或 lossless")
            print(f"[LLM Success] 成功获取并解析建议: {suggestion}")
            return suggestion
        except json.JSONDecodeError as e:
            print(f"[LLM Error] 无法解析模型返回的JSON建议: {assistant_response_content}, 错误: {e}")
            return None
        except ValueError as e:
            print(f"[LLM Error] 模型返回的建议格式不正确: {e}")
            return None

    except requests.exceptions.HTTPError as http_err:
        print(f"[API Error] HTTP错误: {http_err}")
        print(f"           响应状态码: {response.status_code}")
        print(f"           响应内容: {response.text}")
    except requests.exceptions.Timeout:
        print(f"[API Error] 请求超时。")
    except requests.exceptions.RequestException as req_err:
        print(f"[API Error] 请求错误: {req_err}")
    except Exception as e:
        print(f"[Error] 调用LLM时发生未知错误: {e}")
    return None

# --- 主逻辑 ---
def main():
    if not os.path.exists(SOURCE_IMAGES_DIR):
        print(f"错误：源图片目录 '{SOURCE_IMAGES_DIR}' 不存在。")
        return

    os.makedirs(RESULT_DIR, exist_ok=True)

    print(f"开始处理目录: {SOURCE_IMAGES_DIR}")
    image_files = [f for f in os.listdir(SOURCE_IMAGES_DIR) if os.path.isfile(os.path.join(SOURCE_IMAGES_DIR, f))]
    
    if not image_files:
        print("目录中没有找到图片文件。")
        return

    all_suggestions = {}

    for image_file in image_files:
        image_path = os.path.join(SOURCE_IMAGES_DIR, image_file)
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                img_format = img.format
                print(f"\n处理图片: {image_file} (格式: {img_format}, 尺寸: {width}x{height})")
                
                suggestion = get_image_optimization_suggestion(image_path, img_format, width, height)
                if suggestion:
                    formatted_suggestion = {
                        "project_name": PROJECT_NAME,
                        "original_filename": image_file,
                        "original_format": img_format,
                        "original_width": width,
                        "original_height": height,
                        "llm_api_call_details": {
                            "status": "success",
                            "request_payload_summary": {
                                "model": LLM_MODEL,
                                "image_filename_in_prompt": image_file,
                                "image_format": img_format,
                                "width": width,
                                "height": height
                            }
                        },
                        "llm_suggestion": suggestion
                    }
                    all_suggestions[image_file] = formatted_suggestion
                else:
                    all_suggestions[image_file] = {
                        "project_name": PROJECT_NAME,
                        "original_filename": image_file,
                        "original_format": img_format,
                        "original_width": width,
                        "original_height": height,
                        "llm_api_call_details": {
                            "status": "api http error",
                            "request_payload_summary": {
                                "model": LLM_MODEL,
                                "image_filename_in_prompt": image_file,
                                "image_format": img_format,
                                "width": width,
                                "height": height
                            }
                        },
                        "llm_suggestion": {"error": "未能获取优化建议"}
                    }

        except IOError:
            print(f"无法打开或读取图片文件: {image_path}")
            all_suggestions[image_file] = {"error": f"无法打开或读取图片: {image_path}"}
        except Exception as e:
            print(f"处理图片 {image_file} 时发生错误: {e}")
            all_suggestions[image_file] = {"error": f"处理时发生未知错误: {e}"}

    print("\n\n--- 所有图片的优化建议汇总 ---")
    print(json.dumps(all_suggestions, indent=4, ensure_ascii=False))

    with open(SUGGESTIONS_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(all_suggestions, f, indent=4, ensure_ascii=False)
    print(f"\n建议已保存到 {SUGGESTIONS_FILE_PATH}")

    # 生成 CSV 报告
    csv_data = [["Filename", "Original Format", "Original Dimensions", "Recommended Format", "Quality", "Lossless", "Resize Dimensions", "Advanced Options"]]
    for image_file, data in all_suggestions.items():
        if "error" in data or "error" in data.get("llm_suggestion", {}):
            csv_data.append([image_file, "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "Failed to get suggestion"])
            continue

        suggestion = data["llm_suggestion"]
        original_format = data["original_format"]
        original_dimensions = f"{data['original_width']} x {data['original_height']}"
        recommended_format = suggestion.get("recommended_format", "N/A")
        parameters = suggestion.get("parameters", {})
        quality = parameters.get("quality", "N/A")
        lossless = parameters.get("lossless", "N/A")
        resize = parameters.get("resize", None)
        resize_dimensions = f"{resize['width']} x {resize['height']}" if resize else "N/A"
        advanced_options = parameters.get("advanced_options", {})
        advanced_options_str = ", ".join([f"{key}={value}" for key, value in advanced_options.items()]) if advanced_options else "N/A"

        csv_data.append([
            image_file,
            original_format,
            original_dimensions,
            recommended_format,
            str(quality),
            str(lossless),
            resize_dimensions,
            advanced_options_str
        ])

    with open(CSV_SUGGESTIONS_FILE_PATH, 'w', newline='', encoding='utf-8') as f_csv:
        writer = csv.writer(f_csv)
        writer.writerows(csv_data)
    print(f"优化建议 CSV 已保存到 {CSV_SUGGESTIONS_FILE_PATH}")

if __name__ == "__main__":
    try:
        from PIL import Image
    except ImportError:
        print("错误：Pillow 库未安装。请运行 'pip install Pillow'")
        sys.exit(1)
    main()