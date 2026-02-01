# 股骨头坏死灰度分析工具 - 打包指南

## 功能介绍

这是一个用于分析股骨头坏死X光片的桌面应用程序，功能包括：
- 上传图片
- 从DICOM文件校准px/mm
- 手动输入px/mm
- 自动/手动识别股骨头
- 自动检测硬化带交点
- 计算灰度比值（硬化带/坏死区）
- 保存分析结果图片

## 安装依赖

```bash
pip install opencv-python numpy pillow pydicom pyinstaller
```

## 直接运行（不打包）

```bash
python femoral_gui.py
```

## 打包成EXE

### 方法1：单文件打包（推荐）

```bash
pyinstaller --onefile --windowed --name "股骨头坏死分析" femoral_gui.py
```

生成的exe文件在 `dist/股骨头坏死分析.exe`

### 方法2：带图标打包

先准备一个ico图标文件，然后：

```bash
pyinstaller --onefile --windowed --icon=icon.ico --name "股骨头坏死分析" femoral_gui.py
```

### 方法3：使用spec文件（更多控制）

1. 先生成spec文件：
```bash
pyinstaller --onefile --windowed --name "股骨头坏死分析" femoral_gui.py
```

2. 编辑生成的 `股骨头坏死分析.spec` 文件

3. 重新打包：
```bash
pyinstaller "股骨头坏死分析.spec"
```

## 使用说明

1. **上传图片**: 点击按钮选择X光片（JPG/PNG等）

2. **校准px/mm**:
   - 从DICOM校准：如果有DICOM文件，可以自动提取像素间距
   - 手动输入：根据成年人平均股骨头直径44mm计算
     - 公式：px/mm = 图像中股骨头直径(像素) / 44

3. **分析**:
   - 自动分析：程序自动检测股骨头并分析
   - 手动选择：先点击圆心，再点击边缘确定股骨头

4. **参数调整**:
   - 内缩r-：默认6mm，即r-6mm内圆
   - ROI半径：默认1mm，用于计算灰度的小圆半径

5. **保存结果**: 将标注后的图片保存为PNG/JPG

## 图例说明

- 绿色大圆：股骨头轮廓
- 红色十字：股骨头圆心
- 青色圆：r-6mm内圆
- 橙色点：硬化带交点（内圆与硬化带相交处）
- 绿色小圆：硬化带ROI
- 红色小圆：坏死区ROI

## 常见问题

### Q: 打包后运行报错"找不到模块"
A: 确保所有依赖都正确安装，使用 `pip list` 检查

### Q: 打包后的exe太大
A: 这是正常的，因为包含了Python解释器和所有依赖库。可以使用UPX压缩：
```bash
pyinstaller --onefile --windowed --upx-dir=/path/to/upx femoral_gui.py
```

### Q: 自动检测不准确
A: 使用"手动选择"功能，先点击股骨头圆心，再点击边缘

### Q: 如何确定px/mm？
A: 
- 如果有DICOM文件，使用"从DICOM校准"
- 否则，测量图像中股骨头直径（像素），除以44mm
