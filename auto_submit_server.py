#!/usr/bin/env python3
import subprocess
import time
import os
import sys
import re

# 定义标识模型任务的名称模式
MODEL_JOB_NAME_PATTERN = "QwQ-serv"
ACTIVE_NODES = ["compute04", "compute01", "compute05"]  # 优先级顺序
CURRENT_RUNNING_NODE = None  # 当前运行节点

def check_node_status(node_name, ignore_our_job=True):
    """
    检查指定节点的状态
    Args:
        ignore_our_job: 是否忽略我们自己的任务
    返回: (是否有任务在运行, 任务ID列表或错误信息)
    """
    try:
        # 获取完整任务信息
        result = subprocess.run(f"scontrol show jobs", shell=True, capture_output=True, text=True)
        
        jobs = []
        job_blocks = result.stdout.strip().split("\n\n")
        
        for block in job_blocks:
            job_info = {}
            for line in block.split("\n"):
                for part in line.strip().split():
                    if "=" in part:
                        key, value = part.split("=", 1)
                        job_info[key] = value
            
            if job_info.get('NodeList') == node_name:
                if ignore_our_job and MODEL_JOB_NAME_PATTERN in job_info.get('JobName', ''):
                    continue  # 忽略我们自己的任务
                jobs.append(job_info)

        has_jobs = len(jobs) > 0 or check_gpu_usage(node_name)
        print(f"{node_name} 状态: {'有任务运行' if has_jobs else '空闲'}")
        return (has_jobs, jobs)
    except Exception as e:
        error_msg = f"检查节点状态时出错: {str(e)}"
        print(error_msg)
        return (True, error_msg)  # 发生错误时假定节点繁忙

def check_gpu_usage(node_name):
    """检查节点GPU使用率"""
    try:
        result = subprocess.run(
            f"ssh {node_name} nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits",
            shell=True, capture_output=True, text=True, timeout=10
        )
        usages = [int(x) for x in result.stdout.strip().split('\n') if x]
        avg_usage = sum(usages)/len(usages) if usages else 0
        return avg_usage > 20  # GPU使用率超过20%视为繁忙
    except:
        return True  # 无法获取时视为繁忙

def submit_server_job(node_name):
    """
    提交到指定节点
    """
    try:
        # 生成动态slurm脚本
        slurm_script = f"""#!/bin/bash
#SBATCH -J QwQ-serv
#SBATCH -p dlq
#SBATCH --time=7-00:00:00
#SBATCH -N 1
#SBATCH -n 12
#SBATCH --mem=50G
#SBATCH --nodelist={node_name}  # 动态设置节点名称
#SBATCH --gres=gpu:2
#SBATCH -o logs/{node_name}_%j.out  # 日志包含节点名称
#SBATCH -e logs/{node_name}_%j.err

# 创建日志目录（如果不存在）
mkdir -p logs

source /archive/liugu/.env
source /archive/liugu/ds/venv/llama/bin/activate
/archive/liugu/ds/llama.cpp-server-3090/build/bin/llama-server \\
  -m /archive/liugu/QwQ/QwQ-GGUF/QwQ-32B-Q8_0.gguf \\
  -ngl 100 \\
  -fa \\
  -ctk q8_0 \\
  -ctv q8_0 \\
  --host 0.0.0.0 \\
  --port 29500 \\
  -np 4 \\
  -t 12 \\
  -c 40960
"""
        with open("dynamic_server.slurm", "w") as f:
            f.write(slurm_script)
            
        result = subprocess.run(f"sbatch dynamic_server.slurm", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            global CURRENT_RUNNING_NODE
            CURRENT_RUNNING_NODE = node_name
            job_id = result.stdout.strip().split()[-1]
            print(f"任务提交成功，ID: {job_id}")
            return (True, job_id)
        else:
            error_msg = f"提交任务失败: {result.stderr}"
            print(error_msg)
            return (False, error_msg)
            
    except Exception as e:
        error_msg = f"提交任务时出错: {str(e)}"
        print(error_msg)
        return (False, error_msg)

def get_all_jobs():
    """
    获取所有SLURM任务的详细信息
    返回: 任务信息字典列表
    """
    try:
        result = subprocess.run(
            "scontrol show jobs",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"获取任务信息失败: {result.stderr}")
            return []
            
        # 解析任务信息
        jobs = []
        job_blocks = result.stdout.strip().split("\n\n")
        
        for block in job_blocks:
            job_info = {}
            for line in block.split("\n"):
                line = line.strip()
                # 提取键值对
                for part in line.split():
                    if "=" in part:
                        key, value = part.split("=", 1)
                        job_info[key] = value
            
            if job_info:
                jobs.append(job_info)
                
        return jobs
    except Exception as e:
        print(f"获取任务信息时出错: {str(e)}")
        return []

def get_running_model_job_on_node(node_name):
    """
    获取在指定节点上运行的模型任务ID
    返回: 任务ID或None
    """
    jobs = get_all_jobs()
    
    for job in jobs:
        # 检查任务是否在指定节点上运行
        if 'NodeList' in job and node_name in job['NodeList']:
            # 检查是否是模型任务
            if 'JobName' in job and MODEL_JOB_NAME_PATTERN in job['JobName']:
                return job.get('JobId')
    
    return None

def check_pending_jobs_for_node(node_name):
    """
    检查是否有非模型任务正在等待指定节点
    返回: 布尔值，表示是否有这样的任务
    """
    jobs = get_all_jobs()
    
    for job in jobs:
        # 检查任务是否处于等待状态
        if 'JobState' in job and job['JobState'] == 'PENDING':
            # 检查任务是否需要该节点
            if 'ReqNodeList' in job and node_name in job['ReqNodeList']:
                # 检查是否不是模型任务
                if 'JobName' in job and MODEL_JOB_NAME_PATTERN not in job['JobName']:
                    print(f"发现等待{node_name}的非模型任务: {job.get('JobId')} (名称: {job.get('JobName')})")
                    return True
    
    return False

def cancel_model_job_on_node(node_name):
    """
    取消在指定节点上运行的模型任务
    返回: 是否成功取消
    """
    job_id = get_running_model_job_on_node(node_name)
    
    if not job_id:
        print(f"在{node_name}上没有找到运行中的模型任务")
        return False
        
    try:
        print(f"发现需要取消的模型任务: {job_id}")
        result = subprocess.run(
            f"scancel {job_id}",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"成功取消任务 {job_id}")
            return True
        else:
            print(f"取消任务失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"取消任务时出错: {str(e)}")
        return False

def check_and_handle_pending_jobs():
    """
    检查并处理等待compute04的非模型任务
    """
    if check_pending_jobs_for_node("compute04"):
        print("发现等待compute04的非模型任务，准备取消当前运行的模型任务")
        if cancel_model_job_on_node("compute04"):
            print("已取消compute04上的模型任务，让步给其他任务")
        else:
            print("尝试取消模型任务失败")

def find_idle_node():
    """寻找空闲节点"""
    for node in ACTIVE_NODES:
        busy, _ = check_node_status(node)
        if not busy:
            # 二次确认
            time.sleep(5)
            if not check_node_status(node)[0]:
                return node
    return None

def main():
    print("自动提交服务器任务脚本启动")
    last_pending_check_time = 0
    current_job_id = None
    
    while True:
        current_time = time.time()
        
        # 如果当前有运行中的任务
        if CURRENT_RUNNING_NODE:
            # 检查任务是否仍在运行
            busy, _ = check_node_status(CURRENT_RUNNING_NODE, ignore_our_job=False)
            if busy:
                print(f"{CURRENT_RUNNING_NODE} 上的任务仍在运行")
                time.sleep(60)
                continue
            else:
                print(f"{CURRENT_RUNNING_NODE} 上的任务已结束")
                CURRENT_RUNNING_NODE = None
                
        # 寻找空闲节点
        target_node = find_idle_node()
        if target_node:
            print(f"在 {target_node} 发现空闲资源，准备提交任务...")
            success, job_id = submit_server_job(target_node)
            if success:
                current_job_id = job_id
                print(f"已在 {target_node} 提交任务，ID: {job_id}")
                # 监控间隔缩短
                time.sleep(30)
            else:
                print(f"提交到 {target_node} 失败: {job_id}")
                time.sleep(10)
        else:
            print("当前无可用节点，等待下一轮检查...")
            time.sleep(60)
        
        # 每10分钟检查优先级
        if current_time - last_pending_check_time >= 300:
            # 如果有更高优先级节点空闲，迁移任务
            for node in ACTIVE_NODES:
                if node == CURRENT_RUNNING_NODE:
                    continue
                if not check_node_status(node)[0]:
                    print(f"发现更高优先级节点 {node} 空闲，准备迁移任务")
                    if cancel_current_job():
                        CURRENT_RUNNING_NODE = None
                    break
            last_pending_check_time = current_time

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n检测到Ctrl+C，程序退出")
        sys.exit(0) 