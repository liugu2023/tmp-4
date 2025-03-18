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
    检查SLURM队列中是否有名为QwQ-serv的任务
    """
    try:
        # 使用grep直接过滤结果
        result = subprocess.run(
            "squeue | grep 'QwQ-serv'", 
            shell=True,
            capture_output=True, 
            text=True
        )
        
        # 如果grep找到内容，返回码为0
        is_running = result.returncode == 0
        
        # 打印状态，方便调试
        print(f"QwQ-serv服务状态: {'运行中' if is_running else '未运行'}")
        
        return is_running
    except Exception as e:
        print(f"检查服务状态时出错: {str(e)}")
        return False

if __name__ == '__main__':
    print("SLURM服务状态检查API已启动")
    print("监听端口: 25000")
    app.run(host='0.0.0.0', port=25000) 