# SIW Via Generator — 開發指令紀錄

本文件記錄使用者下達、且導致程式或功能變更的指令。

---

## 1. CST VBA 參數化巨集

`2026-06-21 01:00`

### 指令

> 新增 CST VBA 分頁，將 SIW 幾何轉換為 CST 參數化 VBA 巨集

### 實作摘要

- 新增 `cst_export.py`、`gui_cst_vba.py`
- VBA 含基板、銅箔、Via、Port、材料參數
- 後續項目 4 起持續修正與擴充

---

## 2. 基板材料下拉選單

`2026-06-21 01:30`

### 指令

> substrate material 下拉選單，VBA 材料名稱與 CST 完全一致

### 實作摘要

- `materials.py` 五種 CST 材料名稱
- GUI Combobox；VBA 直接使用材料庫名稱

---

## 3. Recipe 儲存與上次工作階段

`2026-06-21 01:45`

### 指令

> 重新開啟程式時欄位與上次關閉相同；recipe 目錄可儲存／讀取；空白檔名用時間戳記_SIW；參考 scribe 說明分頁

### 實作摘要

- `recipe_io.py`、`recipe/` 目錄
- `_last_session.json` 自動還原
- **說明** 分頁：USER_GUIDE + AGENT_HISTORY（含圖片）

---

## 4. CST VBA 巨集穩定化（圓形 Via）

`2026-06-21 02:30`

### 指令

> 修正 CST Run Macro 錯誤（GetParameterValue、via_diameter/2、via_104、Port、RT5880 材料等）；改用迴圈（Loop）重構 VBA 製作 via；獨立的 vias component

### 實作摘要

- `DefineMaterial` 改直接讀 `er_sub` / `tand_sub`
- 新增數值參數 `via_radius`；Cylinder 使用 `.OuterRadius "via_radius"`
- `ClearPreviousSIW` 改 `Component.Delete "siw"` / `"vias"` 整包清除
- `CreateCircularVias` / `AddOneVia` 迴圈建立圓柱，Via 集中於 `vias` 元件
- 修正 Port VBA API（`PortOnBound` 等）

---

## 5. Via 裁切與金屬層厚度參數

`2026-06-21 03:00`

### 指令

> VBA 中輸出 via 個數超出基板尺寸要自動消除跟 DXF 一致；金屬層厚度也要能輸出參數

### 實作摘要

- VBA 參數 `via_col_requested`、`copper_thickness`、`copper_thickness_um`
- 迴圈端部裁切邏輯與 Python / DXF `x_positions` 一致

---

## 6. Port 預設與基板 X 防洩漏

`2026-06-21 03:30`

### 指令

> Port 預設高度涵蓋上下金屬層、寬度為 SIW 寬度；基板 X 防洩漏（距離 ≈ pitch − 孔徑）；防洩漏倍數 0~2、預設 0.5

### 實作摘要

- Port 還原預設按鈕；`compute_port_aperture` 高度含雙面銅厚
- `leakage_margin_factor`（0~2）調整基板長度
- 圓形 Via 分頁 **基板 X 防洩漏** 按鈕

---

## 7. 還原 Slot 獨立與修復啟動

`2026-06-21 04:00`

### 指令

> 還原至 slot 不與 via 同步的狀態；無法執行

### 實作摘要

- 移除 Slot ↔ 圓形 Via 同步按鈕與相關邏輯
- 還原遺失模組（`materials.py`、`recipe_io.py`、`gui_help_panel.py` 等）
- 保留圓形 Via 可調 `via_pitch`

---

## 8. Slot 疊圖預覽

`2026-06-21 04:30`

### 指令

> 實做疊圖功能；疊圖同步顯示 slot 模式的 substrate 外框

### 實作摘要

- 圓形 Via 分頁 **Slot 疊圖** 核取方塊
- `preview.py` 橘色虛線疊加 Slot 基板外框與 Slot 孔
- Slot 參數變更時通知圓形分頁更新疊圖

---

## 9. Slot 分頁 UI 與防洩漏

`2026-06-21 05:00`

### 指令

> 修正孔距欄位不要讓說明文字擋住；slot 基板防洩漏功能要固定 slot 孔數

### 實作摘要

- 說明文字列號改為 `field_start + len(fields)` 自動推算
- `compute_leakage_safe_substrate_length_slot()` 依指定孔數計算基板長度，不縮減欄位數

---

## 10. Terminal 中文 UTF-8

`2026-06-21 05:15`

### 指令

> terminal 顯示中文有亂碼是否能修正

### 實作摘要

- 新增 `console_encoding.py`，程式入口設 UTF-8
- `.vscode/settings.json`：`PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`

---

## 11. Slot CST VBA 建立 Via

`2026-06-21 05:45`

### 指令

> slot 的 VBA 沒有正常創建 slot via；VBA 有創建 via 群組，但是依然沒有成功建立 via 物件

### 實作摘要

- 新增 `CreateSlotVias` / `AddOneSlot`（原 Slot 模式僅 STL 匯入註解）
- 移除無效的 `Component.Activate`；`CreateSlotVias` 改由 Python 展開 `slot_vias` 座標
- `EnsureViasComponent` 建立 `vias` 元件後直接建模

---

## 12. Slot R 角參數化

`2026-06-21 06:15`

### 指令

> slot 的 R 角應該要參照 slot 頁面的輸入值而不是帶入 via diameter；檢查 slot VBA 的 R 角是否按照修正後的邏輯輸出

### 實作摘要

- CST 參數 **`slot_corner_r`**（clamp 至 min(L,W)/2），移除 `slot_radius = W/2`
- `AddOneSlot` 改圓角矩形：3 Brick + 4 圓角 Cylinder（`.OuterRadius "slot_corner_r"`）
- `via_shapes.py` 輪廓依 `corner_r` 繪製；DXF / STL / VBA 一致

---

## 13. 使用說明更新

`2026-06-21 06:30`

### 指令

> 更新說明頁

### 實作摘要

- 更新 `docs/USER_GUIDE.md`：Slot 分頁、Slot 疊圖、`slot_corner_r`、CST VBA 操作、輸出格式對照
- Slot 分頁欄位標籤改為「Slot R 角半徑 (mm)」

---

## 14. CST VBA Parameter Rebuild

`2026-06-21 07:00`

### 指令

> 使用 VBA 建立的變數似乎無法使用 parameter 動態變更幾何

### 實作摘要

- 幾何改以 `AddToHistory` 寫入 CST History（基板、銅箔、via/slot、Port），Main 結尾呼叫 `Rebuild`
- `via_radius` 改為表達式 `via_diameter/2`；Slot 恢復 `slot_pitch` 參數化迴圈
- `ClearPreviousSIW` 新增 `History.Clear`；更新 `USER_GUIDE` 與 `CST_IMPORT.txt` 說明

---

## 15. 說明頁 Parameter Sweep 章節

`2026-06-21 07:30`

### 指令

> 這段適用規則加入說明頁面

### 實作摘要

- `docs/USER_GUIDE.md` 新增「CST Parameter Sweep」：操作步驟、可 Sweep 參數表、限制與實務建議

---

## 16. Slot 連續壁模式（個數 = 2）

`2026-06-21 12:00`

### 指令

> Slot 個數可以是 2（相當於連續壁）；slot=2 時不計算 pitch 相關判定，直接放至指定大小 slot 在中央

### 實作摘要

- Slot 個數下限由 4 改為 **2**（仍須為偶數）；GUI 提示「2 = 連續壁」
- 新增 `_is_continuous_wall()`：`via_count_target == 2` 時跳過 pitch > L 驗證
- `_slot_x_positions()` 連續壁模式固定回傳 `[0.0]`，僅檢查基板 X 是否容納 Slot 長度 L
- `compute_leakage_safe_substrate_length_slot()`：count=2 時邊距改為 factor × W，不使用 pitch
- GUI「對齊基板 X」：count=2 時狀態列顯示連續壁專用訊息
- CST VBA 無需修改（`slot_col_requested = 1` 時本即在 X=0 放上下兩孔）

---

## 17. HFSS 巨集分頁

`2026-06-21 14:00`

### 指令

> 增加新分頁 HFSS，可以將設計實作成 HFSS 的巨集

### 實作摘要

- 新增 `hfss_export.py`：`build_hfss_script_text()` / `export_hfss_script()` 產生 HFSS VBScript
- 新增 `gui_hfss.py`：`HfssScriptPanel`（來源選擇、重新產生、複製全部）
- 主視窗註冊 **HFSS** 分頁；圓形／Slot 參數變更時 debounced 刷新
- CST 套件輸出新增 `siw_hfss.vbs`
- 更新 `USER_GUIDE.md` HFSS 章節

---

## 18. Custom 分頁與模組 JSON

`2026-06-21 16:00`

### 指令

> 新增 Custom 分頁：滑鼠預覽＋左鍵放置圓/方 Via；ctm- 存 module/；RSIW-/SSIW- 從 SIW 匯出至 custom/

### 實作摘要

- `custom_geometry.py` / `custom_io.py` / `custom_preview.py` / `gui_custom.py`
- Custom 分頁：L 可調、W/材料/銅厚同 SIW、預設孔徑 0.15 mm、游標 ghost 預覽
- 模組 JSON：皆存於 `module/`（`ctm-*.json`、`RSIW-*.json`、`SSIW-*.json`）
- 圓形／Slot 分頁新增「匯出至 module/」按鈕（不含 Port）

---

## 19. 組合分頁（Module 平鋪）

`2026-06-21 18:00`

### 指令

> 新增組合分頁：將 module/ 模組平鋪至 M×N 網格；填補、Port、圈選、undo

### 實作摘要

- `compose_geometry.py` / `compose_preview.py` / `compose_io.py` / `gui_compose.py`
- 放置、拖曳、衝突解析、填補基板、Port 幾何
- 組合 Recipe 併入頂部 `recipe_io` session

---

## 20. 組合 UI 與組合存檔

`2026-06-21 22:00`

### 指令

> 組合右欄布局、Panedwindow、上一步／下一步、combination/ 存檔讀檔

### 實作摘要

- 模組預覽高度、Port 列表、組合結果輸出區
- `combination_io.py`、`app_paths.combination_dir()`
- undo/redo 與 `_operation_steps` 同步；session 儲存 sash 比例

---

## 21. 組合 CST VBA 輸出

`2026-06-21 23:00`

### 指令

> CST 分頁支援「當前組合」；輸出 compose_cst_macro.bas

### 實作摘要

- `compose_cst_export.py`；CST 分頁預設來源為當前組合
- 材料 `LoadFromMaterialLibrary` + εr/tanδ fallback（對齊 `cst_export.py`）

---

## 22. 切割基板 CST 上下銅箔合併

`2026-06-21 23:30`

### 指令

> 切割基板時 CST 巨集應合併上下同層銅箔

### 實作摘要

- `substrate_frame` 輸出基板 + 下銅 + 上銅整框 brick
- 框內 module／填補 cell 略過重複 stackup，僅保留 via

---

## 23. 版本 0.9.0beta 發行

`2026-06-21 24:00`

### 指令

> 版本號 0.9.0beta；更新視窗標題、使用說明與開發紀錄；重新編譯至 dist/SIW-Generator_0.9.0beta/；附帶 recipe/module 資料；作為可回滾里程碑

### 實作摘要

- `__version__` / `pyproject.toml` → **0.9.0beta**
- 視窗標題：`SIW Via Generator 0.9.0beta`
- `scripts/build_exe.ps1` 輸出整包至 `dist/SIW-Generator_0.9.0beta/`
- 內含 exe、`docs/`、`recipe/`、`module/`、`combination/`、`CST/`、`VERSION.txt`
- **回滾**：保留此目錄或對應原始碼 tag `v0.9.0beta` 即可還原此里程碑

---

## 24. CST 清除選項、組合 Slot 與 Port 刪除修正

`2026-06-22 01:00`

### 指令

> CST VBA 分頁加入「清除現有 component 與 port」；修正組合 CST Slot 匯出為方孔／圓孔；修正重跑巨集 Port 未清除（含 Port6 殘留）

### 實作摘要

- `gui_cst_vba.py`：新增 **清除現有 component 與 port** 勾選框（預設勾選），匯出／預覽時傳遞 `clear_existing`
- `cst_export.py` / `compose_cst_export.py`：共用 `_vba_clear_project_sub()`，刪除 `siw`、`vias` 與 `component1`～`component64`
- Port 清除改為 CST 官方迭代：`StartPortNumberIteration` → `GetNextPortNumber` → `Port.Delete`（實際 port 編號）；並以 64→1 保底刪除，避免僅剩 Port6 時 `Port.Delete 1` 無效
- `compose_cst_export.py`：組合 Slot Via 改以 **3 Brick + 4 Cylinder** 建立圓角長槽（對齊單一 SIW `AddOneSlot`），支援 module 旋轉／縮放後的世界座標
- 重新編譯 `dist/SIW-Generator_0.9.0beta/`
