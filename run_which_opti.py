import os
import sys
import subprocess
import time
from pathlib import Path

# 动态添加 paths.py 所在目录到 sys.path
PATHS_DIR = Path("C:/Users/user/Desktop/web_carbon/utils")
sys.path.append(str(PATHS_DIR))

# 导入 paths 模块中的路径变量
from paths import  PYTHON_SCRIPTS_DIR,WEBSITES_ORIGINAL_DIR


# 设置 PYTHONUTF8 环境变量以支持 UTF-8 编码
os.environ["PYTHONUTF8"] = "1"

# --- 配置区域 ---

# 支持的任务列表
TASKS = ["html", "css", "js", "image"]

# 每个任务的子脚本后缀
SUB_SCRIPT_SUFFIXES = ["extract", "get_llm_suggestions", "optimize", "replace"]

# --- 辅助函数 ---
def get_available_projects():
    """从 websites_original 文件夹中获取所有项目名（子文件夹名）"""
    if not os.path.exists(WEBSITES_ORIGINAL_DIR):
        print(f"Error: Directory '{WEBSITES_ORIGINAL_DIR}' does not exist")
        sys.exit(1)
    
    # 获取所有子文件夹名
    projects = [d for d in os.listdir(WEBSITES_ORIGINAL_DIR) if os.path.isdir(os.path.join(WEBSITES_ORIGINAL_DIR, d))]
    if not projects:
        print(f"Error: No projects found in '{WEBSITES_ORIGINAL_DIR}'")
        sys.exit(1)
    return sorted(projects)

def prompt_task_selection():
    """提示用户选择任务"""
    print("\nAvailable tasks:", ", ".join(TASKS))
    while True:
        task = input("Please select a task to optimize (html, css, js, image): ").strip().lower()
        if task in TASKS:
            return task
        print(f"Invalid task '{task}'. Please choose from {', '.join(TASKS)}")

def prompt_project_selection(projects):
    """提示用户选择项目"""
    print("\nAvailable projects:", ", ".join(projects))
    while True:
        project = input("Please select a project to optimize (e.g., bookish, crafti): ").strip()
        if project in projects:
            return project
        print(f"Invalid project '{project}'. Please choose from {', '.join(projects)}")

def run_script(task, script_suffix, project_name):
    """运行指定任务的子脚本"""
    script_name = f"{task}_{script_suffix}.py"
    script_path = os.path.join(PYTHON_SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"Error: Script '{script_path}' does not exist")
        return False
    
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S NZST')}] Executing script: {script_name} (Project: {project_name})")
    try:
        result = subprocess.run(
            [sys.executable, script_path, project_name],
            check=True,
            text=True,
            capture_output=True,
            encoding='utf-8'
        )
        print(result.stdout)
        if result.stderr:
            print(f"Warning: Script output error message: {result.stderr}")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S NZST')}] Script {script_name} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to execute '{script_name}': {e.stderr}")
        return False
    except Exception as e:
        print(f"Error: Unknown error occurred while executing '{script_name}': {e}")
        return False

# --- 主逻辑 ---
def main():
    # 获取可用项目
    projects = get_available_projects()

    # 提示用户选择任务
    task = prompt_task_selection()

    # 提示用户选择项目
    project_name = prompt_project_selection(projects)

    print(f"\nStarting optimization for task '{task}' on project '{project_name}'...")

    # 按顺序运行子脚本
    success = True
    for suffix in SUB_SCRIPT_SUFFIXES:
        if not run_script(task, suffix, project_name):
            success = False
            print(f"Warning: '{task}_{suffix}.py' failed, but will continue with the next script")
        else:
            print(f"Success: '{task}_{suffix}.py' completed, proceeding to the next script")
        # 添加短暂延迟以确保文件系统操作完成
        time.sleep(1)
    
    if success:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S NZST')}] All scripts for task '{task}' executed successfully!")
    else:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S NZST')}] Some scripts for task '{task}' failed, please check the error messages above.")

if __name__ == "__main__":
    main()