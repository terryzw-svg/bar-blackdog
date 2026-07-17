#!/usr/bin/env python3
"""本地同步服务：接收老板端保存的数据，写入 data.json"""
import http.server
import json
import os
import sys

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')
GIT_REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bar-blackdog')

class SyncHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path == '/sync':
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f'✅ data.json 已更新 ({len(data.get("cards",[]))} 张卡)')

                # 复制到 bar-blackdog 仓库
                if os.path.isdir(GIT_REPO):
                    import shutil
                    shutil.copy(DATA_FILE, os.path.join(GIT_REPO, 'data.json'))
                    print(f'✅ bar-blackdog/data.json 已同步')

                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True}).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'pong')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silent

if __name__ == '__main__':
    port = 8766
    server = http.server.HTTPServer(('127.0.0.1', port), SyncHandler)
    print(f'🔁 数据同步服务已启动 http://127.0.0.1:{port}')
    print(f'📄 监听: {DATA_FILE}')
    print(f'📦 Git 仓库: {GIT_REPO}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('🛑 同步服务已停止')
