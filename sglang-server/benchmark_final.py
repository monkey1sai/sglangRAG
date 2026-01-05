import sys
import os
import argparse
import asyncio
import time
import json
import aiohttp
import statistics
import random
import threading
import subprocess
from typing import List, Dict, Any

# Force UTF-8 output for Windows console
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

print("開始執行最終基準測試腳本...", flush=True)

def load_env_file(filepath):
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    except:
        pass

load_env_file('.env')

SGLANG_URL = "http://localhost:8082/v1/chat/completions"
API_KEY = os.getenv("SGLANG_API_KEY", "your-secure-api-key-here")
MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"

class SystemMonitor:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.running = False
        self.gpu_stats = []
        self.vram_stats = []
        self.thread = None

    def get_gpu_stats(self):
        try:
            cmd = "nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits"
            output = subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
            util, mem = output.split(',')
            return float(util), float(mem)
        except:
            return 0.0, 0.0

    def _monitor_loop(self):
        while self.running:
            gpu_util, gpu_mem = self.get_gpu_stats()
            self.gpu_stats.append(gpu_util)
            self.vram_stats.append(gpu_mem)
            time.sleep(self.interval)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def report(self):
        if not self.gpu_stats: return "無 GPU 數據。"
        return (f"    GPU 使用率: 平均 {statistics.mean(self.gpu_stats):.1f}% | 最大 {max(self.gpu_stats):.1f}%\n"
                f"    GPU 顯存 (VRAM): 平均 {statistics.mean(self.vram_stats):.0f} MB | 最大 {max(self.vram_stats):.0f} MB")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "process_ecommerce_order",
            "description": "處理電商訂單（含 VIP 客戶與多品項）",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "customer": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "vip": {"type": "string", "enum": ["std", "gold"]}
                        }
                    },
                    "items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "qty": {"type": "integer"}}}}
                },
                "required": ["order_id", "customer", "items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_logs",
            "description": "分析叢集日誌（指定叢集與時間區間）",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster": {"type": "string"},
                    "range": {"type": "object", "properties": {"s": {"type": "string"}, "e": {"type": "string"}}}
                },
                "required": ["cluster", "range"]
            }
        }
    }
]

def generate_request(idx):
    scenarios = [
        (f"請處理訂單 #{idx}：客戶 VIP-123，品項為筆電 2 台、滑鼠 1 個。", "process_ecommerce_order"),
        (f"請分析 Alpha 叢集今天 10 點到 11 點的日誌。", "analyze_logs"),
    ]
    return random.choice(scenarios)

async def make_request(session, req_id):
    prompt, _ = generate_request(req_id)
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是助理。請一律使用中文回覆。"
                    "當需要呼叫工具時，優先以 tool_calls 產生結構化參數，避免輸出多餘文字。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "tools": TOOLS,
        "stream": True
    }
    
    start = time.perf_counter()
    ttft = None
    output = ""
    tokens = 0
    
    try:
        async with session.post(SGLANG_URL, json=payload, headers={"Authorization": f"Bearer {API_KEY}"}) as resp:
            while True:
                line = await resp.content.readline()
                if not line:
                    break
                line = line.decode('utf-8').strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    if ttft is None: ttft = time.perf_counter()
                    try:
                        delta = json.loads(line[6:])["choices"][0]["delta"]
                        if delta.get("tool_calls"):
                            for tc in delta["tool_calls"]:
                                if "function" in tc:
                                    args = tc["function"].get("arguments", "")
                                    output += args
                                    tokens += len(args) / 4
                        if "content" in delta and delta["content"]:
                            output += delta["content"]
                            tokens += len(delta["content"]) / 4
                    except Exception as e:
                        print(f"JSON Parse Error: {e} | Delta: {delta} | Line: {line[:50]}...", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}")
        
    end = time.perf_counter()
    print(f"[請求 ID: {req_id}]\n輸入: {prompt}\n輸出: {output}\n" + "-"*30, flush=True)
    return {"ttft": (ttft-start) if ttft else (end-start), "total": end-start, "tokens": max(1, tokens)}

async def run(concurrency, total):
    print(f"正在執行 {total} 個請求（並發數：{concurrency}）...", flush=True)
    monitor = SystemMonitor()
    monitor.start()
    
    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        tasks = []
        start_time = time.perf_counter()
        for i in range(total):
            async def worker(idx):
                async with sem: return await make_request(session, idx)
            tasks.append(worker(i))
        results = await asyncio.gather(*tasks)
        end_time = time.perf_counter()
    
    monitor.stop()
    valid = [r for r in results if "error" not in r]
    duration = end_time - start_time
    
    print("\n" + "="*50)
    print("測試報告")
    print("="*50)
    print(f"平均首字延遲 (TTFT): {statistics.mean(r['ttft'] for r in valid):.4f}s")
    print(f"平均總耗時: {statistics.mean(r['total'] for r in valid):.4f}s")
    print(f"系統吞吐量 (RPS): {len(valid)/duration:.2f} req/s")
    print(f"系統生成速度 (TPS): {sum(r['tokens'] for r in valid)/duration:.2f} tokens/s")
    print("-"*50)
    print("資源使用監控")
    print(monitor.report())
    print("="*50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--total", type=int, default=20)
    args = parser.parse_args()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args.concurrency, args.total))
