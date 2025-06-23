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

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import HTML_OPTI_DIR, CSS_OPTI_DIR, JS_OPTI_DIR, IMAGE_OPTI_DIR, ACTION_CALC_DIR

# --- Configuration ---
if len(sys.argv) < 2:
    print("Error: Please provide project name and at least one task name as arguments, e.g., python carbon_report.py crafti html or python carbon_report.py crafti html css")
    sys.exit(1)

PROJECT_NAME = sys.argv[1]
TASK_NAMES = sys.argv[2:]  # 支持多个任务名

# Validate task names
VALID_TASKS = {"html": HTML_OPTI_DIR, "css": CSS_OPTI_DIR, "js": JS_OPTI_DIR, "image": IMAGE_OPTI_DIR}
invalid_tasks = [task for task in TASK_NAMES if task.lower() not in VALID_TASKS]
if invalid_tasks:
    print(f"Error: Invalid task name(s) '{', '.join(invalid_tasks)}'. Supported tasks: {list(VALID_TASKS.keys())}")
    sys.exit(1)

# Task directories
TASK_DIRS = {task: dir_path for task, dir_path in VALID_TASKS.items()}

# Path configuration
LOCAL_SERVER_PORT = 8000
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
CUSTOM_EMISSION_SCRIPT = os.path.join(SCRIPT_DIR, "scripts", "compute_emission.mjs")
INPUT_DATA_PATH = os.path.join(DATA_DIR, "lh_data_got.json")
OUTPUT_EMISSION_PATH = os.path.join(DATA_DIR, "carbon_emission.json")

# Output report path
OUTPUT_DIR = os.path.join(ACTION_CALC_DIR, PROJECT_NAME)

# Local node_modules path
NODE_MODULES_DIR = os.path.join(SCRIPT_DIR, "node_modules")
LIGHTHOUSE_EXEC = os.path.join(NODE_MODULES_DIR, ".bin", "lighthouse.cmd")

# Number of Lighthouse runs
NUM_RUNS = 5

# --- Helper Functions ---
def check_local_dependencies():
    if not os.path.exists(LIGHTHOUSE_EXEC):
        print(f"Error: Lighthouse executable '{LIGHTHOUSE_EXEC}' not found. Run: npm install lighthouse")
        sys.exit(1)
    if not os.path.exists(CUSTOM_EMISSION_SCRIPT):
        print(f"Error: Custom carbon emission script '{CUSTOM_EMISSION_SCRIPT}' not found. Ensure the file exists.")
        sys.exit(1)
    os.makedirs(DATA_DIR, exist_ok=True)

def check_directory_exists(directory, description):
    if not os.path.exists(directory):
        print(f"Error: {description} directory '{directory}' does not exist.")
        sys.exit(1)

def check_file_exists(file_path, description):
    if not os.path.exists(file_path):
        print(f"Error: {description} file '{file_path}' does not exist.")
        sys.exit(1)

def start_local_server(serve_dir):
    serve_dir = os.path.abspath(serve_dir)
    os.chdir(serve_dir)
    
    def app(environ, start_response):
        path = environ.get('PATH_INFO', '').lstrip('/')
        print(f"Request: {path}")
        full_path = os.path.join(serve_dir, path)
        
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'404 Not Found']
        
        content_type, _ = mimetypes.guess_type(full_path)
        if not content_type:
            content_type = 'application/octet-stream'
        
        try:
            with open(full_path, 'rb') as f:
                content = f.read()
            start_response('200 OK', [('Content-Type', content_type), ('Content-Length', str(len(content)))])
            return [content]
        except Exception as e:
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [f'Error: {str(e)}'.encode('utf-8')]
    
    server_thread = threading.Thread(
        target=serve,
        args=(app,),
        kwargs={'host': '127.0.0.1', 'port': LOCAL_SERVER_PORT, 'threads': 10}
    )
    server_thread.daemon = True
    server_thread.start()
    print(f"Local server started at http://localhost:{LOCAL_SERVER_PORT}")
    time.sleep(2)
    return server_thread

def stop_local_server(server_thread):
    print("Local server stopped")

def run_custom_emission_script(total_bytes):
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        print(f"  Generating input file: {INPUT_DATA_PATH}")
        input_data = {"total_byte_weight": total_bytes}
        with open(INPUT_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(input_data, f, indent=2)

        print(f"  Running custom script: node {CUSTOM_EMISSION_SCRIPT}")
        process = subprocess.run(
            ["node", CUSTOM_EMISSION_SCRIPT],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30
        )

        if process.returncode != 0:
            print(f"Error: Failed to run compute_emission.mjs. Exit code: {process.returncode}")
            print(f"STDERR: {process.stderr[:500]}...")
            return 0

        if not os.path.exists(OUTPUT_EMISSION_PATH):
            print(f"Error: Carbon emission output file '{OUTPUT_EMISSION_PATH}' was not generated.")
            return 0

        print(f"  Reading output file: {OUTPUT_EMISSION_PATH}")
        with open(OUTPUT_EMISSION_PATH, 'r', encoding='utf-8') as f:
            emission_data = json.load(f)

        carbon_emissions = emission_data.get("carbon_emissions")
        if carbon_emissions is None or not isinstance(carbon_emissions, (int, float)) or carbon_emissions <= 0:
            print(f"Error: Invalid carbon_emissions in carbon_emission.json: {carbon_emissions}")
            return 0

        print(f"  Custom carbon emission: {carbon_emissions} g")
        return carbon_emissions

    except FileNotFoundError as e:
        print(f"Error: Node.js not installed or '{CUSTOM_EMISSION_SCRIPT}' missing: {e}")
        return 0
    except Exception as e:
        print(f"Error: Failed to run custom carbon emission script: {e}")
        return 0

def run_lighthouse(url, num_runs=NUM_RUNS, max_retries=3):
    command = [
        "cmd.exe", "/c", LIGHTHOUSE_EXEC, url,
        "--output=json",
        "--chrome-flags=--headless", "--throttle",
        "--disable-storage-reset", "--only-categories=performance"
    ]
    results = []
    metrics_list = []
    
    for i in range(num_runs):
        temp_output = f"temp_lighthouse_run{i}.json"
        for attempt in range(max_retries):
            try:
                run_command = command[:4] + ["--output=json", f"--output-path={temp_output}"] + command[5:]
                result = subprocess.run(
                    run_command,
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                with open(temp_output, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                metrics = extract_lighthouse_metrics(report)
                if metrics:
                    results.append(report)
                    metrics_list.append(metrics)
                break
            except subprocess.CalledProcessError as e:
                print(f"Run {i+1}, Attempt {attempt+1} failed: {e.stderr}")
                if attempt == max_retries - 1:
                    print(f"Error: Run {i+1} failed after {max_retries} retries")
                    return None
                time.sleep(2)
            except FileNotFoundError as e:
                print(f"Error: Lighthouse executable not found: {str(e)}")
                return None
        # 清理临时文件
        if os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except Exception as e:
                print(f"Warning: Failed to delete temporary file '{temp_output}': {str(e)}")
    
    if not metrics_list:
        print("Error: No valid Lighthouse runs completed")
        return None
    
    # 计算平均值
    averaged_metrics = {
        key: round(mean([m[key] for m in metrics_list]), 2)
        for key in metrics_list[0].keys()
    }
    
    return {
        "raw_runs": metrics_list,
        "averaged_metrics": averaged_metrics
    }

def extract_lighthouse_metrics(report):
    if not report:
        return None
    try:
        audits = report.get("audits", {})
        return {
            "total_byte_weight": audits.get("total-byte-weight", {}).get("numericValue", 0),
            "first_contentful_paint_ms": audits.get("first-contentful-paint", {}).get("numericValue", 0),
            "largest_contentful_paint_ms": audits.get("largest-contentful-paint", {}).get("numericValue", 0),
            "time_to_interactive_ms": audits.get("interactive", {}).get("numericValue", 0),
            "performance_score": report.get("categories", {}).get("performance", {}).get("score", 0) * 100
        }
    except Exception as e:
        print(f"Error: Failed to extract Lighthouse data: {e}")
        return None

def print_summary(carbon_report):
    print("\nCarbon Emissions Report Summary:")
    print(f"Task: {carbon_report['task_name'].upper()}")
    
    print("\nMetrics Before Optimization:")
    for i, run in enumerate(carbon_report['metrics_before']['raw_runs'], 1):
        print(f"  Run {i}:")
        print(f"    Total Byte Size: {run['total_byte_weight']} bytes")
        print(f"    First Contentful Paint: {run['first_contentful_paint_ms']} ms")
        print(f"    Largest Contentful Paint: {run['largest_contentful_paint_ms']} ms")
        print(f"    Time to Interactive: {run['time_to_interactive_ms']} ms")
        print(f"    Performance Score: {run['performance_score']}")
    avg = carbon_report['metrics_before']['averaged_metrics']
    print("  Average:")
    print(f"    Total Byte Size: {avg['total_byte_weight']} bytes")
    print(f"    First Contentful Paint: {avg['first_contentful_paint_ms']} ms")
    print(f"    Largest Contentful Paint: {avg['largest_contentful_paint_ms']} ms")
    print(f"    Time to Interactive: {avg['time_to_interactive_ms']} ms")
    print(f"    Performance Score: {avg['performance_score']}")
    
    print("\nMetrics After Optimization:")
    for i, run in enumerate(carbon_report['metrics_after']['raw_runs'], 1):
        print(f"  Run {i}:")
        print(f"    Total Byte Size: {run['total_byte_weight']} bytes")
        print(f"    First Contentful Paint: {run['first_contentful_paint_ms']} ms")
        print(f"    Largest Contentful Paint: {run['largest_contentful_paint_ms']} ms")
        print(f"    Time to Interactive: {run['time_to_interactive_ms']} ms")
        print(f"    Performance Score: {run['performance_score']}")
    avg = carbon_report['metrics_after']['averaged_metrics']
    print("  Average:")
    print(f"    Total Byte Size: {avg['total_byte_weight']} bytes")
    print(f"    First Contentful Paint: {avg['first_contentful_paint_ms']} ms")
    print(f"    Largest Contentful Paint: {avg['largest_contentful_paint_ms']} ms")
    print(f"    Time to Interactive: {avg['time_to_interactive_ms']} ms")
    print(f"    Performance Score: {avg['performance_score']}")
    
    print(f"\nReduction in Byte Size: {carbon_report['metrics_before']['averaged_metrics']['total_byte_weight'] - carbon_report['metrics_after']['averaged_metrics']['total_byte_weight']} bytes")
    
    print("\nCarbon Emissions Before (based on average):")
    print(f"  Custom: {carbon_report['carbon_estimates_before']['custom']['carbon_g']} g CO2")
    
    print("\nCarbon Emissions After (based on average):")
    print(f"  Custom: {carbon_report['carbon_estimates_after']['custom']['carbon_g']} g CO2")
    
    print(f"\nCarbon Reduction: {carbon_report['carbon_reduction_g']} g CO2")

# --- Main Logic ---
def main():
    check_local_dependencies()

    for TASK_NAME in TASK_NAMES:
        BASE_DIR = TASK_DIRS[TASK_NAME]
        WEBSITES_ORIGINAL_DIR = os.path.join("websites_original", PROJECT_NAME)
        WEBSITES_OPTIMIZED_DIR = os.path.join(BASE_DIR, "websites_optimized", PROJECT_NAME)
        BASE_URL_ORIGINAL = f"http://localhost:{LOCAL_SERVER_PORT}/{WEBSITES_ORIGINAL_DIR.replace(os.sep, '/')}/index.html"
        BASE_URL_OPTIMIZED = f"http://localhost:{LOCAL_SERVER_PORT}/{WEBSITES_OPTIMIZED_DIR.replace(os.sep, '/')}/index.html"
        OUTPUT_REPORT = os.path.join(OUTPUT_DIR, f"{TASK_NAME}_carbon_report_local_deps.json")
        CSV_BEFORE = os.path.join(OUTPUT_DIR, f"{TASK_NAME}_lighthouse_metrics_before.csv")
        CSV_AFTER = os.path.join(OUTPUT_DIR, f"{TASK_NAME}_lighthouse_metrics_after.csv")
        CSV_SUMMARY = os.path.join(OUTPUT_DIR, f"{TASK_NAME}_carbon_emissions_summary.csv")

        check_directory_exists(WEBSITES_ORIGINAL_DIR, "Original website")
        check_file_exists(os.path.join(WEBSITES_ORIGINAL_DIR, "index.html"), "Original index.html")
        check_directory_exists(WEBSITES_OPTIMIZED_DIR, "Optimized website")
        check_file_exists(os.path.join(WEBSITES_OPTIMIZED_DIR, "index.html"), "Optimized index.html")

        server_thread = start_local_server(SCRIPT_DIR)
        try:
            print(f"\nGenerating carbon emissions report for project '{PROJECT_NAME}' task '{TASK_NAME}'...")
            print(f"Report will be saved to: {OUTPUT_REPORT}")

            # Run Lighthouse (before optimization)
            result_before = run_lighthouse(BASE_URL_ORIGINAL)
            if not result_before:
                print(f"Error: Failed to get Lighthouse data for original website for task '{TASK_NAME}'.")
                continue
            lighthouse_metrics_before = result_before

            # Run Lighthouse (after optimization)
            result_after = run_lighthouse(BASE_URL_OPTIMIZED)
            if not result_after:
                print(f"Error: Failed to get Lighthouse data for optimized website for task '{TASK_NAME}'.")
                continue
            lighthouse_metrics_after = result_after

            # Calculate carbon emissions using averaged metrics
            before_total_bytes = lighthouse_metrics_before["averaged_metrics"]["total_byte_weight"]
            after_total_bytes = lighthouse_metrics_after["averaged_metrics"]["total_byte_weight"]

            before_custom_carbon = run_custom_emission_script(before_total_bytes)
            after_custom_carbon = run_custom_emission_script(after_total_bytes)

            # Generate report
            carbon_report = {
                "project_name": PROJECT_NAME,
                "task_name": TASK_NAME,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "metrics_before": {
                    "raw_runs": lighthouse_metrics_before["raw_runs"],
                    "averaged_metrics": lighthouse_metrics_before["averaged_metrics"]
                },
                "metrics_after": {
                    "raw_runs": lighthouse_metrics_after["raw_runs"],
                    "averaged_metrics": lighthouse_metrics_after["averaged_metrics"]
                },
                "carbon_estimates_before": {
                    "custom": {"carbon_g": round(before_custom_carbon, 4)}
                },
                "carbon_estimates_after": {
                    "custom": {"carbon_g": round(after_custom_carbon, 4)}
                },
                "carbon_reduction_g": round(before_custom_carbon - after_custom_carbon, 4)
            }

            # Save report
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
                json.dump(carbon_report, f, indent=4, ensure_ascii=False)

            # Generate CSV files
            # 1. Before optimization metrics
            with open(CSV_BEFORE, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Run", "Total Byte Weight", "First Contentful Paint (ms)", "Largest Contentful Paint (ms)", "Time to Interactive (ms)", "Performance Score"])
                for i, run in enumerate(lighthouse_metrics_before["raw_runs"], 1):
                    writer.writerow([i, run["total_byte_weight"], run["first_contentful_paint_ms"], run["largest_contentful_paint_ms"], run["time_to_interactive_ms"], run["performance_score"]])
                avg = lighthouse_metrics_before["averaged_metrics"]
                writer.writerow(["Average", avg["total_byte_weight"], avg["first_contentful_paint_ms"], avg["largest_contentful_paint_ms"], avg["time_to_interactive_ms"], avg["performance_score"]])

            # 2. After optimization metrics
            with open(CSV_AFTER, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Run", "Total Byte Weight", "First Contentful Paint (ms)", "Largest Contentful Paint (ms)", "Time to Interactive (ms)", "Performance Score"])
                for i, run in enumerate(lighthouse_metrics_after["raw_runs"], 1):
                    writer.writerow([i, run["total_byte_weight"], run["first_contentful_paint_ms"], run["largest_contentful_paint_ms"], run["time_to_interactive_ms"], run["performance_score"]])
                avg = lighthouse_metrics_after["averaged_metrics"]
                writer.writerow(["Average", avg["total_byte_weight"], avg["first_contentful_paint_ms"], avg["largest_contentful_paint_ms"], avg["time_to_interactive_ms"], avg["performance_score"]])

            # 3. Carbon emissions summary
            with open(CSV_SUMMARY, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Metric", "Before Optimization", "After Optimization", "Change (%)"])
                writer.writerow(["Total Byte Size (bytes)", int(lighthouse_metrics_before["averaged_metrics"]["total_byte_weight"]), int(lighthouse_metrics_after["averaged_metrics"]["total_byte_weight"]), f"{round((lighthouse_metrics_after['averaged_metrics']['total_byte_weight'] - lighthouse_metrics_before['averaged_metrics']['total_byte_weight']) / lighthouse_metrics_before['averaged_metrics']['total_byte_weight'] * 100, 2)}%"])
                writer.writerow(["First Contentful Paint (ms)", round(lighthouse_metrics_before["averaged_metrics"]["first_contentful_paint_ms"], 2), round(lighthouse_metrics_after["averaged_metrics"]["first_contentful_paint_ms"], 2), f"{round((lighthouse_metrics_after['averaged_metrics']['first_contentful_paint_ms'] - lighthouse_metrics_before['averaged_metrics']['first_contentful_paint_ms']) / lighthouse_metrics_before['averaged_metrics']['first_contentful_paint_ms'] * 100, 2)}%"])
                writer.writerow(["Largest Contentful Paint (ms)", round(lighthouse_metrics_before["averaged_metrics"]["largest_contentful_paint_ms"], 2), round(lighthouse_metrics_after["averaged_metrics"]["largest_contentful_paint_ms"], 2), f"{round((lighthouse_metrics_after['averaged_metrics']['largest_contentful_paint_ms'] - lighthouse_metrics_before['averaged_metrics']['largest_contentful_paint_ms']) / lighthouse_metrics_before['averaged_metrics']['largest_contentful_paint_ms'] * 100, 2)}%"])
                writer.writerow(["Time to Interactive (ms)", round(lighthouse_metrics_before["averaged_metrics"]["time_to_interactive_ms"], 2), round(lighthouse_metrics_after["averaged_metrics"]["time_to_interactive_ms"], 2), f"{round((lighthouse_metrics_after['averaged_metrics']['time_to_interactive_ms'] - lighthouse_metrics_before['averaged_metrics']['time_to_interactive_ms']) / lighthouse_metrics_before['averaged_metrics']['time_to_interactive_ms'] * 100, 2)}%"])
                writer.writerow(["Performance Score", round(lighthouse_metrics_before["averaged_metrics"]["performance_score"], 2), round(lighthouse_metrics_after["averaged_metrics"]["performance_score"], 2), f"{round((lighthouse_metrics_after['averaged_metrics']['performance_score'] - lighthouse_metrics_before['averaged_metrics']['performance_score']) / lighthouse_metrics_before['averaged_metrics']['performance_score'] * 100, 2)}%"])
                writer.writerow(["Carbon Emissions (g CO2)", round(carbon_report["carbon_estimates_before"]["custom"]["carbon_g"], 4), round(carbon_report["carbon_estimates_after"]["custom"]["carbon_g"], 4), f"{round((carbon_report['carbon_estimates_after']['custom']['carbon_g'] - carbon_report['carbon_estimates_before']['custom']['carbon_g']) / carbon_report['carbon_estimates_before']['custom']['carbon_g'] * 100, 2)}%"])

            print(f"\nCarbon emissions report saved to: {OUTPUT_REPORT}")
            print(f"Lighthouse metrics before saved to: {CSV_BEFORE}")
            print(f"Lighthouse metrics after saved to: {CSV_AFTER}")
            print(f"Carbon emissions summary saved to: {CSV_SUMMARY}")
            print_summary(carbon_report)

        finally:
            stop_local_server(server_thread)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)