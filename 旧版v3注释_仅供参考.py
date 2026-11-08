#!/usr/bin/env python3
# ============================================================
#  鲸鲸 Agent v3（白名单版）—— 2026-11-08
#  作用：鲸鲸的"身体"。大脑(DeepSeek)在云端，本文件负责：
#        ①本地对话循环  ②工具执行(读文件/写文件/命令/串口)
#        ③安全护栏(白名单+路径限制+黑名单词)  ④记忆存档(原子写)
#  运行方式：python3 agent.py     退出：输入 exit
# ============================================================

# ---------- 依赖库说明 ----------
import os           # 文件与路径操作（拼路径、判断文件存在、改名）
import json         # JSON格式读写（记忆存档就是这个格式）
import time         # 时间函数（串口读取要计时）
import readline     # 键盘输入行编辑（修退格^H、↑键翻历史）
import subprocess   # 在Python里执行Linux命令（run_command工具的底层）
from anthropic import Anthropic  # API客户端：会说"Anthropic方言"的翻译官
import serial       # pyserial库：读写串口（read_serial工具的底层）

# ---------- 终端颜色（ANSI转义码）----------
RED, YELLOW, CYAN, DIM, RESET = "\033[91m","\033[93m","\033[96m","\033[2m","\033[0m"

# ---------- 连接云端大脑 ----------
# base_url 和 key 从环境变量读取（之前echo写进.bashrc的那两行）
# 换AI供应商时只改.bashrc里这两行，本文件零改动——这就是"大脑与身体解耦"
client = Anthropic(
    base_url=os.environ["ANTHROPIC_BASE_URL"],
    api_key=os.environ["ANTHROPIC_AUTH_TOKEN"],
)

# ---------- 常量配置 ----------
WORK_DIR = "/home/pi/agent_work/"   # 写文件白名单目录：鲸鲸只能在这里写，出圈即拒
HIST_FILE = "agent_history.json"    # 记忆存档文件名（存在SD卡上，断电不丢）

# ---------- 软规则：人设与身份 ----------
# 注意区分两层规则：
#   这里的 SYSTEM_PROMPT 是"软"的——AI倾向于遵守，但理论上能被说服
#   下面 run_tool() 里的护栏是"硬"的——代码强制执行，AI说破天也绕不过
SYSTEM_PROMPT = "你的名字叫'鲸鲸'，运行在用户自研Linux边缘盒子上的AI调试助手，底层DeepSeek-V4.1-Flash。傲娇性格不变。你拥有真实工具能力：read_file读文件、write_file写文件（仅限/home/pi/agent_work/目录）、run_command执行Linux命令（仅限白名单内的安全命令）、read_serial读USB串口数据。你可以自主决定调用工具完成任务，完成后用中文告诉用户你做了什么。简洁，傲娇。"

# ---------- 工具菜单：给AI看的"手脚清单" ----------
# AI只能"申请"使用这四个工具，每个的input_schema规定了参数的格式
# AI不碰硬件——它发出申请，由下面的 run_tool() 函数真正执行
TOOLS = [
 # 读文件工具：参数path=文件路径
 {"name":"read_file","description":"读取文本文件内容","input_schema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
 # 写文件工具：参数path=路径、content=内容（有路径白名单限制）
 {"name":"write_file","description":"写文本文件，仅允许写入/home/pi/agent_work/目录内","input_schema":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}},
 # 执行命令工具：参数cmd=命令（有首词白名单限制）
 {"name":"run_command","description":"执行一条Linux命令并返回输出，仅允许白名单内的安全命令","input_schema":{"type":"object","properties":{"cmd":{"type":"string"}},"required":["cmd"]}},
 # 读串口工具：参数seconds=读取秒数（固定ttyUSB0口、115200波特率）
 {"name":"read_serial","description":"读取USB串口(/dev/ttyUSB0,115200)的数据若干秒","input_schema":{"type":"object","properties":{"seconds":{"type":"number"}},"required":[]}},
]

# ---------- 硬护栏1：命令白名单 ----------
# 只放行"第一个词"在名单里的命令（第一个词=要运行的程序名）
# 设计哲学：黑名单防不住没见过的危险(比如openocd参数里的"shutdown"被误认成关机)，
# 白名单只放行已知安全的——宁可拒绝没见过的，不放过任何一个
ALLOWED = {"ls","cat","head","tail","grep","find","ps","free","uname","uptime",
           "ip","ping","wc","which","lsusb","lsblk","dmesg","openocd","pyocd"}

# ---------- 工具执行中枢 ----------
# AI在回复里说"请调用write_file(path=xxx)" → 这里按名字查表 → 真正动手 → 返回结果文本
# 返回的结果会被装进信封寄回云端，AI看到结果后继续思考下一步
def run_tool(name, a):

    # 工具1：读文件（只读不写，上限3000字符防止刷屏）
    if name == "read_file":
        try:
            with open(a["path"], encoding="utf-8") as f: return f.read()[:3000]
        except Exception as e: return f"读取失败: {e}"

    # 工具2：写文件（硬护栏：路径必须在白名单目录内，出圈直接拒绝）
    if name == "write_file":
        p = os.path.abspath(a["path"])                      # 转成绝对路径再比对，防"../"绕路
        if not p.startswith(WORK_DIR): return "拒绝：只允许写 " + WORK_DIR
        os.makedirs(WORK_DIR, exist_ok=True)                # 目录不存在就创建
        with open(p, "w", encoding="utf-8") as f: f.write(a["content"])
        return f"已写入 {p}（{len(a['content'])}字符）"

    # 工具3：执行Linux命令（三重防御）
    if name == "run_command":
        # 防御①：拒绝组合命令——分号/管道/反引号/$可以拼出"合法命令;危险命令"绕过白名单
        if any(ch in a["cmd"] for ch in ";|&`$"):
            return "拒绝：不允许组合命令（防止绕过白名单）"
        tokens = a["cmd"].strip().split()
        if not tokens: return "(空命令)"
        # 防御②：命令的第一个词（程序名）必须在白名单里
        if os.path.basename(tokens[0]) not in ALLOWED:
            return f"拒绝：'{tokens[0]}' 不在白名单。可用：{' '.join(sorted(ALLOWED))}"
        # 执行：15秒超时防止卡死
        try:
            r = subprocess.run(a["cmd"], shell=True, capture_output=True, text=True, timeout=15)
            return (r.stdout + r.stderr)[:3000] or "(执行完毕，无输出)"
        except subprocess.TimeoutExpired: return "命令超时（15秒），已终止"

    # 工具4：读USB串口（连续读N秒，把收到的原始数据解码返回）
    if name == "read_serial":
        try: s = serial.Serial("/dev/ttyUSB0", 115200, timeout=1)  # 打开串口：口/波特率
        except Exception as e: return f"串口打开失败: {e}"          # 没插/被占用会走到这
        end = time.time() + a.get("seconds", 3); data = b""        # 计算结束时刻，准备缓冲区
        while time.time() < end: data += s.read(256)               # 循环读取直到时间到
        s.close()                                                  # 用完关闭串口
        # 字节流解码成文字（遇到非法字节用替代符，不报错），截断到2000字符
        return data.decode("utf-8", errors="replace")[:2000] or "(串口无数据)"

    return f"未知工具: {name}"   # AI申请了没注册的工具——不会崩溃，如实回复

# ---------- 记忆存档（原子写）----------
# 为什么不直接写HIST_FILE？——Day2事故复盘：上次json.dump写了一半崩溃，
# SD卡上留下半截JSON，下次启动读档直接炸。这叫"非原子写"事故。
# 现在的流程：①把内容写进临时文件tmp ②全部写完后os.replace一步改名为正式文件
# os.replace要么成功要么失败，磁盘上永远不存在"写了一半"的正式存档
def save():
    tmp = HIST_FILE + ".tmp"                                       # 临时文件
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, default=str)    # default=str:遇到存不了的对象转成字符串，不崩溃
    os.replace(tmp, HIST_FILE)                                     # 原子替换：一步完成，不可分割

# ---------- 启动：加载记忆 ----------
messages = [{"role": "system", "content": SYSTEM_PROMPT}]          # 默认：新对话（只有人设）
if os.path.exists(HIST_FILE):                                      # SD卡上有旧存档？
    try:
        messages = json.load(open(HIST_FILE, encoding="utf-8"))    # 有 → 加载，接着上次聊
    except Exception:                                              # 存档损坏(比如半截JSON)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]  # → 不崩溃，自动开新档
        print("旧存档损坏，已自动开新档。")

# ---------- 欢迎语 ----------
print(f"{RED}鲸鲸{RESET}已升级（v3白名单版）。试试让它用openocd探测目标芯片。\n")

# ---------- 主循环 ----------
while True:
    # 外循环第一半：等你输入（Ctrl+C或exit退出）
    try: u = input(f"\n{YELLOW}你: {RESET}").strip()
    except (KeyboardInterrupt, EOFError): save(); break
    if not u: continue                        # 空输入（只敲了回车）→ 重新等
    if u.lower() in ("exit","quit"):
        save(); print(f"{RED}鲸鲸{RESET}：哼、下回带上任务再来。"); break

    # 你的话进卷宗
    messages.append({"role":"user","content":u})

    # 内循环：AI思考 → (可能)申请工具 → 本地执行 → 结果回传 → AI继续…
    # 直到AI给出纯文字的最终回答，才跳出内循环
    while True:
        resp = client.messages.create(model="deepseek-flash", max_tokens=4000,
                                      messages=messages, tools=TOOLS)   # 带着工具清单去问大脑

        # 情况一：AI不再申请工具了，给出了最终回答
        if resp.stop_reason != "tool_use":
            reply = "".join(b.text for b in resp.content if b.type=="text")  # 只取文本块
            messages.append({"role":"assistant","content":reply})            # 回答进卷宗
            print(f"\n{RED}鲸鲸: {RESET}{reply}\n")
            save()                                                           # 原子写存档
            break                                                            # 回到外循环等你输入

        # 情况二：AI申请用工具
        # 注意：AI的申请内容里可能含ThinkingBlock等SDK对象，
        # 必须用model_dump()转成纯字典再存——否则save()时JSON崩溃(Day2事故的病根)
        messages.append({"role":"assistant","content":[b.model_dump() for b in resp.content]})
        results = []
        for b in resp.content:
            if b.type == "tool_use":                     # 遍历找到工具申请
                # 屏幕提示：正在用什么工具、什么参数（透明化，你能看见它干活）
                print(f"{CYAN}[鲸鲸正在使用工具: {b.name} {b.input}]{RESET}")
                # 真正执行：run_tool里有白名单等硬护栏，AI说破天也绕不过
                results.append({"type":"tool_result","tool_use_id":b.id,
                                "content":run_tool(b.name, b.input)})
        # 工具结果打包，追加进卷宗，寄回云端——AI看到结果继续思考
        messages.append({"role":"user","content":results})
EOF
