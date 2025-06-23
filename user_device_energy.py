import psutil
import time
import csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import statistics
import argparse
import json
import os
from datetime import datetime
import platform

# 系统闲置估算功率（W）基于配置笔记本的公开评测数据

# 配置

DEFAULT_CONFIG = {
    "URLS": [
        "https://www.google.com",
        "https://www.facebook.com",
        "https://www.youtube.com",
        "https://www.wikipedia.org",
        "https://www.amazon.com",
        "https://www.reddit.com",
        "https://www.instagram.com",
        "https://www.twitter.com",
        "https://www.linkedin.com",
        "https://www.netflix.com",
        "https://www.apple.com",
        "https://www.microsoft.com",
        "https://www.bing.com",
        "https://www.yahoo.com",
        "https://www.nytimes.com"
    ],
    "DURATION": 60,
    "SAMPLE_INTERVAL": 1,
    "IDLE_POWER": 4,
    "LOAD_POWER": 37, # 系统满载估算功率（W）基于配置笔记本的公开评测数据
    "OUTPUT_FILE": "results.csv",
    "OUTPUT_FORMAT": "csv",
    "NUM_RUNS": 3,
    "COOLING_TIME": 10,  # 新增冷却时间配置（秒）
    "RETRY_ATTEMPTS": 2,  # 失败重试次数
}

def get_hardware_info():
    """获取硬件和系统信息"""
    return {
        "cpu_model": platform.processor(),
        "cpu_count": psutil.cpu_count(),
        "total_memory_mb": psutil.virtual_memory().total / (1024 ** 2),
        "os": platform.system(),
        "os_version": platform.version()
    }

def get_cpu_usage():
    return psutil.cpu_percent(interval=None)

def get_memory_usage():
    return psutil.virtual_memory().used / (1024 ** 2)

def start_browser():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-cache")  # 禁用缓存
    try:
        return webdriver.Chrome(options=chrome_options)
    except WebDriverException as e:
        print(f"启动浏览器失败: {e}")
        return None

def clear_browser_cache(driver):
    """清除浏览器缓存"""
    try:
        driver.get("chrome://settings/clearBrowserData")
        time.sleep(1)  # 等待设置页面加载
    except WebDriverException as e:
        print(f"清除浏览器缓存失败: {e}")

def record_resource_usage(duration, sample_interval, label="阶段"):
    cpu_usages = []
    mem_usages = []
    print(f"\n{label}：开始记录 {duration} 秒")
    start_time = time.time()
    while time.time() - start_time < duration:
        cpu = get_cpu_usage()
        mem = get_memory_usage()
        cpu_usages.append(cpu)
        mem_usages.append(mem)
        print(f"CPU: {cpu:.1f}%, Mem: {mem:.1f} MB")
        time.sleep(sample_interval)
    return cpu_usages, mem_usages

def estimate_energy(cpu_list, duration, idle_power, load_power):
    if not cpu_list:
        return 0, idle_power, 0, 0
    avg_cpu = statistics.mean(cpu_list)
    power = idle_power + (avg_cpu / 100) * (load_power - idle_power)
    energy_j = power * duration
    energy_wh = energy_j / 3600
    return avg_cpu, power, energy_j, energy_wh

def test_website(url, driver, config):
    print(f"\n======= 正在测试: {url} (进行 {config['NUM_RUNS']} 次) =======")
    if not driver:
        return None

    all_run_results = []
    for i in range(config["NUM_RUNS"]):
        print(f"\n--- 第 {i+1} 次测试 ---")
        for attempt in range(config["RETRY_ATTEMPTS"] + 1):
            try:
                # 清除缓存
                clear_browser_cache(driver)
                
                # 测试空闲状态
                driver.get("about:blank")
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                idle_cpu_run, idle_mem_run = record_resource_usage(
                    config["DURATION"], config["SAMPLE_INTERVAL"], "空白页阶段"
                )

                # 测试页面加载
                driver.get(url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                page_cpu_run, page_mem_run = record_resource_usage(
                    config["DURATION"], config["SAMPLE_INTERVAL"], "网页阶段"
                )

                # 计算能耗
                idle_avg_run, idle_power_run, idle_j_run, idle_wh_run = estimate_energy(
                    idle_cpu_run, config["DURATION"], config["IDLE_POWER"], config["LOAD_POWER"]
                )
                page_avg_run, page_power_run, page_j_run, page_wh_run = estimate_energy(
                    page_cpu_run, config["DURATION"], config["IDLE_POWER"], config["LOAD_POWER"]
                )
                delta_wh_run = (page_j_run - idle_j_run) / 3600

                # 记录内存使用量
                avg_idle_mem = statistics.mean(idle_mem_run) if idle_mem_run else 0
                avg_page_mem = statistics.mean(page_mem_run) if page_mem_run else 0

                all_run_results.append({
                    "idle_avg_cpu": idle_avg_run,
                    "page_avg_cpu": page_avg_run,
                    "idle_power": idle_power_run,
                    "page_power": page_power_run,
                    "idle_wh": idle_wh_run,
                    "page_wh": page_wh_run,
                    "extra_wh": delta_wh_run,
                    "idle_avg_mem": avg_idle_mem,  # 新增内存数据
                    "page_avg_mem": avg_page_mem
                })
                break  # 成功后退出重试循环
            except (WebDriverException, TimeoutException) as e:
                print(f"第 {i+1} 次测试 {url} 失败 (尝试 {attempt+1}/{config['RETRY_ATTEMPTS']+1}): {e}")
                if attempt == config["RETRY_ATTEMPTS"]:
                    print(f"达到最大重试次数，跳过 {url} 的第 {i+1} 次测试")
                    break
                time.sleep(5)  # 重试前等待

    if not all_run_results:
        return None

    # 计算平均值
    avg_idle_avg_cpu = statistics.mean([res["idle_avg_cpu"] for res in all_run_results])
    avg_page_avg_cpu = statistics.mean([res["page_avg_cpu"] for res in all_run_results])
    avg_idle_power = statistics.mean([res["idle_power"] for res in all_run_results])
    avg_page_power = statistics.mean([res["page_power"] for res in all_run_results])
    avg_idle_wh = statistics.mean([res["idle_wh"] for res in all_run_results])
    avg_page_wh = statistics.mean([res["page_wh"] for res in all_run_results])
    avg_extra_wh = statistics.mean([res["extra_wh"] for res in all_run_results])
    avg_idle_avg_mem = statistics.mean([res["idle_avg_mem"] for res in all_run_results])
    avg_page_avg_mem = statistics.mean([res["page_avg_mem"] for res in all_run_results])

    # 计算方差
    var_idle_avg_cpu = statistics.variance([res["idle_avg_cpu"] for res in all_run_results]) if len(all_run_results) > 1 else 0
    var_page_avg_cpu = statistics.variance([res["page_avg_cpu"] for res in all_run_results]) if len(all_run_results) > 1 else 0
    var_idle_power = statistics.variance([res["idle_power"] for res in all_run_results]) if len(all_run_results) > 1 else 0
    var_page_power = statistics.variance([res["page_power"] for res in all_run_results]) if len(all_run_results) > 1 else 0
    var_idle_wh = statistics.variance([res["idle_wh"] for res in all_run_results]) if len(all_run_results) > 1 else 0
    var_page_wh = statistics.variance([res["page_wh"] for res in all_run_results]) if len(all_run_results) > 1 else 0
    var_extra_wh = statistics.variance([res["extra_wh"] for res in all_run_results]) if len(all_run_results) > 1 else 0
    var_idle_avg_mem = statistics.variance([res["idle_avg_mem"] for res in all_run_results]) if len(all_run_results) > 1 else 0
    var_page_avg_mem = statistics.variance([res["page_avg_mem"] for res in all_run_results]) if len(all_run_results) > 1 else 0

    return {
        "url": url,
        "avg_idle_avg_cpu": round(avg_idle_avg_cpu, 2),
        "var_idle_avg_cpu": round(var_idle_avg_cpu, 4),
        "avg_page_avg_cpu": round(avg_page_avg_cpu, 2),
        "var_page_avg_cpu": round(var_page_avg_cpu, 4),
        "avg_idle_power": round(avg_idle_power, 2),
        "var_idle_power": round(var_idle_power, 4),
        "avg_page_power": round(avg_page_power, 2),
        "var_page_power": round(var_page_power, 4),
        "avg_idle_wh": round(avg_idle_wh, 4),
        "var_idle_wh": round(var_idle_wh, 8),
        "avg_page_wh": round(avg_page_wh, 4),
        "var_page_wh": round(var_page_wh, 8),
        "avg_extra_wh": round(avg_extra_wh, 4),
        "var_extra_wh": round(var_extra_wh, 8),
        "avg_idle_avg_mem": round(avg_idle_avg_mem, 2),  # 新增
        "var_idle_avg_mem": round(var_idle_avg_mem, 4),
        "avg_page_avg_mem": round(avg_page_avg_mem, 2),
        "var_page_avg_mem": round(var_page_avg_mem, 4)
    }

def main():
    parser = argparse.ArgumentParser(description="测试网站资源使用和能耗。")
    parser.add_argument("-u", "--urls", nargs='+', help="要测试的 URL 列表 (覆盖默认列表)")
    parser.add_argument("-d", "--duration", type=int, default=DEFAULT_CONFIG["DURATION"], help=f"每个阶段持续时间 (秒), 默认为 {DEFAULT_CONFIG['DURATION']}")
    parser.add_argument("-i", "--interval", type=float, default=DEFAULT_CONFIG["SAMPLE_INTERVAL"], help=f"采样间隔 (秒), 默认为 {DEFAULT_CONFIG['SAMPLE_INTERVAL']}")
    parser.add_argument("--idle_power", type=float, default=DEFAULT_CONFIG["IDLE_POWER"], help=f"系统闲置估算功率 (W), 默认为 {DEFAULT_CONFIG['IDLE_POWER']}")
    parser.add_argument("--load_power", type=float, default=DEFAULT_CONFIG["LOAD_POWER"], help=f"系统满载估算功率 (W), 默认为 {DEFAULT_CONFIG['LOAD_POWER']}")
    parser.add_argument("-o", "--output", default=DEFAULT_CONFIG["OUTPUT_FILE"], help=f"输出文件名, 默认为 {DEFAULT_CONFIG['OUTPUT_FILE']}")
    parser.add_argument("--output_format", choices=["csv", "json"], default=DEFAULT_CONFIG["OUTPUT_FORMAT"], help=f"输出文件格式 (csv 或 json), 默认为 {DEFAULT_CONFIG['OUTPUT_FORMAT']}")
    parser.add_argument("-r", "--runs", type=int, default=DEFAULT_CONFIG["NUM_RUNS"], help=f"每个网站测试运行次数, 默认为 {DEFAULT_CONFIG['NUM_RUNS']}")
    parser.add_argument("--cooling_time", type=int, default=DEFAULT_CONFIG["COOLING_TIME"], help=f"每次测试后的冷却时间 (秒), 默认为 {DEFAULT_CONFIG['COOLING_TIME']}")
    args = parser.parse_args()

    # 创建配置副本，避免修改全局 DEFAULT_CONFIG
    config = DEFAULT_CONFIG.copy()
    config.update({
        "URLS": args.urls or config["URLS"],
        "DURATION": args.duration,
        "SAMPLE_INTERVAL": args.interval,
        "IDLE_POWER": args.idle_power,
        "LOAD_POWER": args.load_power,
        "OUTPUT_FILE": args.output,
        "OUTPUT_FORMAT": args.output_format,
        "NUM_RUNS": args.runs,
        "COOLING_TIME": args.cooling_time
    })

    # 生成带时间戳的输出文件名，防止覆盖
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(config["OUTPUT_FILE"])
    config["OUTPUT_FILE"] = f"{base}_{timestamp}{ext}"

    driver = start_browser()
    if not driver:
        return

    # 记录硬件信息
    hardware_info = get_hardware_info()
    print("硬件信息:", hardware_info)

    all_results = []
    for i, url in enumerate(config["URLS"]):
        result = test_website(url, driver, config)
        if result:
            result.update(hardware_info)  # 将硬件信息添加到结果
            all_results.append(result)
            print(f"结果记录成功：{result['url']}")
        if i < len(config["URLS"]) - 1:
            print(f"等待 {config['COOLING_TIME']} 秒冷却...\n")
            time.sleep(config["COOLING_TIME"])

    driver.quit()

    if all_results:
        fieldnames = list(all_results[0].keys())
        if config["OUTPUT_FORMAT"] == "csv":
            with open(config["OUTPUT_FILE"], mode='w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_results)
            print(f"结果已写入 CSV 文件: {config['OUTPUT_FILE']}")
        elif config["OUTPUT_FORMAT"] == "json":
            with open(config["OUTPUT_FILE"], 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=4)
            print(f"结果已写入 JSON 文件: {config['OUTPUT_FILE']}")

if __name__ == "__main__":
    main()