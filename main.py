import slurm_util
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
import os
import urllib.parse
import json
from datetime import datetime
import threading
import time

BLENDER_PATH = "/archive/junical/render/blender-4.3.2-linux-x64/blender"

folder_name = sys.argv[1]
project_name = sys.argv[2]
file_path = f"./project/{folder_name}/{project_name}.blend"

def generate_sbatch_script(frame_number, cpu_count, use_gpu=True, nodelist=None, partition=None):
    global file_path, BLENDER_PATH
    current_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(current_dir, f"project/{folder_name}/log/slurm")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    script = f"""#!/bin/bash
#SBATCH --job-name=b_{project_name}_{frame_number}
#SBATCH --output={os.path.join(log_dir, f"%j-{timestamp}-{frame_number}.out")}
#SBATCH --error={os.path.join(log_dir, f"%j-{timestamp}-{frame_number}.err")}
{f"#SBATCH --nodelist={nodelist}" if nodelist else ""}
{f"#SBATCH --partition={partition}" if partition else ""}
#SBATCH --cpus-per-task={cpu_count}
#SBATCH --gres=gpu:1
#SBATCH --chdir={current_dir}
#SBATCH --time=0

BLENDER_EXEC="{BLENDER_PATH}"

# 检查blend文件是否存在
if [ ! -f "/tmp/render_project_cache/{folder_name}/{project_name}.blend" ]; then
    mkdir -p "/tmp/render_project_cache/{folder_name}"
    cp "/archive/junical/render/video/project/{folder_name}/{project_name}.blend" "/tmp/render_project_cache/{folder_name}/{project_name}.blend"
fi

$BLENDER_EXEC -b -P b_render_single_frame.py -- /tmp/render_project_cache/{folder_name}/{project_name}.blend {frame_number} {'GPU' if use_gpu else 'CPU'}
"""
    return script

def send_sigle_frame(frame_number, sbatch_script):
    res = slurm_util.submit_job(sbatch_script)
    if res[0]:
        print(f"第{frame_number}帧提交成功，任务ID {res[1]}")
        return res[1]
    else:
        print("第{frame_number}帧提交失败")
        print(res[1])
        return None
    
def check_single_frame(frame_number):
    global project_name, folder_name
    output_file = f"./project/{folder_name}/out/{project_name}_{frame_number:05d}.png"
    if os.path.exists(output_file):
        try:
            with open(output_file, 'rb') as f:
                if f.read(8) == b'\x89PNG\r\n\x1a\n':
                    return True
                else:
                    print(f"第{frame_number}帧渲染失败，文件无效")
                    return False
        except Exception as e:
            print(f"第{frame_number}帧渲染失败，读取文件时出错: {e}")
            return False
    else:
        print(f"第{frame_number}帧未渲染")
        return False

def check_single():
    global folder_name, project_name, file_path

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{current_time}: 检查渲染状态……")
    data_file_path = os.path.join(f"./project/{folder_name}", "data.json")
    if not os.path.exists(data_file_path):
        print(f"错误: {data_file_path} 不存在.")
        sys.exit(1)
    data_file = open(data_file_path, 'r')
    frames = []
    try:
        data = json.load(data_file)
        frames = data.get('frames', [])
    finally:
        data_file.close()
    frames_by_status = {0: [], 1: [], 2: []}
    for frame in frames:
        statue = frame.get('statue', 0)
        frames_by_status[statue].append(frame)

    print("未渲染的帧:", [frame['id'] for frame in frames_by_status[0]])
    print("已发送任务的帧:", [frame['id'] for frame in frames_by_status[1]])
    print("完成渲染的帧:", [frame['id'] for frame in frames_by_status[2]])

    resources = slurm_util.get_node_resources()
    for resource in resources:
        node_name = resource['node_name']
        remaining_cpus = resource['remaining_cpus']
        remaining_gpus = resource['remaining_gpus']
        is_available = resource['is_available']
        print(f"{node_name}: CPU {remaining_cpus}, GPU {remaining_gpus}, 可用 {is_available}")

        if node_name in ['compute06', 'compute07']:
            continue

        if is_available:
            if remaining_gpus > 0:
                for _ in range(remaining_gpus):
                    if frames_by_status[0]:
                        frame = frames_by_status[0].pop(0)
                        if node_name in ['compute06', 'compute07']:
                            sbatch_script = generate_sbatch_script(frame['id'], remaining_cpus // remaining_gpus, True, nodelist=node_name)
                        else: # TODO:针对dlq分区不能指定节点情况的特判
                            sbatch_script = generate_sbatch_script(frame['id'], remaining_cpus // remaining_gpus, True, partition='dlq')
                        job_id = send_sigle_frame(frame['id'], sbatch_script)
                        print(f"帧{frame['id']}提交任务到 {node_name}，任务ID {job_id}")
                        if job_id:
                            frame['statue'] = 1
                            frame['slurm_id'] = job_id
            # TODO: 对CPU渲染的支持，现在提交的任务会处于PENDING状态，原因为PartitionConfig
            # TODO: 添加一个机制，当前提交的任务如提交之后立即进入PENDING状态，就立即取消任务
            # elif remaining_cpus > 40:
            #     if frames_by_status[0]:
            #         frame = frames_by_status[0].pop(0)
            #         sbatch_script = generate_sbatch_script(frame['id'], node_name, remaining_cpus, False)
            #         job_id = send_sigle_frame(frame['id'], sbatch_script)
            #         print(f"帧{frame['id']}提交任务到 {node_name}，任务ID {job_id}")
            #         if job_id:
            #             frame['statue'] = 1
            #             frame['slurm_id'] = job_id

    for frame in frames_by_status[1]:
        job_status = slurm_util.get_job_status(frame['slurm_id'])
        if job_status:
            if job_status['job_state'] == 'COMPLETED':
                if check_single_frame(frame['id']):
                    print(f"第{frame['id']}帧渲染完成")
                    frame['statue'] = 2
                else:
                    print(f"第{frame['id']}帧渲染失败")
                    frame['statue'] = 0
                    frame['slurm_id'] = None
            elif job_status['job_state'] in ['PENDING', 'RUNNING', 'SUSPENDED']:
                if job_status['job_state'] != 'PENDING':
                    print(f"帧{frame['id']} {job_status['job_state']}，任务ID {frame['slurm_id']}")
            else:
                print(f"帧{frame['id']} {job_status['job_state']}，任务ID {frame['slurm_id']}，任务失败")
                frame['statue'] = 0
                frame['slurm_id'] = None

    for frame in frames_by_status[2]:
        if not check_single_frame(frame['id']):
            print(f"第{frame['id']}帧渲染失败，重新提交任务")
            frame['statue'] = 0
            frame['slurm_id'] = None

    output_dir = f"./project/{folder_name}/out"
    for file_name in os.listdir(output_dir):
        if file_name.startswith(f"{project_name}_") and file_name.endswith(".png"):
            try:
                frame_number = int(file_name[len(project_name) + 1:-4])
                output_file = os.path.join(output_dir, file_name)
                with open(output_file, 'rb') as f:
                    if f.read(8) == b'\x89PNG\r\n\x1a\n':
                        for frame in frames:
                            if frame['id'] == frame_number:
                                if frame['statue'] != 2:
                                    frame['statue'] = 2
                                    print(f"第{frame_number}帧已渲染完成并标记")
                                break
            except Exception as e:
                print(f"检查文件 {file_name} 时出错: {e}")

    with open(data_file_path, 'w') as data_file:
        json.dump(data, data_file, indent=4)

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_dict = urllib.parse.parse_qs(parsed_path.query)
        print(f"Query string dictionary: {query_dict}")
        blend_file = query_dict.get('blend_file', [None])[0]
        frame_number = query_dict.get('frame_number', [None])[0]

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        if blend_file and frame_number:
            if blend_file == project_name:
                print(f"收到来自 {self.client_address} 的渲染完成通知: {frame_number}")
                check_single()

def run_http_server(server_class=HTTPServer, handler_class=RequestHandler, port=59405):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"渲染完毕监测服务已启动于 {port}")
    httpd.serve_forever()

def periodic_check(interval):
    while True:
        check_single()
        time.sleep(interval)

if __name__ == "__main__":

    if len(sys.argv) != 3:
        print("用法: python main.py <文件夹名称> <Blender项目名称>")
        sys.exit(1)

    folder_name = sys.argv[1]
    project_name = sys.argv[2]
    file_path = f"./project/{folder_name}/{project_name}.blend"

    if not os.path.exists(file_path):
        print(f"错误: {file_path} 不存在.")
        sys.exit(1)

    print(f"准备处理 {file_path}.")

    data_file_path = os.path.join(f"./project/{folder_name}", "data.json")

    if os.path.exists(data_file_path):
        with open(data_file_path, 'r') as data_file:
            data = json.load(data_file)
            if data.get('blend_file') != f"{project_name}.blend":
                print(f"错误: data.json 中的 blend_file ({data.get('blend_file')}) 与项目名称 ({project_name}) 不符.")
                sys.exit(1)
    else:
        blender_command = f"{BLENDER_PATH} -b -P b_generate_list.py -- {file_path}"
        os.system(blender_command)

    output_dir = f"./project/{folder_name}/out"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # TODO: 将模型预先复制到各个计算节点的SSD中，同时在定期检查线程中每次检查模型文件是否存在

    # 启动定期检查线程
    check_thread = threading.Thread(target=periodic_check, args=(20,))
    check_thread.daemon = True
    check_thread.start()

    # 启动HTTP服务器
    run_http_server()
