#!/usr/bin/env python3
import subprocess
from flask import Flask, jsonify
from flask_restx import Api, Resource

app = Flask(__name__)
api = Api(app, version='1.0', title='SLURM服务状态检查',
    description='检查模型服务状态',
    doc='/api/docs'
)

ns = api.namespace('api', description='服务状态检查')

@ns.route('/check-service')
class CheckService(Resource):
    @api.doc(
        responses={
            200: "成功执行检查",
        },
        description="检查SLURM队列中是否存在名为QwQ-serv的任务"
    )
    def get(self):
        """检查QwQ-serv是否正在运行"""
        is_running = check_qwq_service()
        return jsonify({"running": is_running})

def check_qwq_service():
    """
    检查SLURM队列中是否有正在运行的QwQ-serv任务
    """
    try:
        # 使用更精确的检查命令，只匹配运行中的任务
        cmd = "squeue -h -n QwQ-serv -t R --noheader"
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        # 打印调试信息
        print(f"执行检查命令: {cmd}")
        print("命令输出:", result.stdout.strip())
        print("错误输出:", result.stderr.strip())
        
        # 如果有输出则表示有正在运行的任务
        is_running = result.stdout.strip() != ""
        
        print(f"QwQ-serv服务状态: {'运行中' if is_running else '未运行'}")
        return is_running
        
    except Exception as e:
        print(f"检查服务状态时出错: {str(e)}")
        return False

if __name__ == '__main__':
    # 添加直接检查功能
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        print("执行手动检查...")
        status = check_qwq_service()
        print(f"检查结果: {status}")
        sys.exit(0)
    
    print("SLURM服务状态检查API已启动")
    print("监听端口：30000")
    app.run(host='0.0.0.0', port=30000) 