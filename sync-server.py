#!/usr/bin/env python3
"""本地同步服务：
1. 接收老板端 POST /sync 的完整数据 → 写入 data.json（本地原始）
2. 自动脱敏 → 生成 public-data.json（只含客端需要的字段，无隐私信息）
3. 自动 git add/commit/push 推送到 GitHub Pages
"""
import http.server
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'data.json')
PUBLIC_FILE = os.path.join(BASE_DIR, 'public-data.json')


# ===== 脱敏算法 =====
def hash_phone(phone):
    """SHA256 前12位 hex，用于查询匹配"""
    if not phone:
        return None
    return hashlib.sha256(phone.encode()).hexdigest()[:12]


def mask_phone(phone):
    """138****1234 格式"""
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + '****' + phone[-4:]


def sanitize_data(raw_data):
    """从完整数据提取客端字段，手机号脱敏"""
    raw_cards = raw_data.get('cards', [])
    raw_tickets = raw_data.get('giftTickets', [])
    raw_wallets = raw_data.get('wallets', {})

    clean_cards = []
    for c in raw_cards:
        phone = c.get('phone', '')
        clean_cards.append({
            'id': c.get('id', ''),
            'name': c.get('name', ''),
            'phoneHash': hash_phone(phone),
            'phoneMasked': mask_phone(phone),
            'total': c.get('total', 4),
            'used': c.get('used', 0),
            'buyDate': c.get('buyDate', ''),
            'expireDate': c.get('expireDate', ''),
            'inviteCode': c.get('inviteCode', ''),
            'status': c.get('status', ''),
            'transferred': c.get('transferred', 0),
            'renewCount': c.get('renewCount', 0),
        })

    clean_wallets = {}
    for code, w in raw_wallets.items():
        clean_wallets[code] = {'balance': w.get('balance', 0)}

    clean_tickets = []
    for t in raw_tickets:
        clean_tickets.append({
            'id': t.get('id', ''),
            'redeemCode': t.get('redeemCode', ''),
            'ownerPhoneHash': hash_phone(t.get('ownerPhone', '')),
            'ownerName': t.get('ownerName', ''),
            'source': t.get('source', ''),
            'sourceDetail': t.get('sourceDetail', ''),
            'createdAt': t.get('createdAt', ''),
            'expireDate': t.get('expireDate', ''),
            'status': t.get('status', ''),
            'transferredTo': t.get('transferredTo', ''),
            'usedAt': t.get('usedAt', ''),
        })

    return {
        'cards': clean_cards,
        'wallets': clean_wallets,
        'giftTickets': clean_tickets,
        'updatedAt': datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S +08:00'),
    }


# ===== Git 自动提交 =====
def git_push():
    try:
        now = datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')

        # 先拉取远程，避免冲突
        subprocess.run(['git', 'pull', '--rebase', 'origin', 'main'],
                       cwd=BASE_DIR, capture_output=True, check=True)

        subprocess.run(['git', 'add', 'data.json', 'public-data.json'],
                       cwd=BASE_DIR, capture_output=True, check=True)

        # 跳过空提交
        diff = subprocess.run(['git', 'diff', '--cached', '--quiet'],
                              cwd=BASE_DIR, capture_output=True)
        if diff.returncode == 0:
            msg = '⏭️ 无变更，跳过 git push'
            print(msg)
            return (True, msg)

        subprocess.run(['git', 'commit', '-m', f'Auto-sync {now}'],
                       cwd=BASE_DIR, capture_output=True, check=True)
        subprocess.run(['git', 'push', 'origin', 'main'],
                       cwd=BASE_DIR, capture_output=True, check=True)
        msg = '🚀 已推送至 GitHub Pages'
        print(msg)
        return (True, msg)
    except subprocess.CalledProcessError as e:
        msg = f'Git push 失败: {e.stderr.decode() if e.stderr else str(e)}'
        print(msg)
        return (False, msg)
    except Exception as e:
        msg = f'Git push 异常: {str(e)}'
        print(msg)
        return (False, msg)


# ===== HTTP Server =====
class SyncHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path == '/sync':
            cl = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(cl).decode('utf-8')
            try:
                raw = json.loads(body)

                # 1. 原始数据
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(raw, f, ensure_ascii=False, indent=2)
                n = len(raw.get('cards', []))
                print(f'✅ data.json ({n} 张卡)')

                # 2. 脱敏数据
                pub = sanitize_data(raw)
                with open(PUBLIC_FILE, 'w', encoding='utf-8') as f:
                    json.dump(pub, f, ensure_ascii=False, indent=2)
                print(f'🔒 public-data.json (脱敏)')

                # 3. Git push
                ok, push_msg = git_push()
                print(push_msg)

                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'ok': ok,
                    'pushMsg': push_msg,
                    'cards': len(pub['cards']),
                }, ensure_ascii=False).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'pong': True}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    port = 8766
    server = http.server.HTTPServer(('127.0.0.1', port), SyncHandler)
    print(f'🔁 数据同步服务 http://127.0.0.1:{port}')
    print(f'📄 原始: {DATA_FILE}')
    print(f'🔒 脱敏: {PUBLIC_FILE}')
    print(f'📦 Git: {BASE_DIR}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n🛑 已停止')
