#!/usr/bin/env python3
import subprocess
import time
import os
import sys
import re

# 定义标识模型任务的名称模式
MODEL_JOB_NAME_PATTERN = "QwQ-serv"  # 假设模型任务的名称包含这个字符串

def check_node_status(node_name):
    """
    检查指定节点的状态
    返回: (是否有任务在运行, 错误信息)
    """
    try:
        # 使用squeue检查指定节点上的任务
        result = subprocess.run(
            f"squeue -w {node_name}", 
            shell=True,
            capture_output=True, 
            text=True
        )
        
        # 如果输出中包含节点名称，说明有任务在运行
        has_jobs = node_name in result.stdout
        
        # 打印状态，方便调试
        print(f"{node_name} 状态: {'有任务运行' if has_jobs else '空闲'}")
        
        return (has_jobs, None)
    except Exception as e:
        error_msg = f"检查节点状态时出错: {str(e)}"
        print(error_msg)
        return (True, error_msg)  # 发生错误时假定节点繁忙

def submit_server_job():
    """
    提交server.slurm任务
    返回: (是否成功, 任务ID或错误信息)
    """
    try:
        # 检查slurm文件是否存在
        if not os.path.exists("server.slurm"):
            return (False, "server.slurm文件不存在")
        
        # 提交任务
        result = subprocess.run(
            "sbatch server.slurm",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # 从输出中提取任务ID
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

def main():
    print("自动提交服务器任务脚本启动")
    last_pending_check_time = 0
    
    while True:
        current_time = time.time()
        
        # 每5分钟检查一次等待任务
        if current_time - last_pending_check_time >= 300:  # 5分钟 = 300秒
            print("执行定期检查等待任务...")
            check_and_handle_pending_jobs()
            last_pending_check_time = current_time
        
        has_jobs, error = check_node_status("compute04")
        
        if error:
            print(f"检查节点状态失败: {error}")
        elif not has_jobs:
            print("compute04节点空闲，准备提交任务...")
            success, result = submit_server_job()
            
            if success:
                print(f"成功提交任务到compute04，任务ID: {result}")
                # 等待较长时间再次检查
                time.sleep(300)  # 5分钟
            else:
                print(f"提交任务失败: {result}")
                # 失败后等待较短时间再试
                time.sleep(60)  # 1分钟
        else:
            print("compute04节点当前有任务运行")
            time.sleep(60)  # 1分钟后再次检查

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n检测到Ctrl+C，程序退出")
        sys.exit(0) 