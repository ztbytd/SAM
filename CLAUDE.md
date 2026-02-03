# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

股骨头坏死灰度分析系统 (Femoral Head Necrosis Grayscale Analysis System) - A medical image analysis desktop application for analyzing femoral head necrosis using image processing techniques.

**Language:** Python 3.7+
**GUI Framework:** tkinter
**Main File:** `femoral_gui.py` (single-file application, ~2100 lines)

## Commands

### Run the application
```bash
python femoral_gui.py
```

### Install dependencies
```bash
pip install -r requirements.txt
```

### Package as Windows executable
```bash
pyinstaller --onefile --windowed femoral_gui.py
# Output: dist/femoral_gui.exe
```

## Architecture

### Core Classes (all in femoral_gui.py)

**ImageData** (lines 33-68)
- Data container for single image state: path, analysis results, thumbnails, calibration

**ImageProject** (lines 71-201)
- Project-level management for multiple images
- Handles batch operations, output directory creation, Excel export

**FemoralHeadAnalyzer** (lines 204-403)
- Core image processing engine
- Key methods:
  - `detect_femoral_head()` - Hough Circle detection for femoral head
  - `find_sclerotic_intersections()` - Identifies sclerotic band peaks
  - `analyze()` - Main analysis pipeline
  - `_calc_roi_gray()` - ROI grayscale calculation

**FemoralHeadApp** (lines 406-2113)
- Main GUI application with all UI and event handling
- State managed through mode flags: `manual_mode`, `intersection_mode`, `ruler_mode`

### User Workflow
```
Load Images → Calibration (DICOM/Ruler/Manual) → Auto/Manual Analysis → Save Results/Export Excel
```

## Key Implementation Patterns

### Chinese Path Support
Uses `np.fromfile + cv2.imdecode` instead of `cv2.imread` to handle Chinese filenames (line 219):
```python
self.image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
```

### PIL Image Caching
Caches PIL conversions to avoid repeated BGR→RGB transformations (lines 1247-1252)

### Coordinate Transformation
Canvas to image coordinates using scale and offset tracking (lines 1466-1481)

### Mode-based State Management
Analysis modes control which events are active; each mode has backup image for restoration

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| Default px/mm | 5.0 | Pixel to millimeter ratio |
| Inner offset | 6mm | Sclerotic band thickness |
| ROI radius | 1mm | Measurement area |
| Max intersections | 2 | Grayscale ratio calculation points |
| Zoom range | 10%-300% | Image zoom limits |

## Dependencies

- **opencv-python** (>=4.5.0): Image processing & Hough detection
- **numpy** (>=1.19.0): Numerical computations
- **pillow** (>=8.0.0): Image display in tkinter
- **openpyxl** (>=3.0.0): Excel report generation
- **pydicom** (>=2.0.0): DICOM medical image calibration
- **tkinter**: Built-in GUI framework

## Adding New Features

### New Analysis Mode
1. Add mode flag in `__init__` (e.g., `self.new_mode = False`)
2. Add backup image variable for mode restoration
3. Create activation method
4. Handle events in `on_canvas_release()`
5. Add result processing method

### UI Modifications
- All UI defined in `setup_ui()` (line 948)
- Dark theme colors configured in ttk style setup (lines 2118-2128)
- Uses pack/grid layout managers
