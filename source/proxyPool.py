import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor
# Import các hàm từ utils.py của mày
from utils import log, safeRequest
import os
import random

SOURCE_URL = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt"
OUTPUT_FILE = "proxies.json"
TARGET_POOL_SIZE = 50
CHECK_TIMEOUT = 5
PROXY_POOL_ENABLED = os.getenv("USE_PROXY_POOL", "0") == "1"

class ProxyScanner:
    def __init__(self):
        self.valid_proxies = []
        self.lock = threading.Lock()

    def check_proxy(self, proxy):
        proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
        try:
            start = time.time()
            # Sử dụng safeRequest từ utils để check IP
            # Dùng httpbin.org để đo độ trễ
            r = safeRequest("GET", "http://httpbin.org/ip", proxies=proxies, timeout=CHECK_TIMEOUT)
            
            if r and r.status_code == 200:
                latency = round(time.time() - start, 2)
                with self.lock:
                    self.valid_proxies.append({"ip": proxy, "latency": latency})
        except Exception:
            pass

    def run(self):
        if not PROXY_POOL_ENABLED:
            log("SCANNER", "Proxy pool disabled by USE_PROXY_POOL=0")
            return
        log("SCANNER", "Bắt đầu khởi động vòng lặp quét Proxy...")
        while True:
            self.valid_proxies = []
            
            # Lấy list thô từ nguồn
            resp = safeRequest("GET", SOURCE_URL, timeout=15)
            if not resp:
                log("SCANNER", "Không thể tải SOURCE_URL, thử lại sau 60s...")
                time.sleep(60)
                continue

            raw_list = [line.replace('http://', '').strip() for line in resp.text.split('\n') if line.strip()]
            raw_list = list(set(raw_list))

            log("SCANNER", f"Đang kiểm tra {len(raw_list[:500])} IP thô...")

            # Dùng ThreadPoolExecutor để quét
            with ThreadPoolExecutor(max_workers=100) as executor:
                executor.map(self.check_proxy, raw_list[:500]) 

            with self.lock:
                # 1. Lọc trễ < 5s
                final_list = [p for p in self.valid_proxies if p['latency'] <= 5.0]
                # 2. Sắp xếp nhanh nhất lên đầu
                final_list.sort(key=lambda x: x['latency'])
                # 3. Lấy đúng số lượng mục tiêu
                final_list = final_list[:TARGET_POOL_SIZE]

            # Ghi vào file JSON
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(final_list, f, indent=4)
            
            log("SCANNER", f"Đã cập nhật Pool: {len(final_list)} IP ngon. Nghỉ 10 phút.")
            time.sleep(600)

# --- Các hàm tiện ích để Bot gọi từ bên ngoài ---

def getRandomProxy():
    """Bốc ngẫu nhiên 1 proxy từ pool"""
    if not PROXY_POOL_ENABLED:
        return None
    # Đảm bảo dùng đường dẫn file chính xác
    if not os.path.exists(OUTPUT_FILE):
        return None
    
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            proxies = json.load(f)
        
        if not proxies: 
            return None
            
        return random.choice(proxies)
    except Exception as e:
        log("ERROR", f"Lỗi getRandomProxy: {e}")
        return None

def reportDead(proxy_ip):
    """Xóa IP lỏ khỏi file ngay lập tức"""
    if not os.path.exists(OUTPUT_FILE):
        return

    with threading.Lock(): # Dùng lock để an toàn khi ghi file
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                proxies = json.load(f)
            
            new_proxies = [p for p in proxies if p['ip'] != proxy_ip]
            
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_proxies, f, indent=4)
            log("PROXY", f"Đã loại bỏ IP lỗi: {proxy_ip}")
        except Exception as e:
            log("ERROR", f"Lỗi khi xóa IP: {e}")

if __name__ == "__main__":
    import os
    scanner = ProxyScanner()
    scanner.run()