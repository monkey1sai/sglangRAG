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
from datetime import datetime

# Force UTF-8 output for Windows console
try:
    sys.stdout.reconfigure(encoding="utf-8")
except:
    pass

print("開始執行 50-Tools TPS 基準測試腳本...", flush=True)


def load_env_file(filepath):
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value
    except:
        pass


load_env_file(".env")

SGLANG_URL = "http://localhost:8082/v1/chat/completions"
API_KEY = os.getenv("SGLANG_API_KEY", "your-secure-api-key-here")
MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
TOOL_COUNT = 12
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
LOG_FILE = os.path.join(LOG_DIR, "benchmark_50_tools_tps.log")

LOCATION_TRANSLATIONS = {
    "living_room": "客廳",
    "bedroom": "臥室",
    "kitchen": "廚房",
    "bathroom": "浴室",
    "home": "家裡",
}

DEVICE_ID_TRANSLATIONS = {
    "ac_1": "冷氣",
    "air_purifier_1": "空氣清淨機",
    "air_cleaner": "空氣清淨機",
    "air_cleaner_1": "空氣清淨機",
    "robot_vacuum_1": "掃地機器人",
    "lights_1": "燈",
    "water_heater_1": "熱水器",
    "fridge_1": "冰箱",
    "tv_1": "電視",
    "curtain_1": "窗簾",
    "door_lock_1": "大門門鎖",
    "security_camera_1": "監視器",
    "siren_1": "警報器",
    "motion_sensor_1": "動作感測器",
}


def log_print(message, *, end="\n", flush=False):
    print(message, end=end, flush=flush)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + end)


def _translate_value(key, value):
    if not isinstance(value, str):
        return value
    if key == "location":
        return LOCATION_TRANSLATIONS.get(value, value)
    if key == "device_id":
        return DEVICE_ID_TRANSLATIONS.get(value, value)
    return value


def _localize_obj(obj):
    if isinstance(obj, list):
        return [_localize_obj(item) for item in obj]
    if isinstance(obj, dict):
        localized = {}
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                localized[key] = _localize_obj(value)
            else:
                localized[key] = _translate_value(key, value)
        return localized
    return obj


def localize_output(output):
    if not isinstance(output, str) or not output.strip():
        return output
    stripped = output.strip()
    try:
        parsed = json.loads(stripped)
        localized = _localize_obj(parsed)
        return json.dumps(localized, ensure_ascii=False)
    except Exception:
        # Best-effort string replacements for stream/partial outputs.
        for src, dst in LOCATION_TRANSLATIONS.items():
            stripped = stripped.replace(src, dst)
        for src, dst in DEVICE_ID_TRANSLATIONS.items():
            stripped = stripped.replace(src, dst)
        return stripped


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
            output = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
            util, mem = output.split(",")
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
        if not self.gpu_stats:
            return "無 GPU 數據。"
        return (
            f"    GPU 使用率: 平均 {statistics.mean(self.gpu_stats):.1f}% | 最大 {max(self.gpu_stats):.1f}%\n"
            f"    GPU 顯存 (VRAM): 平均 {statistics.mean(self.vram_stats):.0f} MB | 最大 {max(self.vram_stats):.0f} MB"
        )


def build_tools(count):
    devices = [
        "ac",
        "air_purifier",
        "robot_vacuum",
        "lights",
        "water_heater",
        "fridge",
        "dehumidifier",
        "humidifier",
        "tv",
        "curtain",
        "door_lock",
        "security_camera",
        "siren",
        "motion_sensor",
    ]
    actions = [
        "set_power",
        "set_mode",
        "set_level",
        "set_timer",
        "lock",
        "unlock",
        "arm",
        "disarm",
        "start_recording",
        "stop_recording",
        "get_status",
    ]
    prioritized_pairs = [
        ("door_lock", "lock"),
        ("door_lock", "unlock"),
        ("door_lock", "get_status"),
        ("security_camera", "start_recording"),
        ("security_camera", "stop_recording"),
        ("security_camera", "get_status"),
        ("siren", "set_power"),
        ("siren", "set_mode"),
        ("siren", "get_status"),
        ("motion_sensor", "arm"),
        ("motion_sensor", "disarm"),
        ("motion_sensor", "get_status"),
        ("lights", "set_level"),
        ("lights", "set_power"),
        ("lights", "set_timer"),
        ("lights", "get_status"),
        ("curtain", "set_level"),
        ("curtain", "set_power"),
        ("curtain", "get_status"),
        ("tv", "set_timer"),
        ("tv", "set_power"),
        ("tv", "get_status"),
    ]

    tools = []
    seen = set()

    def add_tool(device, action):
        key = (device, action)
        if key in seen:
            return
        seen.add(key)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"{device}_{action}",
                    "description": f"智慧家庭控制：{device} {action}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "request_id": {"type": "string"},
                            "device_id": {"type": "string"},
                            "location": {"type": "string"},
                        },
                        "required": ["request_id", "device_id"],
                    },
                },
            }
        )

    # Ensure security and multi-tool devices are in the first N tools.
    for device, action in prioritized_pairs:
        add_tool(device, action)

    for device in devices:
        for action in actions:
            add_tool(device, action)

    return tools[:count]


TOOLS = build_tools(TOOL_COUNT)


def generate_request(idx):
    tool_needed = [
        (
            "請幫我把客廳冷氣調到 24 度並開啟睡眠模式，現在很熱。"
        ),
        (
            "家裡空氣品質不太好，請把空氣清淨機調到強力檔 30 分鐘。"
        ),
        (
            "幫我啟動掃地機器人，清掃客廳與餐廳並避開地毯區。"
        ),
        (
            "晚上 10 點請把客廳燈調到 40% 亮度並切成暖黃光。"
        ),
        (
            "冰箱門好像沒關好，請檢查門的狀態並提醒我。"
        ),
        (
            "請把熱水器設定為 42 度，並開啟節能模式。"
        ),
    ]
    multi_tool_needed = [
        "我要外出，請開啟客廳燈並調到 30% 亮度，同時拉上客廳窗簾。",
        "晚上睡覺前，請關閉客廳燈並拉上窗簾，再把電視設定 30 分鐘後自動關閉。",
        "啟動夜間安全模式：把客廳燈調到 20% 亮度並切成暖黃光，同時關閉窗簾。",
        "我要出門，請鎖上大門並啟動客廳監視器錄影。",
        "聽到異常聲響，請開啟警報器並啟動監視器錄影。",
    ]
    if idx % 5 == 0:
        return random.choice(multi_tool_needed)
    return random.choice(tool_needed)

def select_tools(prompt, all_tools):
    keyword_map = {
        "ac": ["冷氣", "空調", "冷房", "air conditioner", "ac"],
        "air_purifier": ["空氣清淨機", "空氣淨化", "air purifier"],
        "robot_vacuum": ["掃地機器人", "掃地", "robot vacuum"],
        "lights": ["燈", "燈光", "照明", "lights", "light"],
        "water_heater": ["熱水器", "water heater"],
        "fridge": ["冰箱", "fridge", "refrigerator"],
        "dehumidifier": ["除濕機", "除濕", "dehumidifier"],
        "humidifier": ["加濕器", "加濕", "humidifier"],
        "tv": ["電視", "tv", "television"],
        "curtain": ["窗簾", "curtain", "blind"],
        "door_lock": ["門鎖", "大門", "lock", "door"],
        "security_camera": ["監視器", "攝影機", "camera", "security"],
        "siren": ["警報", "警鈴", "siren", "alarm"],
        "motion_sensor": ["感測", "偵測", "sensor", "motion"],
    }
    matched_devices = set()
    for device, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword in prompt:
                matched_devices.add(device)
                break
    if not matched_devices:
        return all_tools
    filtered = []
    for tool in all_tools:
        name = tool.get("function", {}).get("name", "")
        device = name.split("_", 1)[0]
        if device in matched_devices:
            filtered.append(tool)
    return filtered if filtered else all_tools


async def make_request(session, req_id, stream):
    prompt = generate_request(req_id)
    tools_for_request = select_tools(prompt, TOOLS)
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是智慧家庭助理，請一律使用中文。"
                    "你必須依使用者需求呼叫最合適的工具。"
                    "只能呼叫與裝置與動作相符的工具；若同時需要多個動作，請呼叫多個工具。"
                    "工具參數值（如 location、device_id）請務必使用中文（不要輸出 living_room、door_lock_1 這類英文/代碼）。"
                    "若不需要工具，請用一句簡短中文回答。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "tools": tools_for_request,
        "tool_choice": "required",
        "temperature": 0.2,
        "stream": stream,
        "max_tokens": 80,
    }

    start = time.perf_counter()
    ttft = None
    output = ""
    tokens = 0

    try:
        async with session.post(
            SGLANG_URL, json=payload, headers={"Authorization": f"Bearer {API_KEY}"}
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                log_print(f"Error: HTTP {resp.status} - {error_text}")
                return {"ttft": 0, "total": 0, "tokens": 1}
            if stream:
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    if line == "data: [DONE]":
                        break
                    if ttft is None:
                        ttft = time.perf_counter()
                    try:
                        delta = json.loads(line[6:])["choices"][0]["delta"]
                        if "tool_calls" in delta:
                            for tc in delta["tool_calls"]:
                                if "function" in tc:
                                    args = tc["function"].get("arguments", "")
                                    output += args
                                    tokens += len(args) / 4
                        if "content" in delta and delta["content"]:
                            output += delta["content"]
                            tokens += len(delta["content"]) / 4
                    except:
                        pass
            else:
                data = await resp.json()
                ttft = time.perf_counter()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content") or ""
                output += content
                tokens += len(content) / 4
                tool_calls = message.get("tool_calls") or []
                for tc in tool_calls:
                    function = tc.get("function", {})
                    args = function.get("arguments", "") or ""
                    output += args
                    tokens += len(args) / 4
    except Exception as e:
        log_print(f"Error: {e}")

    end = time.perf_counter()
    display_output = localize_output(output)
    log_print(
        f"[請求 ID: {req_id}]\n輸入: {prompt}\n輸出: {display_output}\n" + "-" * 30,
        flush=True,
    )
    return {
        "ttft": (ttft - start) if ttft else (end - start),
        "total": end - start,
        "tokens": max(1, tokens),
    }


async def run(concurrency, total, stream, tps_non_stream):
    mode = "stream" if stream else "non-stream"
    tps_mode = "non-stream" if tps_non_stream else mode
    os.makedirs(LOG_DIR, exist_ok=True)
    log_print(f"\n[{datetime.now().isoformat(timespec='seconds')}] 基準測試開始")
    log_print(
        f"正在執行 {total} 個請求（並發數：{concurrency}），tools={TOOL_COUNT}，mode={mode}, tps_mode={tps_mode}...",
        flush=True,
    )
    monitor = SystemMonitor()
    monitor.start()

    request_stream = stream
    if tps_non_stream:
        request_stream = False

    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        tasks = []
        start_time = time.perf_counter()
        for i in range(total):
            async def worker(idx):
                async with sem:
                    return await make_request(session, idx, request_stream)
            tasks.append(worker(i))
        results = await asyncio.gather(*tasks)
        end_time = time.perf_counter()

    monitor.stop()
    valid = [r for r in results if "error" not in r]
    duration = end_time - start_time

    log_print("\n" + "=" * 50)
    log_print(f"測試報告（{TOOL_COUNT} Tools TPS）")
    log_print("=" * 50)
    log_print(f"平均首字延遲 (TTFT): {statistics.mean(r['ttft'] for r in valid):.4f}s")
    log_print(f"平均總耗時: {statistics.mean(r['total'] for r in valid):.4f}s")
    log_print(f"系統吞吐量 (RPS): {len(valid) / duration:.2f} req/s")
    log_print(f"系統生成速度 (TPS): {sum(r['tokens'] for r in valid) / duration:.2f} tokens/s")
    log_print("-" * 50)
    log_print("資源使用監控")
    log_print(monitor.report())
    log_print("=" * 50)
    log_print(f"[{datetime.now().isoformat(timespec='seconds')}] 基準測試結束")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--total", type=int, default=20)
    parser.add_argument("--stream", action="store_true", default=True)
    parser.add_argument("--no-stream", action="store_false", dest="stream")
    parser.add_argument(
        "--tps-non-stream",
        action="store_true",
        help="Force non-stream mode when measuring TPS, even if stream is enabled.",
    )
    args = parser.parse_args()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args.concurrency, args.total, args.stream, args.tps_non_stream))
