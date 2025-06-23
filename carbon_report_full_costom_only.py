import os
import sys
import json
import time
import subprocess
import threading
from waitress import serve
import mimetypes
import numpy as np
from statistics import mean
import csv
from pathlib import Path

# --- 动态添加 paths.py 所在目录到 sys.path ---
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
if str(PATHS_DIR) not in sys.path:
    sys.path.append(str(PATHS_DIR))

try:
    from paths import WEBSITES_ORIGINAL_DIR, FULL_CARBON_DIR, FULL_OPTI_DIR
except ImportError as e:
    print(f"错误：无法从 'paths.py' 导入路径变量。请确保 'utils/paths.py' 文件存在且路径正确。")
    print(f"尝试的路径是: {PATHS_DIR}")
    print(f"错误详情: {e}")
    sys.exit(1)

# --- 全局配置 ---
LOCAL_SERVER_PORT = 8000
ROOT_DIR = "C:/Users/user/Desktop/web_carbon"
FINAL_OPTIMIZED_WEBSITES_BASE_DIR = os.path.join(FULL_OPTI_DIR, "websites_optimized")
FULL_REPORT_OUTPUT_BASE_DIR = FULL_CARBON_DIR
TEMP_PROJECT_DATA_BASE_DIR = os.path.join(FULL_REPORT_OUTPUT_BASE_DIR, "temp")
FINAL_AGGREGATED_REPORTS_DIR = FULL_REPORT_OUTPUT_BASE_DIR
DATA_DIR = os.path.join(ROOT_DIR, "data")
CUSTOM_EMISSION_SCRIPT = os.path.join(ROOT_DIR, "scripts", "compute_emission.mjs")
INPUT_DATA_PATH = os.path.join(DATA_DIR, "lh_data_got.json")
OUTPUT_EMISSION_PATH = os.path.join(DATA_DIR, "carbon_emission.json")


# Lighthouse 可执行文件路径
PROJECT_ROOT_DIR = Path(__file__).resolve().parent
NODE_MODULES_DIR = PROJECT_ROOT_DIR / "node_modules"
LIGHTHOUSE_EXEC = NODE_MODULES_DIR / ".bin" / "lighthouse.cmd"
if sys.platform != "win32":
    LIGHTHOUSE_EXEC = NODE_MODULES_DIR / ".bin" / "lighthouse"

NUM_RUNS = 5
MAX_RETRIES_PER_RUN = 3

# --- 辅助函数 ---
def check_local_dependencies():
    if not os.path.exists(LIGHTHOUSE_EXEC):
        print(f"错误: Lighthouse 可执行文件 '{LIGHTHOUSE_EXEC}' 未找到。请运行: npm install lighthouse")
        sys.exit(1)
    if not os.path.exists(CUSTOM_EMISSION_SCRIPT):
        print(f"错误: 自定义碳排放脚本 '{CUSTOM_EMISSION_SCRIPT}' 未找到。请确保文件存在。")
        sys.exit(1)
    os.makedirs(DATA_DIR, exist_ok=True)

def check_directory_exists(directory, description, critical=True):
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"{'错误' if critical else '警告'}: {description} 目录 '{directory}' 不存在或不是一个目录。")
        if critical:
            sys.exit(1)
        return False
    return True

def check_file_exists(file_path, description, critical=True):
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        print(f"{'错误' if critical else '警告'}: {description} 文件 '{file_path}' 不存在或不是一个文件。")
        if critical:
            sys.exit(1)
        return False
    return True

def start_local_server(serve_from_dir):
    abs_serve_from_dir = os.path.abspath(serve_from_dir)
    print(f"尝试从以下目录启动服务: {abs_serve_from_dir}")

    def app(environ, start_response):
        path = environ.get('PATH_INFO', '').lstrip('/')
        requested_file_path = os.path.normpath(os.path.join(abs_serve_from_dir, path))
        if not requested_file_path.startswith(abs_serve_from_dir):
            start_response('403 Forbidden', [('Content-Type', 'text/plain')])
            return [b'403 Forbidden']
        if os.path.exists(requested_file_path) and os.path.isfile(requested_file_path):
            content_type, _ = mimetypes.guess_type(requested_file_path)
            content_type = content_type or 'application/octet-stream'
            try:
                with open(requested_file_path, 'rb') as f:
                    content = f.read()
                start_response('200 OK', [('Content-Type', content_type), ('Content-Length', str(len(content)))])
                return [content]
            except Exception as e:
                start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
                return [f'读取文件错误: {str(e)}'.encode('utf-8')]
        else:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'404 Not Found']

    server_thread = threading.Thread(
        target=serve,
        args=(app,),
        kwargs={'host': '127.0.0.1', 'port': LOCAL_SERVER_PORT, 'threads': 10, '_quiet': False}
    )
    server_thread.daemon = True
    server_thread.start()
    print(f"本地 Waitress 服务器已启动: http://localhost:{LOCAL_SERVER_PORT}, 服务目录: {abs_serve_from_dir}")
    time.sleep(5)
    return server_thread

def stop_local_server(server_thread):
    print("本地服务器正在停止 (Waitress 通常在主线程退出时停止守护线程)。")

def run_custom_emission_script(total_bytes):
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        print(f"  生成输入文件: {INPUT_DATA_PATH}")
        input_data = {"total_byte_weight": total_bytes}
        with open(INPUT_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(input_data, f, indent=2)

        print(f"  运行自定义脚本: node {CUSTOM_EMISSION_SCRIPT}")
        process = subprocess.run(
            ["node", CUSTOM_EMISSION_SCRIPT],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30
        )

        if process.returncode != 0:
            print(f"错误: 运行 compute_emission.mjs 失败。退出码: {process.returncode}")
            print(f"STDERR: {process.stderr[:500]}...")
            return 0

        if not os.path.exists(OUTPUT_EMISSION_PATH):
            print(f"错误: 碳排放输出文件 '{OUTPUT_EMISSION_PATH}' 未生成。")
            return 0

        print(f"  读取输出文件: {OUTPUT_EMISSION_PATH}")
        with open(OUTPUT_EMISSION_PATH, 'r', encoding='utf-8') as f:
            emission_data = json.load(f)

        carbon_emissions = emission_data.get("carbon_emissions")
        if carbon_emissions is None or not isinstance(carbon_emissions, (int, float)) or carbon_emissions <= 0:
            print(f"错误: carbon_emission.json 中的 carbon_emissions 无效: {carbon_emissions}")
            return 0

        print(f"  自定义碳排放: {carbon_emissions} g")
        return carbon_emissions

    except FileNotFoundError as e:
        print(f"错误: Node.js 未安装或 '{CUSTOM_EMISSION_SCRIPT}' 缺失: {e}")
        return 0
    except Exception as e:
        print(f"错误: 运行自定义碳排放脚本失败: {e}")
        return 0

def run_lighthouse_multiple_times(url, num_runs=NUM_RUNS, max_retries=MAX_RETRIES_PER_RUN, temp_dir="."):
    base_command_prefix = [str(LIGHTHOUSE_EXEC), url, "--output=json"]
    base_command_suffix = [
        "--chrome-flags=--headless --disable-gpu --no-sandbox --no-zygote",
        "--disable-storage-reset",
        "--only-categories=performance"
    ]
    all_run_metrics = []
    os.makedirs(temp_dir, exist_ok=True)

    for i in range(num_runs):
        temp_output_json = os.path.join(temp_dir, f"temp_lighthouse_run_{i+1}_{time.time_ns()}.json")
        print(f"  Lighthouse 运行 {i+1}/{num_runs} 针对 {url}...")
        current_run_command = base_command_prefix + [f"--output-path={temp_output_json}"] + base_command_suffix

        for attempt in range(max_retries):
            process_handle = None
            print(f"    尝试 {attempt+1} 命令: {' '.join(current_run_command)}")
            try:
                process_handle = subprocess.Popen(
                    current_run_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    shell=(sys.platform == "win32")
                )
                stdout, stderr = process_handle.communicate(timeout=100)
                returncode = process_handle.returncode

                if stdout:
                    print(f"      Lighthouse stdout (运行 {i+1}, 尝试 {attempt+1}) 头500字符:\n{stdout[:500]}...")
                if stderr:
                    print(f"      Lighthouse stderr (运行 {i+1}, 尝试 {attempt+1}) 头500字符:\n{stderr[:500]}...")

                if returncode != 0:
                    print(f"    运行 {i+1}, 尝试 {attempt+1} 失败: Lighthouse 退出码 {returncode}")
                    if attempt < max_retries - 1:
                        print(f"      2秒后重试...")
                        time.sleep(2)
                        continue
                    else:
                        print(f"  错误: 运行 {i+1} 在 {max_retries} 次重试后因 Lighthouse 错误退出 (URL: {url})。")
                        break

                if not os.path.exists(temp_output_json):
                    print(f"    运行 {i+1}, 尝试 {attempt+1}: Lighthouse 报告文件 '{temp_output_json}' 未创建。")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        break

                if os.path.getsize(temp_output_json) == 0:
                    print(f"    运行 {i+1}, 尝试 {attempt+1}: Lighthouse 报告文件 '{temp_output_json}' 为空。")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        break

                with open(temp_output_json, 'r', encoding='utf-8') as f:
                    report = json.load(f)

                metrics = extract_lighthouse_metrics(report)
                if metrics:
                    all_run_metrics.append(metrics)
                    print(f"    运行 {i+1} 成功。性能得分: {metrics.get('performance_score', 'N/A')}")
                    break
                else:
                    print(f"    运行 {i+1}, 尝试 {attempt+1}: 未能从报告中提取指标。文件内容可能不是有效的 Lighthouse JSON。")

            except subprocess.TimeoutExpired:
                print(f"    运行 {i+1}, 尝试 {attempt+1}: Lighthouse 运行超时。")
                if process_handle:
                    process_handle.kill()
            except FileNotFoundError:
                print(f"    运行 {i+1}, 尝试 {attempt+1}: Lighthouse 可执行文件未找到。请检查路径: {LIGHTHOUSE_EXEC}")
                return None
            except json.JSONDecodeError:
                print(f"    运行 {i+1}, 尝试 {attempt+1}: 解析 Lighthouse JSON 报告 '{temp_output_json}' 失败。")
                if os.path.exists(temp_output_json):
                    try:
                        with open(temp_output_json, 'r', encoding='utf-8') as f_err:
                            file_content_preview = f_err.read(1000)
                            print(f"      文件 '{temp_output_json}' 内容预览 (前1000字符):\n{file_content_preview}...")
                    except Exception as e_read:
                        print(f"      读取错误文件 '{temp_output_json}' 内容时出错: {e_read}")
            except Exception as e:
                print(f"    运行 {i+1}, 尝试 {attempt+1}: 发生意外错误: {e}")

            if attempt < max_retries - 1 and not all_run_metrics:
                print(f"      2秒后重试...")
                time.sleep(2)
            elif all_run_metrics and len(all_run_metrics) == i+1:
                break
            else:
                print(f"  错误: 运行 {i+1} 在 {max_retries} 次重试后失败 (URL: {url})。")

        if os.path.exists(temp_output_json):
            try:
                os.remove(temp_output_json)
            except Exception as e_del:
                print(f"    警告: 删除临时 Lighthouse 文件 '{temp_output_json}' 失败: {e_del}")

    if not all_run_metrics:
        print(f"错误: {num_runs} 次 Lighthouse 运行后未能收集到有效指标 (URL: {url})。")
        return None

    averaged_metrics = {}
    if all_run_metrics:
        keys_to_average = all_run_metrics[0].keys()
        for key in keys_to_average:
            values = [m[key] for m in all_run_metrics if key in m and isinstance(m[key], (int, float))]
            if values:
                averaged_metrics[key] = round(mean(values), 2)
            else:
                averaged_metrics[key] = 0

    return {"raw_runs": all_run_metrics, "averaged_metrics": averaged_metrics}

def extract_lighthouse_metrics(report):
    if not report:
        return None
    try:
        audits = report.get("audits", {})
        total_byte_weight = audits.get("total-byte-weight", {}).get("numericValue")
        fcp = audits.get("first-contentful-paint", {}).get("numericValue")
        lcp = audits.get("largest-contentful-paint", {}).get("numericValue")
        tti = audits.get("interactive", {}).get("numericValue")
        speed_index = audits.get("speed-index", {}).get("numericValue")
        perf_score = report.get("categories", {}).get("performance", {}).get("score")

        if None in [total_byte_weight, fcp, lcp, tti, speed_index, perf_score]:
            print("    提取指标时发现缺失值，Lighthouse 报告可能不完整。")
            return None

        return {
            "total_byte_weight_bytes": total_byte_weight,
            "first_contentful_paint_ms": fcp,
            "largest_contentful_paint_ms": lcp,
            "time_to_interactive_ms": tti,
            "loading_time_ms": speed_index,
            "performance_score": perf_score * 100
        }
    except Exception as e:
        print(f"错误: 提取 Lighthouse 数据失败: {e}")
        return None

def save_per_project_lighthouse_csv(metrics_data, csv_path, site_state_label):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        if not metrics_data or not metrics_data.get("raw_runs") or not metrics_data["raw_runs"]:
            csvfile.write(f"没有可用的 {site_state_label} 数据\n")
            print(f"警告: 没有 Lighthouse 数据可保存到 {csv_path}")
            return

        writer = csv.writer(csvfile)
        header = [
            "Run", "total_byte_weight (bytes)", "first_contentful_paint (ms)",
            "largest_contentful_paint (ms)", "time_to_interactive (ms)",
            "loading_time (ms)", "performance_score"
        ]
        writer.writerow(header)
        for i, run_metrics in enumerate(metrics_data["raw_runs"], 1):
            writer.writerow([
                f"Run {i}",
                round(run_metrics.get("total_byte_weight_bytes", 0), 2),
                round(run_metrics.get("first_contentful_paint_ms", 0), 2),
                round(run_metrics.get("largest_contentful_paint_ms", 0), 2),
                round(run_metrics.get("time_to_interactive_ms", 0), 2),
                round(run_metrics.get("loading_time_ms", 0), 2),
                round(run_metrics.get("performance_score", 0), 2)
            ])
        avg_metrics = metrics_data["averaged_metrics"]
        writer.writerow([
            "Average",
            round(avg_metrics.get("total_byte_weight_bytes", 0), 2),
            round(avg_metrics.get("first_contentful_paint_ms", 0), 2),
            round(avg_metrics.get("largest_contentful_paint_ms", 0), 2),
            round(avg_metrics.get("time_to_interactive_ms", 0), 2),
            round(avg_metrics.get("loading_time_ms", 0), 2),
            round(avg_metrics.get("performance_score", 0), 2)
        ])
    print(f"  单个项目 Lighthouse 指标 ({site_state_label}) 已保存到: {csv_path}")

def main_full_report():
    check_local_dependencies()
    os.makedirs(TEMP_PROJECT_DATA_BASE_DIR, exist_ok=True)
    os.makedirs(FINAL_AGGREGATED_REPORTS_DIR, exist_ok=True)

    if not check_directory_exists(WEBSITES_ORIGINAL_DIR, "基础原始网站目录", critical=True):
        return

    project_names = [d for d in os.listdir(WEBSITES_ORIGINAL_DIR) if os.path.isdir(os.path.join(WEBSITES_ORIGINAL_DIR, d))]
    if not project_names:
        print(f"在 '{WEBSITES_ORIGINAL_DIR}' 目录中没有找到项目文件夹。")
        return

    print(f"发现 {len(project_names)} 个项目: {project_names}")
    all_sites_before_data_for_csv = []
    all_sites_after_data_for_csv = []
    server_thread = start_local_server(str(PROJECT_ROOT_DIR))
    if not server_thread:
        print("启动本地服务器失败。正在退出。")
        return

    try:
        for current_project_name in project_names:
            print(f"\n正在处理项目: {current_project_name}...")
            project_original_site_path = os.path.join(WEBSITES_ORIGINAL_DIR, current_project_name)
            project_optimized_site_path = os.path.join(FINAL_OPTIMIZED_WEBSITES_BASE_DIR, current_project_name)

            relative_original_url_path = os.path.join(os.path.basename(Path(WEBSITES_ORIGINAL_DIR)), current_project_name, "index.html").replace(os.sep, '/')
            relative_optimized_url_path = os.path.join(os.path.basename(Path(FULL_OPTI_DIR)), "websites_optimized", current_project_name, "index.html").replace(os.sep, '/')

            url_original = f"http://localhost:{LOCAL_SERVER_PORT}/{relative_original_url_path}"
            url_optimized = f"http://localhost:{LOCAL_SERVER_PORT}/{relative_optimized_url_path}"
            project_temp_output_dir = os.path.join(TEMP_PROJECT_DATA_BASE_DIR, current_project_name)
            os.makedirs(project_temp_output_dir, exist_ok=True)

            if not (check_directory_exists(project_original_site_path, f"项目 '{current_project_name}' 的原始网站目录", critical=False) and
                    check_file_exists(os.path.join(project_original_site_path, "index.html"), f"项目 '{current_project_name}' 的原始 index.html", critical=False) and
                    check_directory_exists(project_optimized_site_path, f"项目 '{current_project_name}' 的优化后网站目录", critical=False) and
                    check_file_exists(os.path.join(project_optimized_site_path, "index.html"), f"项目 '{current_project_name}' 的优化后 index.html", critical=False)):
                continue

            print(f"  原始网站 URL: {url_original}")
            print(f"  优化后网站 URL: {url_optimized}")

            print(f"  正在运行 Lighthouse 针对 '{current_project_name}' 的原始版本...")
            lh_result_before = run_lighthouse_multiple_times(url_original, temp_dir=project_temp_output_dir)
            if not lh_result_before or not lh_result_before.get("averaged_metrics"):
                print(f"  因 Lighthouse 在原始网站上运行失败，跳过项目 {current_project_name}。")
                continue

            print(f"  正在运行 Lighthouse 针对 '{current_project_name}' 的优化版本...")
            lh_result_after = run_lighthouse_multiple_times(url_optimized, temp_dir=project_temp_output_dir)
            if not lh_result_after or not lh_result_after.get("averaged_metrics"):
                print(f"  因 Lighthouse 在优化后网站上运行失败，跳过项目 {current_project_name}。")
                continue

            csv_before_path = os.path.join(project_temp_output_dir, "lighthouse_metrics_before.csv")
            save_per_project_lighthouse_csv(lh_result_before, csv_before_path, "Original")
            csv_after_path = os.path.join(project_temp_output_dir, "lighthouse_metrics_after.csv")
            save_per_project_lighthouse_csv(lh_result_after, csv_after_path, "Optimized")

            avg_metrics_before = lh_result_before["averaged_metrics"]
            avg_metrics_after = lh_result_after["averaged_metrics"]
            before_total_bytes = avg_metrics_before.get("total_byte_weight_bytes", 0)
            after_total_bytes = avg_metrics_after.get("total_byte_weight_bytes", 0)

            before_custom_carbon = run_custom_emission_script(before_total_bytes)
            after_custom_carbon = run_custom_emission_script(after_total_bytes)

            carbon_reduced_g = before_custom_carbon - after_custom_carbon
            carbon_reduced_percent = (
                round((carbon_reduced_g / before_custom_carbon * 100), 2)
                if before_custom_carbon > 0 else 0
            )
            carbon_reduced_str = f"{round(carbon_reduced_g, 2)} ({carbon_reduced_percent}%)"

            project_detail_report = {
                "project_name": current_project_name,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "urls": {"original": url_original, "optimized": url_optimized},
                "lighthouse_metrics_before_all_runs": lh_result_before["raw_runs"],
                "lighthouse_metrics_before_average": avg_metrics_before,
                "lighthouse_metrics_after_all_runs": lh_result_after["raw_runs"],
                "lighthouse_metrics_after_average": avg_metrics_after,
                "carbon_estimates_before_g": {
                    "custom": round(before_custom_carbon, 4) if before_custom_carbon else None
                },
                "carbon_estimates_after_g": {
                    "custom": round(after_custom_carbon, 4) if after_custom_carbon else None
                },
                "carbon_reduction_g_avg": round(carbon_reduced_g, 4),
                "carbon_reduction_percent": carbon_reduced_percent
            }
            project_detail_report_path = os.path.join(project_temp_output_dir, "carbon_report_local_deps.json")
            with open(project_detail_report_path, "w", encoding="utf-8") as f:
                json.dump(project_detail_report, f, indent=4, ensure_ascii=False)
            print(f"  单个项目详细报告已保存到: {project_detail_report_path}")

            all_sites_before_data_for_csv.append([
                current_project_name, url_original,
                avg_metrics_before.get("total_byte_weight_bytes", 0),
                avg_metrics_before.get("first_contentful_paint_ms", 0),
                avg_metrics_before.get("largest_contentful_paint_ms", 0),
                avg_metrics_before.get("time_to_interactive_ms", 0),
                avg_metrics_before.get("loading_time_ms", 0),
                avg_metrics_before.get("performance_score", 0),
                round(before_custom_carbon, 4) if before_custom_carbon else 0
            ])
            all_sites_after_data_for_csv.append([
                current_project_name, url_optimized,
                avg_metrics_after.get("total_byte_weight_bytes", 0),
                avg_metrics_after.get("first_contentful_paint_ms", 0),
                avg_metrics_after.get("largest_contentful_paint_ms", 0),
                avg_metrics_after.get("time_to_interactive_ms", 0),
                avg_metrics_after.get("loading_time_ms", 0),
                avg_metrics_after.get("performance_score", 0),
                round(after_custom_carbon, 4) if after_custom_carbon else 0,
                carbon_reduced_str
            ])
        print("\n所有项目处理完毕。")
    finally:
        stop_local_server(server_thread)

    csv_header_before = [
        "Site Name", "Site Path", "Total Byte Size (bytes)", "First Contentful Paint (ms)",
        "Largest Contentful Paint (ms)", "Time to Interactive (ms)",
        "Loading Time (ms)", "Performance Score", "CO2 - Custom (g)"
    ]

    csv_header_after = [
        "Site Name", "Site Path", "Total Byte Size (bytes)", "First Contentful Paint (ms)",
        "Largest Contentful Paint (ms)", "Time to Interactive (ms)",
        "Loading Time (ms)", "Performance Score", "CO2 - Custom (g)", "Carbon_reduced (g / %)"
    ]

    csv_before_aggregated_path = os.path.join(FINAL_AGGREGATED_REPORTS_DIR, "carbon_report_before.csv")
    with open(csv_before_aggregated_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(csv_header_before)
        writer.writerows(all_sites_before_data_for_csv)
    print(f"\n汇总的优化前报告已保存到: {csv_before_aggregated_path}")

    csv_after_aggregated_path = os.path.join(FINAL_AGGREGATED_REPORTS_DIR, "carbon_report_after.csv")
    with open(csv_after_aggregated_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(csv_header_after)
        writer.writerows(all_sites_after_data_for_csv)
    print(f"汇总的优化后报告已保存到: {csv_after_aggregated_path}")

    print("\n完整碳排放报告流程结束。")

if __name__ == "__main__":
    if 'WEBSITES_ORIGINAL_DIR' not in globals() or \
       'FULL_CARBON_DIR' not in globals() or \
       'FULL_OPTI_DIR' not in globals():
        print("错误: 关键路径变量未能从 paths.py 加载。")
        sys.exit(1)

    try:
        import waitress
        import numpy
    except ImportError as e:
        print(f"错误: 缺少依赖库 '{e.name}'。请运行 'pip install waitress numpy'。")
        sys.exit(1)

    main_full_report()