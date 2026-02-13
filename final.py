import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
import threading
import time
import os
import random
import requests
import math 

# ================= 1. 硬件与AI模块加载 =================
try:
    from stepper_driver import StepperMotor
    from ir_sensor import IRSensor
    from sorter_motor import SorterMotor
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    # print("提示: 硬件驱动未找到，进入 [模拟演示模式]")

try:
    from ai_detector import DefectDetector
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    # print("提示: ai_detector.py 未找到，AI功能已禁用")

# ================= 2. 全局配置 =================
# ✅ [关键修改] 已改为你的阿里云服务器公网 IP
SERVER_IP = "39.106.39.101" 
SERVER_URL = f"http://{SERVER_IP}:5000"
SAVE_FOLDER = "/home/pi/conveyor_photos"

STEP_DELAY = 0.0006 
BATCH_STEPS = 50     

# ================= 3. 全局状态 =================
lock = threading.RLock()
sys_state = {
    "running": False,
    "user": None,
    "good": 0, "bad": 0,
    "defects": {"Wrinkles": 0, "Scratchs": 0, "Other": 0},
    "img": None, "res": "等待检测", "conf": 0.0, "time": "--:--:--", # 增加了 conf 字段
    "log": "系统初始化完成", "exit": False,
    "new_records": [],
    "status": {"motor": False, "sensor": True, "cloud": False}
}

# ================= 4. 视觉主题 (HMI 工业暗色系) =================
COLOR_BG = "#0f172a"        # 极深蓝黑 (全局背景)
COLOR_CARD = "#1e293b"      # 卡片背景 (浅一度)
COLOR_ACCENT = "#38bdf8"    # 科技蓝 (高亮强调)
COLOR_OK = "#10b981"        # 状态绿
COLOR_NG = "#ef4444"        # 警告红
COLOR_TEXT_MAIN = "#ffffff" # 纯白
COLOR_TEXT_SUB = "#94a3b8"  # 灰蓝辅助字

# ================= 5. 通信与保存逻辑 =================

def verify_login_on_server(username, password):
    try:
        # 尝试连接服务器进行登录验证
        data = {'username': username, 'password': password}
        resp = requests.post(f"{SERVER_URL}/login_api", json=data, timeout=3) # [优化] 超时时间稍微改长一点适应公网
        if resp.status_code == 200 and resp.json().get('success'): 
            sys_state["status"]["cloud"] = True
            return True
    except: 
        sys_state["status"]["cloud"] = False
    
    # 离线兜底登录 (如果服务器连不上，允许本地admin登录)
    if username == "admin" and password == "123": return True
    return False

def upload_task(path, result_str, confidence):
    try:
        filename = os.path.basename(path)
        with open(path, 'rb') as f:
            # [升级] 增加了 confidence 字段
            data = {
                'operator': sys_state['user'], 
                'result': result_str,
                'confidence': confidence
            }
            files = {'file': (filename, f, 'image/jpeg')}
            requests.post(f"{SERVER_URL}/upload", data=data, files=files, timeout=5)
        sys_state["status"]["cloud"] = True
    except: 
        sys_state["status"]["cloud"] = False

def save_snapshot(frame):
    if not os.path.exists(SAVE_FOLDER): 
        try: os.makedirs(SAVE_FOLDER)
        except: pass
    fname = f"img_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
    path = os.path.join(SAVE_FOLDER, fname)
    if not os.path.exists(os.path.dirname(path)): path = fname 
    import cv2
    cv2.imwrite(path, frame)
    return path

# ================= 6. 工作线程 (AI核心逻辑) =================

def worker_thread():
    global cv2
    import cv2
    
    if HARDWARE_AVAILABLE:
        motor = StepperMotor(); sensor = IRSensor(); pusher = SorterMotor(steps=400)
    else:
        class Mock: 
            def move_steps(self, *a, **k): time.sleep(0.01)
            def is_object_detected(self): return False
            def eject(self): pass
        motor=Mock(); sensor=Mock(); pusher=Mock()

    detector = None
    if AI_AVAILABLE:
        try: detector = DefectDetector(model_path='best.pt') 
        except: pass

    cap = cv2.VideoCapture(0)
    if not cap.isOpened(): print("提示: 未检测到摄像头，将使用黑屏模拟")
    cap.set(3, 1280); cap.set(4, 720) 
    
    active_items = []
    last_detect = False

    while not sys_state["exit"]:
        if not sys_state["running"]:
            time.sleep(0.1); continue

        if HARDWARE_AVAILABLE: motor.move_steps(BATCH_STEPS, delay=STEP_DELAY)
        else: time.sleep(0.02)
        
        for item in active_items: item['steps'] += BATCH_STEPS
        
        detected = sensor.is_object_detected()
        if not HARDWARE_AVAILABLE and random.random() < 0.005: detected = True 

        if detected and not last_detect:
            with lock: sys_state["log"] = "正在 AI 分析..."
            time.sleep(0.8) # 等待物体移动到相机下方
            
            frame = None
            if cap.isOpened():
                for _ in range(2): cap.read() # 清空缓存
                ret, frame = cap.read()
            
            # 如果没有摄像头或者读取失败，造一个假图
            if frame is None:
                import numpy as np
                frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                cv2.putText(frame, "No Camera", (50, 360), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 2)

            # --- AI 推理核心 ---
            if detector:
                # 真实 AI 检测
                is_bad, res_str, conf, ann_img = detector.detect(frame)
                save_img = ann_img 
            else:
                # 模拟 AI 检测
                is_bad = random.choice([True, False])
                res_str = "不合格" if is_bad else "合格"
                if is_bad and random.random() > 0.5: res_str += " (Wrinkle)"
                elif is_bad: res_str += " (Scratch)"
                
                # 模拟置信度
                conf = round(random.uniform(0.85, 0.99), 4)
                save_img = frame
            
            path = save_snapshot(save_img)
            curr_time = time.strftime("%H:%M:%S")
            
            with lock:
                sys_state["img"] = path
                sys_state["res"] = res_str
                sys_state["conf"] = conf # 记录置信度
                sys_state["time"] = curr_time
                sys_state["log"] = f"判定: {res_str} ({int(conf*100)}%)"
                
                detail_type = "正常"
                if is_bad: 
                    sys_state["bad"] += 1
                    if "Wrinkle" in res_str: 
                        sys_state["defects"]["Wrinkles"] += 1
                        detail_type = "褶皱"
                    elif "Scratch" in res_str: 
                        sys_state["defects"]["Scratchs"] += 1
                        detail_type = "划痕"
                    else: 
                        sys_state["defects"]["Other"] += 1
                        detail_type = "其他"
                else: 
                    sys_state["good"] += 1
                
                sys_state["new_records"].append({
                    "time": curr_time, 
                    "result": res_str, 
                    "detail": detail_type,
                    "conf": f"{int(conf*100)}%"
                })
            
            # [重要] 启动上传线程 (包含置信度)
            threading.Thread(target=upload_task, args=(path, res_str, conf)).start()
            
            active_items.append({'is_bad': is_bad, 'steps': 0})
        
        last_detect = detected

        for i in range(len(active_items)-1, -1, -1):
            item = active_items[i]
            # 剔除逻辑
            if item['is_bad'] and item['steps'] >= 6000:
                pusher.eject(); active_items.pop(i)
            elif not item['is_bad'] and item['steps'] > 8000:
                active_items.pop(i)
                
    if cap and cap.isOpened(): cap.release()

# ================= 7. 虚拟键盘 (保持不变) =================
class TouchKeyboard(tk.Toplevel):
    def __init__(self, target_entry, root, x, y):
        super().__init__(root)
        self.target = target_entry
        self.overrideredirect(True) 
        self.configure(bg=COLOR_CARD)
        self.geometry(f"780x300+{x}+{y}")
        self.attributes('-topmost', True) 
        self.mode = 0 
        self.layout_lower = [['1','2','3','4','5','6','7','8','9','0'],['q','w','e','r','t','y','u','i','o','p'],['a','s','d','f','g','h','j','k','l'],['z','x','c','v','b','n','m']]
        self.layout_upper = [['1','2','3','4','5','6','7','8','9','0'],['Q','W','E','R','T','Y','U','I','O','P'],['A','S','D','F','G','H','J','K','L'],['Z','X','C','V','B','N','M']]
        self.layout_sym = [['!','@','#','$','%','^','&','*','(',')'],['-','_','=','+','[',']','{','}','\\','|'],[';',':','\'','"',',','.','<','>','?','/'],['`','~']]
        title_bar = tk.Frame(self, bg=COLOR_ACCENT, height=8)
        title_bar.pack(fill="x")
        self.key_area = tk.Frame(self, bg=COLOR_CARD)
        self.key_area.pack(fill="both", expand=True, padx=5, pady=5)
        func_f = tk.Frame(self, bg=COLOR_CARD)
        func_f.pack(fill="x", padx=5, pady=5)
        self.btn_mode = tk.Button(func_f, text="大写", bg=COLOR_BG, fg="white", width=12, command=self.switch_mode, font=("Arial", 11, "bold"))
        self.btn_mode.pack(side="left", padx=2)
        tk.Button(func_f, text="空格", bg=COLOR_BG, fg="white", width=20, command=lambda: self.add_char(" ")).pack(side="left", padx=2)
        tk.Button(func_f, text="退格", bg="#f59e0b", fg="white", width=10, command=self.backspace).pack(side="left", padx=2)
        tk.Button(func_f, text="确定", bg=COLOR_OK, fg="white", width=10, command=self.destroy).pack(side="left", padx=2)
        tk.Button(func_f, text="关闭", bg="#ef4444", fg="white", width=8, command=self.destroy).pack(side="right", padx=2)
        self.render_keys()

    def switch_mode(self):
        self.mode = (self.mode + 1) % 3
        self.render_keys()

    def render_keys(self):
        for widget in self.key_area.winfo_children(): widget.destroy()
        if self.mode == 0: current_layout = self.layout_lower; self.btn_mode.config(text="大写", bg=COLOR_BG, fg="white")
        elif self.mode == 1: current_layout = self.layout_upper; self.btn_mode.config(text="符号", bg=COLOR_ACCENT, fg="black")
        else: current_layout = self.layout_sym; self.btn_mode.config(text="返回", bg="#f59e0b", fg="white")
        for row in current_layout:
            row_f = tk.Frame(self.key_area, bg=COLOR_CARD)
            row_f.pack(fill="both", expand=True)
            for char in row:
                tk.Button(row_f, text=char, font=("Arial", 13, "bold"), bg=COLOR_BG, fg="white", activebackground=COLOR_ACCENT, relief="flat", command=lambda c=char: self.add_char(c), width=4, height=1).pack(side="left", padx=2, pady=2, expand=True)

    def add_char(self, char): self.target.insert(tk.END, char)
    def backspace(self): txt = self.target.get(); self.target.delete(0, tk.END); self.target.insert(0, txt[:-1])

# ================= 8. GUI 界面类 (优化版) =================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("智能工业分拣系统 V10.0")
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg=COLOR_BG)
        self.tk_img = None; self.last_img = None
        self.kb_win = None 
        
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=COLOR_CARD, foreground="white", fieldbackground=COLOR_CARD, borderwidth=0, rowheight=30, font=("微软雅黑", 11))
        style.configure("Treeview.Heading", background=COLOR_BG, foreground="white", font=("微软雅黑", 11, "bold"), relief="flat")
        style.map("Treeview", background=[('selected', COLOR_ACCENT)], foreground=[('selected', 'white')])
        
        self.show_login()

    def open_keyboard(self, event, entry_widget):
        if self.kb_win: 
            try: self.kb_win.destroy()
            except: pass
        kb_w, kb_h = 780, 300
        screen_w = self.root.winfo_width(); screen_h = self.root.winfo_height()
        x = (screen_w - kb_w) // 2; y = screen_h - kb_h - 10 
        self.kb_win = TouchKeyboard(entry_widget, self.root, x, y)

    def draw_donut(self, canvas, x, y, r, percentage, color):
        canvas.delete("all")
        canvas.create_oval(x-r, y-r, x+r, y+r, outline="#334155", width=18)
        if percentage > 0: canvas.create_arc(x-r, y-r, x+r, y+r, start=90, extent=-360*percentage, style="arc", outline=color, width=18)
        canvas.create_text(x, y-15, text=f"{int(percentage*100)}%", fill="white", font=("Arial", 32, "bold"))
        canvas.create_text(x, y+25, text="综合良率", fill=COLOR_TEXT_SUB, font=("微软雅黑", 12))

    def draw_bar(self, canvas, x_start, y_base, bar_w, max_h, val, max_val, label, color):
        bar_h = (val / max_val) * max_h if max_val > 0 else 2
        canvas.create_rectangle(x_start, y_base-max_h, x_start+bar_w, y_base, fill="#334155", outline="")
        canvas.create_rectangle(x_start, y_base-bar_h, x_start+bar_w, y_base, fill=color, outline="")
        canvas.create_text(x_start+bar_w/2, y_base+20, text=label, fill=COLOR_TEXT_SUB, font=("微软雅黑", 10))
        canvas.create_text(x_start+bar_w/2, y_base-bar_h-12, text=str(val), fill="white", font=("Arial", 11))

    def show_login(self):
        for w in self.root.winfo_children(): w.destroy()
        tk.Frame(self.root, bg=COLOR_ACCENT, height=5).pack(fill="x", side="top")
        center = tk.Frame(self.root, bg=COLOR_BG)
        center.place(relx=0.5, rely=0.48, anchor="center")
        tk.Label(center, text="", font=("微软雅黑", 14), bg=COLOR_BG, fg=COLOR_ACCENT).pack()
        tk.Label(center, text="锂电池表面缺陷智能检测系统", font=("微软雅黑", 42, "bold"), bg=COLOR_BG, fg="white").pack(pady=(10, 30))
        stat_f = tk.Frame(center, bg=COLOR_BG); stat_f.pack(pady=(0, 20))
        tk.Label(stat_f, text="●", fg=COLOR_OK, bg=COLOR_BG, font=("Arial", 16)).pack(side="left")
        tk.Label(stat_f, text=" 系统自检完成，正在等待操作员登录", fg=COLOR_TEXT_SUB, bg=COLOR_BG, font=("微软雅黑", 12)).pack(side="left")
        card = tk.Frame(center, bg=COLOR_CARD, padx=60, pady=50, highlightbackground="#334155", highlightthickness=1)
        card.pack()
        tk.Label(card, text="操作员账号", font=("微软雅黑", 11, "bold"), bg=COLOR_CARD, fg=COLOR_TEXT_SUB).pack(anchor="w")
        self.entry_user = tk.Entry(card, font=("微软雅黑", 16), bg=COLOR_BG, fg="white", relief="flat", insertbackground="white", width=22)
        self.entry_user.pack(ipady=10, pady=(8, 25)); self.entry_user.insert(0, "admin")
        self.entry_user.bind("<Button-1>", lambda e: self.open_keyboard(e, self.entry_user))
        tk.Label(card, text="安全访问密码", font=("微软雅黑", 11, "bold"), bg=COLOR_CARD, fg=COLOR_TEXT_SUB).pack(anchor="w")
        self.entry_pwd = tk.Entry(card, show="●", font=("微软雅黑", 16), bg=COLOR_BG, fg="white", relief="flat", insertbackground="white", width=22)
        self.entry_pwd.pack(ipady=10, pady=(8, 35)); self.entry_pwd.insert(0, "123")
        self.entry_pwd.bind("<Button-1>", lambda e: self.open_keyboard(e, self.entry_pwd))
        tk.Button(card, text="进入系统", font=("微软雅黑", 15, "bold"), bg=COLOR_ACCENT, fg="#0f172a", relief="flat", command=self.do_login).pack(fill="x", ipady=12)
        footer = tk.Frame(self.root, bg=COLOR_BG)
        footer.pack(side="bottom", fill="x", pady=30, padx=50)
        self.lbl_login_time = tk.Label(footer, text="--", font=("Consolas", 14), bg=COLOR_BG, fg=COLOR_ACCENT)
        self.lbl_login_time.pack(side="right")
        self.update_time_loop()

    def do_login(self):
        if self.kb_win: 
            try: self.kb_win.destroy()
            except: pass
        if verify_login_on_server(self.entry_user.get(), self.entry_pwd.get()):
            sys_state["user"] = self.entry_user.get()
            self.show_dashboard()
            threading.Thread(target=worker_thread, daemon=True).start()
        else:
            messagebox.showerror("登录失败", "账号或密码错误")

    def show_dashboard(self):
        for w in self.root.winfo_children(): w.destroy()
        top = tk.Frame(self.root, bg=COLOR_CARD, height=80)
        top.pack(fill="x", side="top")
        tk.Label(top, text=" 🏭 生产线实时监控看板", font=("微软雅黑", 22, "bold"), bg=COLOR_CARD, fg="white").pack(side="left", padx=30, pady=15)
        top_right = tk.Frame(top, bg=COLOR_CARD)
        top_right.pack(side="right", padx=30)
        self.inds = {}
        status_box = tk.Frame(top_right, bg=COLOR_CARD)
        status_box.pack(side="right", padx=(20, 0)) 
        for k, n in [("motor", "电机驱动"), ("sensor", "红外感应"), ("cloud", "云端通信")]:
            f = tk.Frame(status_box, bg=COLOR_CARD); f.pack(side="left", padx=10)
            l = tk.Label(f, text="●", fg=COLOR_TEXT_SUB, bg=COLOR_CARD, font=("Arial", 16)); l.pack(side="left")
            tk.Label(f, text=n, bg=COLOR_CARD, fg=COLOR_TEXT_SUB, font=("微软雅黑", 10)).pack(side="left")
            self.inds[k] = l
        self.lbl_main_time = tk.Label(top_right, text="--:--:--", font=("Arial", 28, "bold"), bg=COLOR_CARD, fg=COLOR_ACCENT)
        self.lbl_main_time.pack(side="right")
        self.update_time_loop()
        content = tk.Frame(self.root, bg=COLOR_BG)
        content.pack(fill="both", expand=True, padx=20, pady=20)
        left = tk.Frame(content, bg=COLOR_BG)
        left.place(relx=0, rely=0, relwidth=0.62, relheight=1)
        self.img_lbl = tk.Label(left, bg="black", text="正在等待视频信号...", fg="white", font=("微软雅黑", 14))
        self.img_lbl.place(relx=0, rely=0, relwidth=1, relheight=0.68)
        info_panel = tk.Frame(left, bg=COLOR_CARD)
        info_panel.place(relx=0, rely=0.70, relwidth=1, relheight=0.30)
        info_left = tk.Frame(info_panel, bg=COLOR_CARD)
        info_left.place(relx=0, rely=0, relwidth=0.4, relheight=1)
        tk.Label(info_left, text="当前判定", font=("微软雅黑", 12), bg=COLOR_CARD, fg=COLOR_TEXT_SUB).pack(pady=(25, 5))
        self.lbl_res = tk.Label(info_left, text="等待中", font=("微软雅黑", 36, "bold"), bg=COLOR_CARD, fg=COLOR_TEXT_SUB)
        self.lbl_res.pack()
        
        # [UI微调] 显示置信度
        self.lbl_conf = tk.Label(info_left, text="置信度: --", font=("微软雅黑", 10), bg=COLOR_CARD, fg=COLOR_TEXT_SUB)
        self.lbl_conf.pack()

        info_right = tk.Frame(info_panel, bg=COLOR_CARD)
        info_right.place(relx=0.4, rely=0, relwidth=0.6, relheight=1)
        tk.Label(info_right, text="最近检测记录", font=("微软雅黑", 10, "bold"), bg=COLOR_CARD, fg=COLOR_TEXT_SUB).pack(anchor="w", padx=10, pady=(10, 5))
        columns = ("time", "res", "detail", "conf")
        self.tree = ttk.Treeview(info_right, columns=columns, show="headings", height=5)
        self.tree.heading("time", text="时间"); self.tree.column("time", width=70, anchor="center")
        self.tree.heading("res", text="结果"); self.tree.column("res", width=60, anchor="center")
        self.tree.heading("detail", text="类型"); self.tree.column("detail", width=60, anchor="center")
        self.tree.heading("conf", text="置信度"); self.tree.column("conf", width=60, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.tag_configure("ok", foreground="white"); self.tree.tag_configure("ng", foreground="#ff4d4d")
        
        right = tk.Frame(content, bg=COLOR_BG)
        right.place(relx=0.64, rely=0, relwidth=0.36, relheight=1)
        c1 = tk.Frame(right, bg=COLOR_CARD); c1.pack(fill="both", expand=True, pady=(0, 15))
        tk.Label(c1, text="产能统计数据", font=("微软雅黑", 12, "bold"), bg=COLOR_CARD, fg="white").pack(anchor="w", padx=15, pady=10)
        self.can_stat = tk.Canvas(c1, bg=COLOR_CARD, highlightthickness=0); self.can_stat.pack(fill="both", expand=True) 
        c2 = tk.Frame(right, bg=COLOR_CARD); c2.pack(fill="both", expand=True, pady=(0, 15))
        tk.Label(c2, text="缺陷类型分布", font=("微软雅黑", 12, "bold"), bg=COLOR_CARD, fg="white").pack(anchor="w", padx=15, pady=10)
        self.can_def = tk.Canvas(c2, bg=COLOR_CARD, highlightthickness=0); self.can_def.pack(fill="both", expand=True) 
        self.btn_run = tk.Button(right, text="▶ 启动生产线", bg=COLOR_OK, fg="white", font=("微软雅黑", 18, "bold"), relief="flat", command=self.toggle)
        self.btn_run.pack(fill="x", ipady=20) 
        tk.Button(right, text="退出系统", bg=COLOR_BG, fg=COLOR_TEXT_SUB, relief="flat", font=("微软雅黑", 11), command=self.root.destroy).pack(side="bottom", pady=10)
        self.update_ui()

    def update_time_loop(self):
        try:
            curr_str = time.strftime("%Y-%m-%d %H:%M:%S"); time_only = time.strftime("%H:%M:%S")
            try: self.lbl_login_time.config(text=curr_str)
            except: pass
            try: self.lbl_main_time.config(text=time_only)
            except: pass
            self.root.after(1000, self.update_time_loop)
        except: pass

    def toggle(self):
        sys_state["running"] = not sys_state["running"]
        self.btn_run.config(text="⏸ 暂停运行" if sys_state["running"] else "▶ 恢复运行", bg="#f59e0b" if sys_state["running"] else COLOR_OK)

    def update_ui(self):
        with lock:
            if sys_state["img"] and sys_state["img"] != self.last_img:
                try:
                    img = Image.open(sys_state["img"]).resize((800, 500))
                    self.tk_img = ImageTk.PhotoImage(img)
                    self.img_lbl.config(image=self.tk_img, text=""); self.last_img = sys_state["img"]
                except: pass
            
            res = sys_state["res"]
            self.lbl_res.config(text=res, fg=COLOR_OK if "合格" in res or "OK" in res else COLOR_NG)
            # 更新置信度标签
            try: self.lbl_conf.config(text=f"AI置信度: {int(sys_state['conf']*100)}%")
            except: pass
            
            if sys_state["new_records"]:
                for rec in sys_state["new_records"]:
                    tag = "ok" if "合格" in rec["result"] else "ng"
                    self.tree.insert("", 0, values=(rec["time"], rec["result"], rec["detail"], rec["conf"]), tags=(tag,))
                children = self.tree.get_children()
                if len(children) > 10:
                    for child in children[10:]: self.tree.delete(child)
                sys_state["new_records"] = [] 

            w1 = self.can_stat.winfo_width(); h1 = self.can_stat.winfo_height()
            w2 = self.can_def.winfo_width(); h2 = self.can_def.winfo_height()
            if w1 > 10:
                total = sys_state["good"] + sys_state["bad"]
                rate = sys_state["good"]/total if total > 0 else 0
                self.draw_donut(self.can_stat, w1/2, h1/2, 65, rate, COLOR_OK)
            if w2 > 10:
                self.can_def.delete("all")
                d = sys_state["defects"]; m = max(d.values()) if any(d.values()) else 1
                spacing = w2 / 4 
                self.draw_bar(self.can_def, spacing*0.8, h2-40, 40, h2-80, d["Wrinkles"], m, "褶皱", "#a78bfa")
                self.draw_bar(self.can_def, spacing*1.8, h2-40, 40, h2-80, d["Scratchs"], m, "划痕", "#f472b6")
                self.draw_bar(self.can_def, spacing*2.8, h2-40, 40, h2-80, d["Other"], m, "其他", COLOR_TEXT_SUB)
            
            self.inds["cloud"].config(fg=COLOR_OK if sys_state["status"]["cloud"] else COLOR_TEXT_SUB)
            self.inds["motor"].config(fg=COLOR_OK if sys_state["running"] else "#f59e0b")
        self.root.after(200, self.update_ui)

if __name__ == "__main__":
    root = tk.Tk(); app = App(root); root.mainloop()