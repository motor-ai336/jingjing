# 命令速查 v2（2026-11-08 全量更新，替代旧版）

═══════════════ ① 系统/网络（板子SSH内）═══════════════

sudo nmcli device wifi list                                          # 列出WiFi
sudo nmcli device wifi connect "WiFi名" password "WiFi密码"            # 连WiFi
ip addr show wlan0                                                   # 查板子IP
sudo iw dev wlan0 set power_save off                                 # 关省电(治打字回显慢,重启失效)
sudo iw dev wlan0 link                                               # 查信号(-42满分/-70勉强/-80挪板)
echo "nameserver 223.5.5.5" | sudo tee /etc/resolv.conf              # DNS钉死(治命令前卡几秒)
sudo sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list && sudo apt update   # apt换源
free -h                                                              # 看内存
ls -lh 文件                                                          # 看文件大小(验证写入/粘贴事故必备)

═══════════════ ② 笔记本(PowerShell)═══════════════

ipconfig                       # 笔记本IP(必须与板子同网段)
ping 192.168.2.xx              # 连通测试(首包超时=ARP正常)
ssh pi@192.168.2.xx            # SSH

═══════════════ ③ AI安装与配置 ═══════════════

sudo apt update && sudo apt install -y python3-pip
pip3 install anthropic pyocd pymodbus pyserial --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
python3 -c "import anthropic, pyocd, pymodbus, serial; print('四件套OK')"

# API身份(DeepSeek)
echo 'export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic' >> ~/.bashrc
echo 'export ANTHROPIC_AUTH_TOKEN=sk-你的key' >> ~/.bashrc
source ~/.bashrc

# 查询真实模型名(权威)——已知: deepseek-flash(快,1M上下文,识图) / deepseek-v4-pro(重)
curl -s https://api.deepseek.com/models -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN"

# 切换模型的两种方式
# 方式1(推荐): agent对话内 /model deepseek-v4-pro   ← v6已加此命令
# 方式2: 改agent.py里 MODEL  = "deepseek-flash" 那行，重启生效

═══════════════ ④ agent.py 对话内命令(鲸鲸v6+)═══════════════

/new                          开新话题(旧对话自动归档为 agent_history.json.时间戳)
/img 图片路径 [问题]           发图识图(图先经MobaXterm左侧面板拖进板子)
/effort low|high|max          思考档位(low快/high均衡/max深思,思考消耗max_tokens)
/model deepseek-flash         切换大脑(deepseek-v4-pro=疑难重活)
/paste                        多行粘贴模式(单独一行EOF结束)——发长任务/代码用
exit                          退出
[审批门]                      危险操作(删除/下载/安装/系统级)弹y/n,同意才执行
[行动纪律]                    AI宣告不做会被自动推回执行(最多3次)

═══════════════ ⑤ M3 仿真器(openocd/pyocd)═══════════════

# 接线: ST-LINK SWDIO→板SWDIO, SWCLK→SWCLK, GND→GND
lsusb                                          # 确认ST-LINK枚举
sudo apt install -y openocd
openocd -f interface/stlink.cfg -c "transport select hla_swd; adapter speed 1000; init; targets; shutdown"
pyocd list                                     # 列下载器
pyocd udev                                     # 装权限规则后拔插
pyocd pack install stm32f103c8                 # 按目标芯片型号改
pyocd flash demo.hex -t stm32f103c8            # 烧录
pyocd reset -t stm32f103c8                     # 复位
pyocd commander -t stm32f103c8                 # 交互调试(reg/mem32/read32,quit退出)



═══════════════ ⑧ 系统加固杂项 ═══════════════

# swapfile(1GB内存安全网)
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab ; free -h
# zram(不磨SD卡,二选一)
sudo apt install -y zram-tools
# ping权限修复(白名单里的ping跑不起来时)
sudo setcap 'cap_net_raw+ep' $(which ping)
# 关闭括号粘贴(MobaXterm粘贴污染事故根治)
sed -i '/enable-bracketed-paste/d' ~/.inputrc
bind 'set enable-bracketed-paste off' 2>/dev/null

═══════════════ ⑨ 常用Linux ═══════════════

ls / cat 文件 / nano 文件(Ctrl+O存,Ctrl+X退,Alt+N关自动缩进) / top(q退)
wc -l 文件       # 数行数(验收AI写文件)
free -h          # 内存
sudo reboot / sudo poweroff
Ctrl+C 中断 / Ctrl+U 清行 / Ctrl+W 删词 / 右键粘贴 / 选中即复制
