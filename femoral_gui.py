#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股骨头坏死灰度分析 GUI应用
========================
功能：
- 上传图片 / 从DICOM校准 / 手动输入px/mm
- 自动/手动识别股骨头
- 画股骨头圆、r-6mm内圆
- 自动检测硬化带交点
- 计算灰度比值
- 保存结果图片

打包成exe: pyinstaller --onefile --windowed femoral_gui.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import cv2
import numpy as np
import os


class FemoralHeadAnalyzer:
    """股骨头分析核心类"""
    
    def __init__(self, px_per_mm=5.0):
        self.px_per_mm = px_per_mm
        self.image = None
        self.gray = None
        self.center = None
        self.radius = None
        self.inner_radius = None
        self.results = []
        
    def load_image(self, path):
        """加载图像（支持中文路径）"""
        # 使用 np.fromfile + cv2.imdecode 解决中文路径问题
        self.image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if self.image is None:
            raise ValueError(f"无法加载图像: {path}")
        self.gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        return self.image
    
    def detect_femoral_head(self, search_roi=None, min_r=30, max_r=150):
        """自动检测股骨头"""
        if self.gray is None:
            return None
            
        if search_roi:
            x, y, w, h = search_roi
            search = self.gray[y:y+h, x:x+w]
            offset = (x, y)
        else:
            search = self.gray
            offset = (0, 0)
        
        blurred = cv2.GaussianBlur(search, (9, 9), 2)
        
        for p2 in [25, 30, 20, 35, 40]:
            circles = cv2.HoughCircles(
                blurred, cv2.HOUGH_GRADIENT, 1.2, 50,
                param1=50, param2=p2, minRadius=min_r, maxRadius=max_r
            )
            if circles is not None:
                c = max(circles[0], key=lambda x: x[2])
                self.center = (int(c[0]) + offset[0], int(c[1]) + offset[1])
                self.radius = int(c[2])
                return self.center, self.radius
        return None
    
    def set_femoral_head(self, center, radius):
        """手动设置股骨头"""
        self.center = center
        self.radius = radius
    
    def find_sclerotic_intersections(self, inner_radius, n_samples=72):
        """找硬化带交点"""
        if self.gray is None or self.center is None:
            return []
        
        cx, cy = self.center
        samples = []
        
        for i in range(n_samples):
            angle = 2 * np.pi * i / n_samples
            x = int(cx + inner_radius * np.cos(angle))
            y = int(cy + inner_radius * np.sin(angle))
            
            if 0 <= x < self.gray.shape[1] and 0 <= y < self.gray.shape[0]:
                w = 2
                region = self.gray[max(0,y-w):y+w+1, max(0,x-w):x+w+1]
                samples.append({
                    'angle': angle, 'deg': i * 360 / n_samples,
                    'x': x, 'y': y, 'bright': float(np.mean(region))
                })
        
        if not samples:
            return []
        
        brights = [s['bright'] for s in samples]
        mean_b, std_b = np.mean(brights), np.std(brights)
        
        # 找峰值
        peaks = []
        for i in range(len(samples)):
            prev_i = (i - 1) % len(samples)
            next_i = (i + 1) % len(samples)
            if (samples[i]['bright'] > samples[prev_i]['bright'] and 
                samples[i]['bright'] > samples[next_i]['bright'] and
                samples[i]['bright'] > mean_b + 0.3 * std_b):
                peaks.append(samples[i])
        
        peaks.sort(key=lambda x: x['bright'], reverse=True)
        
        # 确保峰值间隔足够
        final_peaks = []
        for p in peaks:
            is_far = True
            for fp in final_peaks:
                angle_diff = abs(p['deg'] - fp['deg'])
                if angle_diff > 180:
                    angle_diff = 360 - angle_diff
                if angle_diff < 40:
                    is_far = False
                    break
            if is_far:
                final_peaks.append(p)
            if len(final_peaks) >= 2:
                break
        
        return final_peaks
    
    def analyze(self, inner_offset_mm=6.0, roi_offset_mm=2.0, roi_radius_mm=1.0):
        """执行分析"""
        if self.gray is None or self.center is None or self.radius is None:
            return []
        
        cx, cy = self.center
        inner_offset_px = int(inner_offset_mm * self.px_per_mm)
        self.inner_radius = max(10, self.radius - inner_offset_px)
        roi_offset_px = int(roi_offset_mm * self.px_per_mm)
        roi_radius_px = max(3, int(roi_radius_mm * self.px_per_mm))
        
        intersections = self.find_sclerotic_intersections(self.inner_radius)
        
        self.results = []
        for inter in intersections:
            dx = inter['x'] - cx
            dy = inter['y'] - cy
            dist = np.sqrt(dx*dx + dy*dy)
            if dist > 0:
                ux, uy = dx/dist, dy/dist
            else:
                ux, uy = 0, -1
            
            # 坏死区ROI（向外）
            necrosis_x = int(inter['x'] + ux * roi_offset_px)
            necrosis_y = int(inter['y'] + uy * roi_offset_px)
            
            # 硬化带ROI（向内）
            sclerotic_x = int(inter['x'] - ux * roi_offset_px)
            sclerotic_y = int(inter['y'] - uy * roi_offset_px)
            
            g_necrosis = self._calc_roi_gray(necrosis_x, necrosis_y, roi_radius_px)
            g_sclerotic = self._calc_roi_gray(sclerotic_x, sclerotic_y, roi_radius_px)
            
            ratio = g_sclerotic / g_necrosis if g_necrosis > 0 else 0
            
            self.results.append({
                'intersection': inter,
                'necrosis': (necrosis_x, necrosis_y),
                'sclerotic': (sclerotic_x, sclerotic_y),
                'roi_radius': roi_radius_px,
                'g_necrosis': g_necrosis,
                'g_sclerotic': g_sclerotic,
                'ratio': ratio
            })
        
        return self.results
    
    def _calc_roi_gray(self, cx, cy, r):
        """计算ROI平均灰度"""
        mask = np.zeros(self.gray.shape, np.uint8)
        cv2.circle(mask, (cx, cy), r, 255, -1)
        pixels = self.gray[mask > 0]
        return float(np.mean(pixels)) if len(pixels) > 0 else 0
    
    def draw_result(self):
        """绘制结果图像"""
        if self.image is None or self.center is None:
            return None
        
        vis = self.image.copy()
        cx, cy = self.center
        
        # 股骨头（绿色）
        cv2.circle(vis, self.center, self.radius, (0, 255, 0), 2)
        
        # 圆心（红色十字）
        cv2.line(vis, (cx-10, cy), (cx+10, cy), (0, 0, 255), 2)
        cv2.line(vis, (cx, cy-10), (cx, cy+10), (0, 0, 255), 2)
        
        # r-6mm内圆（青色）
        if self.inner_radius:
            cv2.circle(vis, self.center, self.inner_radius, (255, 255, 0), 2)
        
        # 交点和ROI
        for r in self.results:
            inter = r['intersection']
            # 交点（橙色）
            cv2.circle(vis, (inter['x'], inter['y']), 4, (0, 165, 255), -1)
            
            # 硬化带ROI（绿色）
            cv2.circle(vis, r['sclerotic'], r['roi_radius'], (0, 255, 0), 2)
            
            # 坏死区ROI（红色）
            cv2.circle(vis, r['necrosis'], r['roi_radius'], (0, 0, 255), 2)
            
            # 连线
            cv2.line(vis, r['sclerotic'], r['necrosis'], (200, 200, 200), 1)
        
        return vis


class FemoralHeadApp:
    """GUI应用主类"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("股骨头坏死灰度分析")
        self.root.state('zoomed')  # 默认全屏
        self.root.configure(bg='#2b2b2b')
        
        # 分析器
        self.analyzer = FemoralHeadAnalyzer()
        
        # 变量
        self.image_path = None
        self.current_image = None
        self.display_image = None
        self.click_points = []  # 用于手动选择
        self.manual_mode = False  # 手动圆心模式
        self.intersection_mode = False  # 手动交点模式
        self.intersection_points = []  # 手动交点坐标
        self.necrosis_direction_point = None  # 坏死区方向点
        self.ruler_mode = False  # 标尺校准模式
        self.ruler_points = []   # 标尺校准点
        self.ruler_backup_image = None  # 标尺校准时的备份图像
        self.zoom_scale = 1.0  # 图片缩放比例
        self.close_btn_coords = None  # 关闭按钮坐标

        # 拖动相关变量
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.image_offset_x = 0  # 图片偏移量
        self.image_offset_y = 0
        self.is_dragging = False

        # 缩放优化相关
        self._pil_cache = None       # 缓存颜色转换后的PIL图像
        self._cache_id = None        # 缓存标识（检测图像变化）
        self._zoom_timer = None      # 缩放防抖定时器

        # 参数变量
        self.px_per_mm = tk.DoubleVar(value=5.0)
        self.inner_offset = tk.DoubleVar(value=6.0)
        self.roi_radius = tk.DoubleVar(value=1.0)
        
        self.setup_ui()
    
    def setup_ui(self):
        """设置界面"""
        # 顶部工具栏
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # 按钮样式
        style = ttk.Style()
        style.configure('TButton', font=('Microsoft YaHei', 10))
        
        # 上传图片按钮
        ttk.Button(toolbar, text="上传图片", command=self.load_image).pack(side=tk.LEFT, padx=5)

        # DICOM校准按钮
        ttk.Button(toolbar, text="从DICOM校准", command=self.calibrate_dicom).pack(side=tk.LEFT, padx=5)

        # 标尺校准按钮
        ttk.Button(toolbar, text="标尺校准", command=self.start_ruler_calibration).pack(side=tk.LEFT, padx=5)

        # px/mm 输入框（可显示默认值，也可手动修改）
        ttk.Label(toolbar, text="px/mm:").pack(side=tk.LEFT, padx=(5, 0))
        self.pxmm_entry = ttk.Entry(toolbar, textvariable=self.px_per_mm, width=6)
        self.pxmm_entry.pack(side=tk.LEFT)
        self.pxmm_source_label = ttk.Label(toolbar, text="(默认)", foreground='gray',
                                           font=('Microsoft YaHei', 9))
        self.pxmm_source_label.pack(side=tk.LEFT, padx=(2, 5))

        # 参数输入
        ttk.Label(toolbar, text="内缩r-").pack(side=tk.LEFT, padx=(5, 0))
        ttk.Entry(toolbar, textvariable=self.inner_offset, width=5).pack(side=tk.LEFT)
        ttk.Label(toolbar, text="mm").pack(side=tk.LEFT)

        ttk.Label(toolbar, text="ROI半径:").pack(side=tk.LEFT, padx=(5, 0))
        ttk.Entry(toolbar, textvariable=self.roi_radius, width=5).pack(side=tk.LEFT)
        ttk.Label(toolbar, text="mm").pack(side=tk.LEFT)

        # 分析按钮
        ttk.Button(toolbar, text="自动分析", command=self.auto_analyze).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="手动交点", command=self.manual_select_intersection).pack(side=tk.LEFT, padx=5)

        # 保存和重置
        ttk.Button(toolbar, text="保存图片", command=self.save_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="清除标注", command=self.clear_annotations).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="重置", command=self.reset).pack(side=tk.LEFT, padx=5)
        
        # 主内容区域
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左侧：图像显示区
        self.canvas_frame = ttk.Frame(main_frame)
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg='#1e1e1e', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # Windows滚轮
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)    # Linux滚轮上
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)    # Linux滚轮下
        
        # 右侧：结果面板
        self.result_frame = ttk.Frame(main_frame, width=280)
        self.result_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        self.result_frame.pack_propagate(False)
        
        # 结果标题
        ttk.Label(self.result_frame, text="分析结果", font=('Microsoft YaHei', 14, 'bold')).pack(pady=10)
        
        # 灰度比值显示
        ttk.Label(self.result_frame, text="灰度比值 (硬化带/坏死区)", 
                  font=('Microsoft YaHei', 10)).pack(pady=5)
        
        self.ratio_labels = []
        for i in range(3):
            label = ttk.Label(self.result_frame, text="", font=('Microsoft YaHei', 12), foreground='cyan')
            label.pack(pady=2)
            self.ratio_labels.append(label)
        
        ttk.Separator(self.result_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # 平均灰度比
        ttk.Label(self.result_frame, text="平均灰度比", font=('Microsoft YaHei', 10)).pack(pady=5)
        self.avg_ratio_label = ttk.Label(self.result_frame, text="--", 
                                          font=('Microsoft YaHei', 24, 'bold'), foreground='#00ff00')
        self.avg_ratio_label.pack(pady=10)
        
        ttk.Separator(self.result_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # 图例
        ttk.Label(self.result_frame, text="图例:", font=('Microsoft YaHei', 11, 'bold')).pack(pady=5, anchor='w')
        
        legends = [
            ("● 绿色大圆 = 股骨头", "#00ff00"),
            ("● 红色十字 = 圆心", "#ff0000"),
            ("● 青色圆 = r-6mm圆", "#00ffff"),
            ("● 橙色点 = 硬化带交点", "#ffa500"),
            ("● 绿色小圆 = 硬化带ROI", "#00ff00"),
            ("● 红色小圆 = 坏死区ROI", "#ff0000"),
        ]
        
        for text, color in legends:
            ttk.Label(self.result_frame, text=text, foreground=color, 
                      font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, 
                                     font=('Microsoft YaHei', 9), foreground='#00ff00')
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
    
    def load_image(self):
        """加载图片"""
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff"),
                       ("所有文件", "*.*")]
        )
        if path:
            try:
                self.image_path = path
                self.analyzer.load_image(path)
                self.current_image = self.analyzer.image.copy()
                self.zoom_scale = 1.0  # 重置缩放比例
                self.image_offset_x = 0  # 重置偏移
                self.image_offset_y = 0
                self.display_current_image()
                self.status_var.set(f"已加载: {os.path.basename(path)}")
                self.clear_results()
            except Exception as e:
                messagebox.showerror("错误", f"无法加载图片: {e}")
    
    def display_current_image(self, fast=False):
        """显示当前图像
        fast=True: 使用快速缩放（滚轮缩放时）
        fast=False: 使用高质量缩放（最终渲染）
        """
        if self.current_image is None:
            self.canvas.delete("all")
            self.close_btn_coords = None
            return

        # 缓存颜色转换后的PIL图像（避免每次都转换）
        cache_id = id(self.current_image)
        if self._pil_cache is None or self._cache_id != cache_id:
            img_rgb = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
            self._pil_cache = Image.fromarray(img_rgb)
            self._cache_id = cache_id

        img_pil = self._pil_cache

        # 缩放适应画布
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        if canvas_w > 1 and canvas_h > 1:
            img_w, img_h = img_pil.size
            base_scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
            scale = base_scale * self.zoom_scale
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            if new_w > 0 and new_h > 0:
                # 快速模式用 NEAREST，高质量用 LANCZOS
                resample = Image.Resampling.NEAREST if fast else Image.Resampling.LANCZOS
                img_pil = img_pil.resize((new_w, new_h), resample)

        self.display_image = ImageTk.PhotoImage(img_pil)

        self.canvas.delete("all")

        # 计算图片位置（包含拖动偏移）
        img_x = canvas_w // 2 + self.image_offset_x
        img_y = canvas_h // 2 + self.image_offset_y

        self.canvas.create_image(img_x, img_y, anchor=tk.CENTER, image=self.display_image, tags="image")

        # 绘制关闭按钮（右上角X图标）
        self.draw_close_button()
    
    def on_canvas_resize(self, event):
        """画布大小改变时重绘"""
        if self.current_image is not None:
            self.display_current_image()

    def draw_close_button(self):
        """绘制关闭按钮（右上角X图标）"""
        if self.current_image is None:
            self.close_btn_coords = None
            return

        # 按钮位置和大小
        btn_size = 24
        padding = 10
        x1 = self.canvas.winfo_width() - padding - btn_size
        y1 = padding
        x2 = x1 + btn_size
        y2 = y1 + btn_size

        # 保存按钮坐标用于点击检测
        self.close_btn_coords = (x1, y1, x2, y2)

        # 绘制圆形背景
        self.canvas.create_oval(x1, y1, x2, y2, fill='#ff4444', outline='#cc0000', width=2, tags="close_btn")

        # 绘制X
        margin = 7
        self.canvas.create_line(x1 + margin, y1 + margin, x2 - margin, y2 - margin,
                               fill='white', width=2, tags="close_btn")
        self.canvas.create_line(x1 + margin, y2 - margin, x2 - margin, y1 + margin,
                               fill='white', width=2, tags="close_btn")

    def on_mouse_wheel(self, event):
        """鼠标滚轮缩放"""
        if self.current_image is None:
            return

        # 获取滚轮方向，每次固定增减10%
        if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
            self.zoom_scale += 0.1
        elif event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
            self.zoom_scale -= 0.1

        # 限制缩放范围 10%-250%
        self.zoom_scale = max(0.1, min(2.5, self.zoom_scale))

        # 快速渲染（低质量，不卡顿）
        self.display_current_image(fast=True)
        self.status_var.set(f"缩放: {self.zoom_scale:.0%}")

        # 取消之前的高质量渲染定时器
        if self._zoom_timer is not None:
            self.root.after_cancel(self._zoom_timer)

        # 停止滚动 150ms 后再高质量渲染
        self._zoom_timer = self.root.after(150, self._zoom_finalize)

    def _zoom_finalize(self):
        """缩放结束后高质量渲染"""
        self._zoom_timer = None
        self.display_current_image(fast=False)

    def close_image(self):
        """关闭当前图片"""
        self.current_image = None
        self.display_image = None
        self.image_path = None
        self.analyzer = FemoralHeadAnalyzer()
        self.zoom_scale = 1.0
        self.image_offset_x = 0  # 重置偏移
        self.image_offset_y = 0
        self.close_btn_coords = None
        self.manual_mode = False
        self.intersection_mode = False
        self.intersection_points = []
        self.necrosis_direction_point = None
        self.ruler_mode = False
        self.ruler_points = []
        self.click_points = []
        self._pil_cache = None
        self._cache_id = None

        # 清空画布和结果
        self.canvas.delete("all")
        self.clear_results()
        self.pxmm_source_label.config(text="(默认)", foreground='gray')
        self.px_per_mm.set(5.0)
        self.status_var.set("图片已关闭")
    
    def on_canvas_click(self, event):
        """画布按下事件"""
        # 检查是否点击了关闭按钮
        if self.close_btn_coords is not None:
            x1, y1, x2, y2 = self.close_btn_coords
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.close_image()
                return

        # 记录拖动起始位置
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.is_dragging = False

    def on_canvas_drag(self, event):
        """画布拖动事件"""
        if self.current_image is None:
            return

        # 计算移动距离
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y

        # 如果移动超过5像素，认为是拖动
        if not self.is_dragging and (abs(dx) > 5 or abs(dy) > 5):
            self.is_dragging = True
            self.canvas.config(cursor="fleur")  # 切换为移动光标
            self.canvas.delete("close_btn")     # 隐藏关闭按钮

        if self.is_dragging:
            # 更新图片偏移
            self.image_offset_x += dx
            self.image_offset_y += dy
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            # 只移动图片，不移动关闭按钮
            self.canvas.move("image", dx, dy)

    def on_canvas_release(self, event):
        """画布释放事件"""
        # 如果是拖动，恢复光标并重绘
        if self.is_dragging:
            self.is_dragging = False
            self.canvas.config(cursor="")  # 恢复默认光标
            self.draw_close_button()       # 重绘关闭按钮（固定位置）
            return

        # 以下是点击逻辑
        if self.analyzer.gray is None:
            return

        # 计算实际图像坐标
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        img_h, img_w = self.analyzer.gray.shape

        base_scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
        scale = base_scale * self.zoom_scale  # 考虑用户缩放
        disp_w = int(img_w * scale)
        disp_h = int(img_h * scale)

        # 考虑图片偏移
        offset_x = (canvas_w - disp_w) // 2 + self.image_offset_x
        offset_y = (canvas_h - disp_h) // 2 + self.image_offset_y

        img_x = int((event.x - offset_x) / scale)
        img_y = int((event.y - offset_y) / scale)

        if not (0 <= img_x < img_w and 0 <= img_y < img_h):
            return

        # 标尺校准模式
        if self.ruler_mode:
            self.ruler_points.append((img_x, img_y))

            if len(self.ruler_points) == 1:
                # 绘制第一个红点
                self.draw_ruler_marks()
                self.status_var.set("已选择标尺起点，请点击标尺终点...")
            elif len(self.ruler_points) >= 2:
                # 绘制第二个红点和连线
                self.draw_ruler_marks()

                # 计算像素距离
                x1, y1 = self.ruler_points[0]
                x2, y2 = self.ruler_points[1]
                pixel_distance = np.sqrt((x2-x1)**2 + (y2-y1)**2)

                # 弹窗输入实际距离
                self.ask_ruler_distance(pixel_distance)

                self.ruler_mode = False
                self.ruler_points = []
            return

        # 手动选择模式
        if self.manual_mode:
            self.click_points.append((img_x, img_y))

            if len(self.click_points) == 1:
                self.status_var.set("已选择圆心，请点击股骨头边缘确定半径...")
            elif len(self.click_points) >= 2:
                # 计算半径
                cx, cy = self.click_points[0]
                ex, ey = self.click_points[1]
                radius = int(np.sqrt((ex-cx)**2 + (ey-cy)**2))

                self.analyzer.set_femoral_head((cx, cy), radius)

                # 根据平均股骨头直径(44mm)自动校准 px/mm
                self.auto_calibrate_pxmm()

                self.do_analysis()

                self.manual_mode = False
                self.click_points = []
            return

        # 手动交点模式（2个交点 + 1个坏死区方向）
        if self.intersection_mode:
            if len(self.intersection_points) < 2:
                # 收集交点
                self.intersection_points.append((img_x, img_y))
                self.draw_intersection_marks()

                if len(self.intersection_points) == 1:
                    self.status_var.set("手动交点：请点击第2个硬化带交点...")
                elif len(self.intersection_points) == 2:
                    self.status_var.set("手动交点：请点击坏死区域（确定方向）...")
            else:
                # 第3次点击 - 坏死区方向
                self.necrosis_direction_point = (img_x, img_y)
                self.draw_intersection_marks()  # 绘制坏死区标记

                # 自动检测圆心并执行分析
                self.do_manual_intersection_analysis()

                self.intersection_mode = False
                self.intersection_points = []
                self.necrosis_direction_point = None
            return

    def draw_intersection_marks(self):
        """绘制手动选择的交点和坏死区标记"""
        if self.intersection_backup_image is None:
            return

        # 从备份图像复制
        img = self.intersection_backup_image.copy()

        # 绘制交点（橙色）
        for (x, y) in self.intersection_points:
            cv2.circle(img, (x, y), 6, (0, 165, 255), -1, cv2.LINE_AA)

        # 绘制坏死区方向点（红色）
        if self.necrosis_direction_point is not None:
            nx, ny = self.necrosis_direction_point
            cv2.circle(img, (nx, ny), 6, (0, 0, 255), -1, cv2.LINE_AA)
            # 从两个交点中心画一条线到坏死区点
            if len(self.intersection_points) == 2:
                mid_x = (self.intersection_points[0][0] + self.intersection_points[1][0]) // 2
                mid_y = (self.intersection_points[0][1] + self.intersection_points[1][1]) // 2
                cv2.line(img, (mid_x, mid_y), (nx, ny), (0, 0, 255), 2, cv2.LINE_AA)

        # 更新显示
        self.current_image = img
        self._pil_cache = None  # 清除缓存
        self.display_current_image()

    def do_manual_intersection_analysis(self):
        """根据手动选择的交点和坏死区方向执行分析"""
        if len(self.intersection_points) < 2 or self.necrosis_direction_point is None:
            return

        self.status_var.set("正在自动检测股骨头圆心...")
        self.root.update()

        # 自动检测股骨头圆心（与自动分析相同）
        result = self.analyzer.detect_femoral_head()
        if result is None:
            messagebox.showwarning("警告", "自动检测股骨头失败，请确保图像清晰")
            return

        # 根据平均股骨头直径(44mm)自动校准 px/mm
        self.auto_calibrate_pxmm()

        cx, cy = self.analyzer.center
        roi_offset_px = int(2.0 * self.px_per_mm.get())  # 2mm偏移
        roi_radius_px = max(3, int(self.roi_radius.get() * self.px_per_mm.get()))

        # 计算坏死区方向（从两个交点中点指向坏死区点击位置）
        mid_x = (self.intersection_points[0][0] + self.intersection_points[1][0]) // 2
        mid_y = (self.intersection_points[0][1] + self.intersection_points[1][1]) // 2
        nx, ny = self.necrosis_direction_point

        # 坏死区方向向量（从交点中点指向坏死区）
        dir_x = nx - mid_x
        dir_y = ny - mid_y
        dir_len = np.sqrt(dir_x**2 + dir_y**2)
        if dir_len > 0:
            dir_ux, dir_uy = dir_x / dir_len, dir_y / dir_len
        else:
            dir_ux, dir_uy = 0, -1

        # 计算内圆半径（用于绘制）
        inner_offset_px = int(self.inner_offset.get() * self.px_per_mm.get())
        self.analyzer.inner_radius = max(10, self.analyzer.radius - inner_offset_px)

        # 构建结果
        self.analyzer.results = []
        for (ix, iy) in self.intersection_points:
            # 坏死区ROI（沿坏死区方向偏移）
            necrosis_x = int(ix + dir_ux * roi_offset_px)
            necrosis_y = int(iy + dir_uy * roi_offset_px)

            # 硬化带ROI（反向偏移）
            sclerotic_x = int(ix - dir_ux * roi_offset_px)
            sclerotic_y = int(iy - dir_uy * roi_offset_px)

            g_necrosis = self.analyzer._calc_roi_gray(necrosis_x, necrosis_y, roi_radius_px)
            g_sclerotic = self.analyzer._calc_roi_gray(sclerotic_x, sclerotic_y, roi_radius_px)

            ratio = g_sclerotic / g_necrosis if g_necrosis > 0 else 0

            self.analyzer.results.append({
                'intersection': {'x': ix, 'y': iy},
                'necrosis': (necrosis_x, necrosis_y),
                'sclerotic': (sclerotic_x, sclerotic_y),
                'roi_radius': roi_radius_px,
                'g_necrosis': g_necrosis,
                'g_sclerotic': g_sclerotic,
                'ratio': ratio
            })

        # 绘制结果
        self.current_image = self.analyzer.draw_result()
        self._pil_cache = None  # 清除缓存
        self.display_current_image()

        # 更新结果显示
        self.update_results(self.analyzer.results)
        self.status_var.set(f"手动交点分析完成 | ROI={self.roi_radius.get()}mm")

    def start_ruler_calibration(self):
        """开始标尺校准"""
        if self.analyzer.gray is None:
            messagebox.showwarning("警告", "请先加载图片")
            return

        self.ruler_mode = True
        self.ruler_points = []
        self.manual_mode = False  # 退出手动圆心模式
        self.intersection_mode = False  # 退出手动交点模式
        # 保存原始图像，用于校准完成后恢复
        self.ruler_backup_image = self.current_image.copy() if self.current_image is not None else None
        self.status_var.set("标尺校准：请点击标尺起点...")

    def draw_ruler_marks(self):
        """在图像上绘制标尺校准的红点和红线"""
        if self.ruler_backup_image is None or len(self.ruler_points) == 0:
            return

        # 从备份图像复制，避免累加绘制
        img = self.ruler_backup_image.copy()

        # 如果有两个点，绘制红线（先画线再画点，点在上层）
        if len(self.ruler_points) >= 2:
            x1, y1 = self.ruler_points[0]
            x2, y2 = self.ruler_points[1]
            cv2.line(img, (x1, y1), (x2, y2), (0, 0, 255), 2, cv2.LINE_AA)  # 抗锯齿红线

        # 绘制红点
        for (x, y) in self.ruler_points:
            cv2.circle(img, (x, y), 6, (0, 0, 255), -1, cv2.LINE_AA)  # 红色实心圆，抗锯齿

        # 更新显示
        self.current_image = img
        self.display_current_image()

    def ask_ruler_distance(self, pixel_distance):
        """弹窗输入标尺实际距离"""
        dialog = tk.Toplevel(self.root)
        dialog.title("输入标尺距离")

        # 设置弹窗大小
        dialog_width = 320
        dialog_height = 180

        # 获取屏幕尺寸，计算居中靠上位置
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = screen_height // 4  # 靠上位置（屏幕高度的1/4处）

        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=f"测量的像素距离: {pixel_distance:.1f} 像素",
                  font=('Microsoft YaHei', 10)).pack(pady=10)
        ttk.Label(dialog, text="请输入这两点之间的实际距离 (mm):").pack(pady=5)

        entry = ttk.Entry(dialog, width=10)
        entry.insert(0, "100")  # 默认100mm
        entry.pack(pady=5)
        entry.select_range(0, tk.END)
        entry.focus()

        def confirm():
            try:
                mm_distance = float(entry.get())
                if mm_distance > 0:
                    # 计算 px/mm
                    px_mm = pixel_distance / mm_distance
                    self.px_per_mm.set(round(px_mm, 2))
                    self.analyzer.px_per_mm = px_mm
                    self.pxmm_source_label.config(text="(标尺)", foreground='#ffff00')
                    self.status_var.set(f"标尺校准完成: {px_mm:.2f} px/mm")
                    # 恢复原始图像（移除红点红线）
                    restore_image()
                    dialog.destroy()
                else:
                    messagebox.showerror("错误", "请输入正数")
            except ValueError:
                messagebox.showerror("错误", "请输入有效数字")

        def restore_image():
            """恢复原始图像"""
            if self.ruler_backup_image is not None:
                self.current_image = self.ruler_backup_image.copy()
                self.display_current_image()
                self.ruler_backup_image = None

        def on_cancel():
            """取消时恢复原始图像"""
            restore_image()
            self.status_var.set("标尺校准已取消")
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_cancel)  # 处理关闭按钮

        ttk.Button(dialog, text="确定", command=confirm).pack(pady=10)
        entry.bind("<Return>", lambda e: confirm())

    def calibrate_dicom(self):
        """从DICOM校准"""
        try:
            import pydicom
            path = filedialog.askopenfilename(
                title="选择DICOM文件",
                filetypes=[("DICOM文件", "*.dcm"), ("所有文件", "*.*")]
            )
            if path:
                ds = pydicom.dcmread(path)
                if hasattr(ds, 'PixelSpacing'):
                    spacing = float(ds.PixelSpacing[0])
                    px_mm = 1.0 / spacing
                    self.px_per_mm.set(round(px_mm, 2))
                    self.analyzer.px_per_mm = px_mm
                    self.pxmm_source_label.config(text="(DICOM)", foreground='#00ff00')
                    self.status_var.set(f"已从DICOM校准: {px_mm:.2f} px/mm")
                else:
                    messagebox.showwarning("警告", "DICOM文件中没有PixelSpacing信息")
        except ImportError:
            messagebox.showerror("错误", "需要安装pydicom库\npip install pydicom")
        except Exception as e:
            messagebox.showerror("错误", f"读取DICOM失败: {e}")

    def auto_calibrate_pxmm(self):
        """根据平均股骨头直径(44mm)自动校准px/mm"""
        if self.analyzer.radius is None:
            return

        # 成年人平均股骨头直径 44mm，半径 22mm
        avg_radius_mm = 22.0
        detected_radius_px = self.analyzer.radius

        # 计算 px/mm = 像素半径 / 毫米半径
        px_mm = detected_radius_px / avg_radius_mm

        # 更新值
        self.px_per_mm.set(round(px_mm, 2))
        self.analyzer.px_per_mm = px_mm
        self.pxmm_source_label.config(text="(自动)", foreground='cyan')
        self.status_var.set(f"已按平均股骨头直径(44mm)校准: {px_mm:.2f} px/mm")

    def auto_analyze(self):
        """自动分析"""
        if self.analyzer.gray is None:
            messagebox.showwarning("警告", "请先加载图片")
            return

        self.status_var.set("正在检测股骨头...")
        self.root.update()

        # 尝试自动检测
        result = self.analyzer.detect_femoral_head()

        if result is None:
            messagebox.showwarning("警告", "自动检测失败，请使用手动选择")
            return

        # 根据平均股骨头直径(44mm)自动校准 px/mm
        self.auto_calibrate_pxmm()

        self.do_analysis()

    def manual_select_center(self):
        """手动选择圆心模式"""
        if self.analyzer.gray is None:
            messagebox.showwarning("警告", "请先加载图片")
            return

        self.manual_mode = True
        self.intersection_mode = False
        self.ruler_mode = False
        self.click_points = []
        self.status_var.set("手动圆心：请点击股骨头圆心...")

    def manual_select_intersection(self):
        """手动选择交点模式（2个交点 + 1个坏死区方向）"""
        if self.analyzer.gray is None:
            messagebox.showwarning("警告", "请先加载图片")
            return

        self.intersection_mode = True
        self.manual_mode = False
        self.ruler_mode = False
        self.intersection_points = []
        self.necrosis_direction_point = None  # 坏死区方向点
        # 保存当前图像用于绘制交点
        self.intersection_backup_image = self.analyzer.image.copy()
        self.current_image = self.intersection_backup_image.copy()
        self._pil_cache = None
        self.display_current_image()
        self.status_var.set("手动交点：请点击第1个硬化带交点...")

    def do_analysis(self):
        """执行分析"""
        self.status_var.set("正在分析...")
        self.root.update()
        
        # 更新参数
        self.analyzer.px_per_mm = self.px_per_mm.get()
        
        # 执行分析
        results = self.analyzer.analyze(
            inner_offset_mm=self.inner_offset.get(),
            roi_offset_mm=2.0,
            roi_radius_mm=self.roi_radius.get()
        )
        
        # 绘制结果
        self.current_image = self.analyzer.draw_result()
        self.display_current_image()
        
        # 更新结果显示
        self.update_results(results)
        
        self.status_var.set(f"分析完成 | r-{self.inner_offset.get()}mm | ROI={self.roi_radius.get()}mm")
    
    def update_results(self, results):
        """更新结果显示"""
        # 清空之前的结果
        for label in self.ratio_labels:
            label.config(text="")
        
        # 显示每个交点的结果
        for i, r in enumerate(results[:3]):
            text = f"交点{i+1}: {r['ratio']:.4f}"
            self.ratio_labels[i].config(text=text)
        
        # 平均值
        if results:
            avg = np.mean([r['ratio'] for r in results])
            self.avg_ratio_label.config(text=f"{avg:.4f}")
        else:
            self.avg_ratio_label.config(text="--")
    
    def clear_results(self):
        """清空结果"""
        for label in self.ratio_labels:
            label.config(text="")
        self.avg_ratio_label.config(text="--")
    
    def save_image(self):
        """保存结果图片"""
        if self.current_image is None:
            messagebox.showwarning("警告", "没有可保存的图片")
            return
        
        path = filedialog.asksaveasfilename(
            title="保存图片",
            defaultextension=".png",
            filetypes=[("PNG图片", "*.png"), ("JPEG图片", "*.jpg"), ("所有文件", "*.*")]
        )
        if path:
            cv2.imwrite(path, self.current_image)
            self.status_var.set(f"已保存: {path}")
    
    def clear_annotations(self):
        """清除图片上的标注（保留原图）"""
        if self.analyzer.image is None:
            messagebox.showwarning("警告", "没有已加载的图片")
            return

        # 恢复原始图像
        self.current_image = self.analyzer.image.copy()
        self._pil_cache = None
        self.display_current_image()

        # 清除分析结果
        self.analyzer.center = None
        self.analyzer.radius = None
        self.analyzer.inner_radius = None
        self.analyzer.results = []

        # 清空结果显示
        self.clear_results()
        self.status_var.set("已清除标注")

    def reset(self):
        """重置"""
        self.analyzer = FemoralHeadAnalyzer(px_per_mm=self.px_per_mm.get())
        self.current_image = None
        self.image_path = None
        self.manual_mode = False
        self.click_points = []
        
        self.canvas.delete("all")
        self.clear_results()
        self.status_var.set("已重置")


def main():
    root = tk.Tk()
    
    # 设置主题
    style = ttk.Style()
    style.theme_use('clam')
    
    # 深色主题配置
    style.configure('.', background='#2b2b2b', foreground='white')
    style.configure('TFrame', background='#2b2b2b')
    style.configure('TLabel', background='#2b2b2b', foreground='white')
    style.configure('TButton', background='#404040', foreground='white')
    style.map('TButton', background=[('active', '#505050')])
    style.configure('TEntry', fieldbackground='white', foreground='black')
    
    app = FemoralHeadApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
