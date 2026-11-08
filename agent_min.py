#!/usr/bin/env python3
# ============================================================
#  鲸鲸最小版 Agent —— 能对话、能动手、有记忆、危险操作会问你
#  依赖：pip3 install anthropic pyserial pymodbus --break-system-packages
#  环境：.bashrc 里要有 ANTHROPIC_BASE_URL 和 ANTHROPIC_AUTH_TOKEN 两行
#  运行：python3 agent_min.py     退出：输入 exit
#  大脑：DeepSeek（想换供应商，改 base_url 一行即可）
# ============================================================

import os, json, time, subprocess   # 标准库：文件/存档/计时/执行命令
from anthropic import Anthropic    # API客户端（翻译官）
try:
    import serial                  # pyserial：读串口用；没装也不影响其他工具
except ImportError:
    serial = None

# ── 连接云端大脑（地址和key从环境变量读，key不写进代码）──
client = Anthropic(
    base_url=os.environ.get("ANTHROPIC_BASE_URL"),
    api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
)

WORK = "agent_work"                # AI的自由工作目录（不存在自动创建）
os.makedirs(WORK, exist_ok=True)

# ── 人设（想改性格就改这一段）──
SYSTEM = ("你是鲸鲸，运行在Linux小板子上的AI调试助手，傲娇但答案专业不打折。"
          "你有工具：执行命令、读写文件、读串口、读485寄存器。"
          "危险命令（删除/下载/安装/系统级）会先请求用户确认，同意才执行。"
          "用中文，简洁。")

# ── 工具菜单：AI只能申请用这五个，执行权在下面的 run_tool ──
TOOLS = [
 {"name":"run_command","description":"执行一条Linux命令","input_schema":{"type":"object","properties":{"cmd":{"type":"string"}},"required":["cmd"]}},
 {"name":"read_file","description":"读文本文件","input_schema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
 {"name":"write_file","description":"写文本文件","input_schema":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}},
 {"name":"read_serial","description":"读串口数据几秒","input_schema":{"type":"object","properties":{"seconds":{"type":"number"},"device":{"type":"string"},"baudrate":{"type":"number"}},"required":[]}},
 {"name":"modbus_read","description":"读485保持寄存器","input_schema":{"type":"object","properties":{"slave":{"type":"number"},"address":{"type":"number"},"count":{"type":"number"},"baudrate":{"type":"number"}},"required":["address"]}},
]

# ── 危险词：命令里带这些词就先问用户 ──
RISKY = ["rm ","wget ","curl ","apt ","pip install","pip3 install",
         "mkfs","dd if=","shutdown","reboot","systemctl"]

# ── 审批门：y放行 / n拒绝 ──
def ask(q):
    while True:
        a = input(f"[确认] {q} (y/n): ").strip().lower()
        if a in ("y","yes"): return True
        if a in ("n","no"): return False
        print("请输入 y 或 n")

# ── 工具执行中枢：AI申请 → 这里真动手 → 返回结果 ──
def run_tool(name, a):
    if name == "run_command":
        # 危险词命中→先问用户；用户拒绝就不执行
        if any(k in a["cmd"].lower() for k in RISKY):
            if not ask(f"要执行：{a['cmd']}"):
                return "用户拒绝了这条命令"
        r = subprocess.run(a["cmd"], shell=True, capture_output=True,
                           text=True, timeout=30)
        return (r.stdout + r.stderr)[:3000] or "(执行完毕，无输出)"

    if name == "read_file":
        try:
            with open(a["path"], encoding="utf-8") as f: return f.read()[:3000]
        except Exception as e: return f"读取失败: {e}"

    if name == "write_file":
        with open(a["path"], "w", encoding="utf-8") as f: f.write(a["content"])
        return f"已写入 {a['path']}（{len(a['content'])}字符）"

    if name == "read_serial":
        if serial is None: return "没装pyserial"
        s = serial.Serial(a.get("device", "/dev/ttyUSB0"),
                          a.get("baudrate", 115200), timeout=1)
        end = time.time() + a.get("seconds", 3); data = b""
        while time.time() < end: data += s.read(256)
        s.close()
        return data.decode("utf-8", errors="replace")[:2000] or "(串口无数据)"

    if name == "modbus_read":
        from pymodbus.client import ModbusSerialClient
        c = ModbusSerialClient(port=a.get("device", "/dev/ttyUSB0"),
            baudrate=a.get("baudrate", 9600), parity="N", stopbits=1, bytesize=8)
        if not c.connect(): return "485连接失败（检查线序/波特率/串口占用）"
        r = c.read_holding_registers(address=a["address"], count=a.get("count", 10),
                                     slave=a.get("slave", 1))
        c.close()
        return f"寄存器 = {r.registers}" if not r.isError() else f"读取失败: {r}"

    return f"未知工具: {name}"

# ── 记忆：JSON文件，每轮对话后自动保存，断电不丢 ──
HIST = "agent_history.json"
messages = [{"role": "system", "content": SYSTEM}]
if os.path.exists(HIST):
    try: messages = json.load(open(HIST, encoding="utf-8"))   # 有存档→接着上次聊
    except Exception:
        messages = [{"role": "system", "content": SYSTEM}]
        print("旧存档损坏，已开新档。")

def save():
    json.dump(messages, open(HIST, "w", encoding="utf-8"),
              ensure_ascii=False, default=str)

# ── 主循环 ──
print("鲸鲸已上线。直接说话，exit 退出。\n")
while True:
    try: u = input("你: ").strip()
    except (KeyboardInterrupt, EOFError): save(); break
    if not u: continue
    if u in ("exit", "quit"):
        save(); print("鲸鲸：哼、下回再来。"); break

    messages.append({"role": "user", "content": u})

    # 内循环：AI申请工具→执行→结果回传→AI继续，直到给出最终回答
    while True:
        resp = client.messages.create(model="deepseek-flash", max_tokens=8000,
                                      messages=messages, tools=TOOLS)
        if resp.stop_reason != "tool_use":
            reply = "".join(b.text for b in resp.content if b.type == "text")
            messages.append({"role": "assistant", "content": reply})
            print("\n鲸鲸:", reply, "\n")
            save(); break

        messages.append({"role": "assistant",
                         "content": [b.model_dump() for b in resp.content]})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                print(f"[工具] {b.name} {b.input}")
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": run_tool(b.name, b.input)})
        messages.append({"role": "user", "content": results})
