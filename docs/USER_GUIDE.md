# SIW Via Generator — 使用說明

**版本 0.9.1beta**（組合 CST 銅箔 Lossy metal、Port/置中與材料庫修正）

本軟體用於設計 **SIW（基板集成波導）Via 圍牆**、預覽幾何、輸出 **CST 套件**（DXF / STL / VBA 巨集）、**HFSS VBScript 巨集**與參數報告。可將 `module/` 模組平鋪組合，並輸出組合級 CST VBA 巨集。

---

## 分頁概覽

| 分頁 | 用途 |
|------|------|
| **圓形 Via** | 圓柱 Via 圍牆、Port 設定、CST 輸出、Slot 疊圖預覽 |
| **圓角矩形 Slot Via** | 圓角矩形 Slot 孔 SIW 設計 |
| **CST VBA** | 預覽／轉換 CST 參數化巨集（圓形、Slot 或 **當前組合**） |
| **HFSS** | 預覽／複製 Ansys HFSS VBScript 巨集（可選圓形或 Slot 來源） |
| **Custom** | 滑鼠點擊放置圓形／方形 Via；儲存／載入 `module/` 模組 |
| **組合** | 將 `module/` 內模組平鋪至 M×N 網格；匯入／匯出模組、Recipe；正方形主預覽 |
| **說明** | 左側導覽：**系統**（操作 log）、**使用說明**、**開發紀錄** |

---

## Recipe 設定檔

程式頂部 **Recipe 檔名** 列可儲存／讀取全部輸入欄位（圓形 Via + Slot Via + **組合** 版面）。

- 檔案目錄：`recipe/`（與專案根目錄或 exe 同層）
- **儲存**：將目前欄位寫入 `recipe/{檔名}.json`
- **讀取**：從 `recipe/` 選擇 JSON 還原欄位
- **檔名空白**：自動使用 `{YYYYMMDD_HHMMSS}_SIW.json`
- **關閉程式**：自動寫入 `recipe/_last_session.json`，下次啟動還原上次狀態

![Recipe 列與分頁](images/step1_recipe_bar.png)

---

## 圓形 Via 分頁

### 主要參數

- **基板材料**：下拉選單與 CST 材料庫名稱一致（如 RT5880）
- **Via 直徑 d、孔距 pitch、SIW 寬度 w**：決定圍牆幾何
- **Via 個數**：可手動指定；超出基板長度者會自動截掉
- **防洩漏倍數**：調整基板 X 方向長度（與孔距、Via 尺寸相關）
- **Port 設定**：Port1（左）、Port2（右）波導開口於 YZ 平面

### Slot 疊圖

勾選 **Slot 疊圖** 可在圓形 Via 的 XY 預覽上，以**橘色虛線**疊加 Slot 分頁的基板外框與 Slot 孔位置（僅供對照，不會同步修改圓形 Via 參數）。

### CST VBA（圓形）

巨集會建立：

- `siw` 元件：介電基板、上下銅箔
- `vias` 元件：圓柱 Via（`CreateCircularVias` 迴圈，`via_radius` 參數）
- Port 1 / Port 2

Via 沿 X 以 `via_pitch` 倍數排列（0、±p、±2p…），超出 `|X| > L/2 − via_radius` 的欄位自動略過。

---

## 圓角矩形 Slot Via 分頁

### 主要參數

| 欄位 | 說明 |
|------|------|
| Slot 寬度 W | 孔在 Y 方向的全寬 |
| Slot 長度 L | 孔在 X 方向的全長 |
| **Slot R 角半徑** | 四角圓角半徑 R；實際使用值為 `min(R, L/2, W/2)` |
| Slot pitch | 沿 X 的欄位間距（**Slot 個數 = 2 時不使用**） |
| Slot 個數 | 上下兩排合計個數（**≥2 的偶數**） |

- **SIW 寬度 w**：上下兩排 Slot 的 Y 向間距
- **防洩漏倍數**：依指定 Slot 個數計算基板長度（不會因防洩漏而減少孔數）
- R = W/2 時，輪廓等同標準 obround（跑道形）
- **Slot 個數 ≥ 4**：需滿足 pitch > L；沿 X 以 pitch 倍數排列（0、±p、±2p…）
- **防洩漏對齊基板 X**（一般模式）：端面至 Slot 邊緣 ≈ 防洩漏倍數 × (pitch − L)

### 連續壁模式（Slot 個數 = 2）

上下各 **1** 個 Slot，皆置於 **X = 0**（基板中央），相當於一道連續金屬壁：

| 項目 | 行為 |
|------|------|
| pitch | **不檢查** pitch 與 L 的大小關係，也不依 pitch 排列 |
| 幾何 | 僅依指定的 **W、L、R** 在中央建立兩個 Slot |
| 防洩漏對齊 | 端面至 Slot 邊緣 = 防洩漏倍數 × **W**（非 pitch−L） |
| CST | `slot_col_requested = 1`；`CreateSlotVias` 在 X=0 放置上下兩孔 |

### CST VBA（Slot）

選 **CST VBA** 分頁 → 來源設計選 **Slot Via** → 按 **參數化 VBA (History+Rebuild)** 或 **參數化 VBA (重跑巨集)** 產生預覽。

巨集會建立：

- `siw` 元件：介電基板、上下銅箔（與圓形模式相同）
- `vias` 元件：圓角矩形 Slot（`CreateSlotVias` / `AddOneSlot`）
  - 每孔由 3 個 Brick（`_main` / `_left` / `_right`）+ 4 個圓角 Cylinder（`_c1`～`_c4`）組成
  - 圓角半徑使用 CST 參數 **`slot_corner_r`**（來自 Slot 分頁輸入，並 clamp 至 min(L,W)/2）
  - Slot 中心 XY：一般模式以 `slot_pitch` 倍數參數化；**連續壁（個數 = 2）** 固定於 X=0

主要 CST 參數：`slot_width`、`slot_length`、**`slot_corner_r`**、`slot_pitch`（連續壁時僅保留參數、不參與排列）、`siw_width`。

修改 L、W、R、pitch 後：若使用 **History+Rebuild** 模式，在 CST Parameter List 調整後按 **Rebuild**；若使用 **重跑巨集** 模式，需再次 **Run Macro**。**變更 Slot 個數**（`slot_col_requested`）兩種模式皆需重新 Run Macro 或重新匯出。

---

## CST VBA 分頁操作

1. **來源設計**：選「圓形 Via」、「Slot Via」或 **當前組合**
2. **清除現有 component 與 port**（預設勾選）：Run Macro 前先執行 `ClearPreviousSIW` / `ClearPreviousCompose`，刪除既有 `siw`、`vias` 元件與所有 Waveguide Port；取消勾選則保留專案內既有幾何（適合手動合併或增量修改）
3. **參數化 VBA (History+Rebuild)**：寫入 CST History + StoreParameter，修改 Parameter List 後按 **Rebuild**（支援 Parameter Sweep）
4. **參數化 VBA (重跑巨集)**：同樣 StoreParameter + 參數表達式，但直接 `.Create`（舊版相容）；修改 Parameter List 後需 **重新 Run Macro**
5. **複製全部**：貼至 CST Macro Editor
6. 切換至此分頁時會自動產生 **History+Rebuild** 預覽

### 兩種模式對照

| 項目 | History+Rebuild | 重跑巨集 |
|------|-----------------|----------|
| GUI 按鈕 | 參數化 VBA (History+Rebuild) | 參數化 VBA (重跑巨集) |
| 匯出檔名 | `siw_cst_macro.bas` | `siw_cst_macro_direct.bas` |
| 幾何 API | `AddToHistory` + 結尾 `Rebuild` | 直接 `With Brick/Cylinder .Create` |
| 改參數後 | **Rebuild** | **重新 Run Macro** |
| Parameter Sweep | 適合 | 不適合 |
| 穩定性 | 較新；需 CST 支援 History | 與舊版相同，一般較穩 |

兩種模式皆為**參數化**（非固定數值）：尺寸以 `substrate_length/2`、`via_pitch` 等 CST 參數表示，並以 `StoreParameter` 寫入 Parameter List。

### 在 CST 中的操作

**History+Rebuild**

1. **Macro → Run Macro**（建立參數、材料、History，並 Rebuild）
2. 在 **Parameter List** 修改尺寸
3. 按 **Rebuild** 更新幾何（不必重跑巨集，除非改孔數）

**重跑巨集**

1. **Macro → Run Macro**（建立參數、材料與幾何）
2. 在 **Parameter List** 修改尺寸
3. 再次 **Run Macro**（若已勾選清除選項，會先 `ClearPreviousSIW` / `ClearPreviousCompose` 再重建）

**清除既有 Port / 元件**

- 巨集開頭會呼叫 `ClearPreviousSIW`（單一 SIW）或 `ClearPreviousCompose`（組合）
- Port 刪除使用 CST 官方 API：`StartPortNumberIteration` + `GetNextPortNumber` 取得**實際 port 編號**後刪除（非僅刪 Port1）
- 若重跑巨集後 Port 累加，請確認已重新匯出最新 `.bas`，且 CST VBA 分頁 **「清除現有 component 與 port」** 有勾選

### 材料建立（巨集自動處理）

| 材料 | 名稱 | 建立方式 |
|------|------|----------|
| 介電基板 | 與 GUI 下拉一致（如 `Rogers RT-duroid 5880 (lossy)`） | 先嘗試 Material Library；再以 `DefineMaterial` 以 `er_sub` / `tand_sub` 建立；**History 模式**另將基板材料寫入 History，Rebuild 時可更新 εr |
| 銅箔 / Via | `Copper (annealed)` | `DefineCopperMaterial`（Normal 型 + `Kappa=5.8e7` S/m），**不需** Material Library |

> 若 CST 未安裝 Rogers 等材料庫，基板仍可由 `DefineMaterial` 建立；銅箔不依賴材料庫。

### 輸出 CST 套件時的 VBA 檔

- `siw_cst_macro.bas` — History+Rebuild
- `siw_cst_macro_direct.bas` — 重跑巨集

---

## CST Parameter Sweep

僅 **History+Rebuild** 模式適合 Parameter Sweep。巨集將幾何寫入 CST **History** 並以 **StoreParameter** 建立設計參數（本軟體本身不提供 Sweep 批次匯出）。

### 操作步驟

1. 在 CST 執行 **Macro → Run Macro**（建立參數與 History）
2. 設定求解器（Frequency Domain、Transient 等）
3. 開啟 **Parameter Sweep**（*Home → Parameters* 或求解器設定）
4. 選取要掃描的參數，設定起點、終點、步數
5. 執行 Sweep；CST 會依序改參數 → **Rebuild** → 求解

若幾何未隨 Sweep 更新，請確認已使用含 History 的新版巨集，且 Sweep 目標為 Parameter List 中的變數（非 VBA 區域變數）。

### 適合 Sweep 的參數

| 參數 | Sweep 效果 |
|------|------------|
| `substrate_length` / `substrate_width` | 基板、銅箔尺寸更新 |
| `via_pitch` / `via_diameter` | 孔距、孔徑更新（`via_radius = via_diameter/2`） |
| `siw_width` | Via 牆間距更新 |
| `slot_width` / `slot_length` / `slot_corner_r` / `slot_pitch` | Slot 幾何更新 |
| `port1_x` / `port2_x` / `port_width` / `port_height` | Port 位置與開口更新 |
| `substrate_height` / `copper_thickness` | 堆疊厚度更新 |
| `er_sub` / `tand_sub` | 介電常數 / 損耗角正切更新（History 模式） |

### 限制與注意事項

1. **孔數 / Slot 數**（`via_col_requested`、`slot_col_requested`）  
   History 項目數在 Run Macro 時即固定。可 Sweep 孔距與尺寸；**Sweep 個數**不會自動增減孔，改個數需重新 Run Macro 或重新匯出。

2. **基板變長後多出可放的孔**  
   Sweep `substrate_length` 變大時，**不會**自動新增 History 中未建立的 via 欄位；只會移動既有孔的位置。

3. **材料參數**（`er_sub`、`tand_sub`）  
   History+Rebuild 模式已將基板材料寫入 History（`.Epsilon "er_sub"`、`.TanD "tand_sub"`），Sweep 這兩個值時幾何 Rebuild 後應一併更新介電常數。若未更新，請確認使用 `siw_cst_macro.bas` 而非 direct 版。

4. **幾何拓撲跳變**  
   例如 `slot_corner_r` 大到使 Slot 變成圓柱時，幾何分支會改變；建議分段 Sweep 或分開模擬。

### 實務建議

- **單參數或雙參數掃描**（如 `via_pitch`、`siw_width`）：可直接使用目前流程。
- **掃描孔數或大幅改變 layout**：在 Generator 產生不同設計後各自 Run Macro，或使用不同 CST 專案。
- **掃描 εr / tan δ**：使用 History+Rebuild 巨集並 Sweep `er_sub` / `tand_sub`；或以重跑巨集模式每次改參數後 Run Macro。

---

## CST 巨集常見錯誤

| 訊息 | 可能原因 | 建議 |
|------|----------|------|
| `Unterminated block statement. 'If'` | VBA 語法錯誤（舊版巨集） | 重新從 GUI 產生並複製最新 VBA |
| `The specified material does not exist` | 材料尚未建立或 History 順序錯誤 | 使用最新巨集（含 `DefineMaterial`）；或改試 **重跑巨集** 模式 |
| `The specified component does not exist`（`.Conductivity` / `.SetProperty`） | 舊版在 History 中建立 Lossy metal 失敗 | 已改為 `DefineCopperMaterial`（Normal + Kappa）；請更新巨集 |
| Rebuild 後幾何不變 | 使用了 direct 巨集，或參數未綁定 History | 確認使用 `siw_cst_macro.bas`；參數須在 Parameter List 中 |
| 重複 Run Macro 後 Port 累加 | 舊版巨集僅 `Port.Delete 1`，或清除選項未勾選 | 重新匯出 `.bas`；勾選 **清除現有 component 與 port**；新巨集以 `GetNextPortNumber` 刪除全部 Port |
| 重複 Run Macro 後 History 累加 | History 模式特性 | 建議在空白專案首次執行；改孔數時可新建專案或清除 History |
| 組合 Slot 顯示為圓孔或方孔 | 使用了舊版 `compose_cst_macro.bas` | 重新輸出；`.bas` 中應含 `via_1_main` 等，而非單一 `Cylinder OuterRadius "0.075"` |

若 History+Rebuild 仍無法順利執行，可改用 **參數化 VBA (重跑巨集)**：同樣可在 Parameter List 改參數，但每次需重新 Run Macro。

---

## HFSS 分頁操作

1. **來源設計**：選「圓形 Via」或「Slot Via」（與 CST 分頁相同，獨立選擇）
2. 切換至 **HFSS** 分頁時會自動產生 VBScript 預覽
3. 按 **重新產生** 刷新；**複製全部** 貼至 HFSS Scripting 編輯器
4. 在 Ansys Electronics Desktop：**Tools → Run Script**（或儲存為 `.vbs` 後執行）

### 使用前準備

- 先**開啟或建立** HFSS 專案（腳本使用 `GetActiveProject()`）
- 腳本會刪除並重建名為 **`SIW_Design`** 的 HFSS 設計（Driven Modal）

### 巨集內容

| 項目 | 說明 |
|------|------|
| 設計變數 | `substrate_length`、`siw_width`、`via_pitch` / `slot_*` 等（單位 mm） |
| 材料 | 自訂 `siw_substrate`（εr=`er_sub`、tanδ=`tand_sub`）；銅為內建 `copper` |
| 幾何 | 基板 + 上下銅箔 + 圓柱 Via 或圓角矩形 Slot（參數化迴圈，邏輯對齊 CST） |
| Port | YZ 平面 Wave Port（`AssignWavePort`，矩形 sheet） |
| 求解 | 建立 `Setup1`（頻率 = `center_freq_ghz`） |

修改 HFSS 設計變數後需**重新 Run Script** 重建幾何（與 CST 重跑巨集模式類似）。

輸出 CST 套件時亦會一併產生 **`siw_hfss.vbs`**。

---

## Custom 分頁與模組

### Custom 分頁（手動放置）

- **基板**：L 可調；W、厚度、銅厚、材料與 SIW 分頁相同
- **孔型**：圓形（預設直徑 0.15 mm）或方形（W×H）
- **放置**：勾選「點擊放置」→ 游標處顯示預覽孔 → **左鍵**放置
- **孔位列表**：**單擊**儲存格可編輯 type / X / Y / L/W / H；**拖曳**列可調序
- **新增孔**：下方 type / X / Y / L/W / H 列 + **加入**（圓孔 L/W=直徑，方孔 W/H 獨立）
- **載入 RSIW-/SSIW-**：自 `module/` 載入後可編輯各孔 **X/Y**（Slot 另可改 L/W、H=長度）；SIW 側壁線仍依模組參數顯示
- **儲存**：`module/ctm-{標題}.json`（同名詢問覆蓋）
- **載入**：從 `module/` 選取 JSON（ctm- / RSIW- / SSIW-）

### 從 SIW 匯出模組

| 分頁 | 按鈕 | 路徑 | 前綴 |
|------|------|------|------|
| 圓形 Via | 匯出至 module/ (RSIW-) | `module/` | `RSIW-` |
| Slot Via | 匯出至 module/ (SSIW-) | `module/` | `SSIW-` |

匯出內容：基板尺寸、材料、SIW 參數、所有 Via/Slot 座標（**不含 Port**）。檔名使用輸出設定的「名稱」欄；同名詢問覆蓋。

---

## 組合分頁

1. **版面**：左側組合主預覽；右側 M/N 工具列、模組 I/O、**module 列表與縮圖**（Panedwindow 可拖曳調整寬度，比例會寫入 session）
2. **組合存檔**（右下「組合結果輸出存取」）：
   - **組合名稱**：存於 `combination/{名稱}.json`（含 layout、嵌入 modules、操作步驟、undo/redo 快照）
   - **讀取組合**：自 `combination/` 選檔；缺少的 module 會還原至 `module/`
   - 同名存檔需確認覆蓋
3. **Recipe / 模組**：
   - 頂部 **Recipe** 仍儲存／讀取全域欄位（含組合版面狀態）
   - **匯入模組**：載入 `module/` 內 JSON，右側 L/W/h/Cu 可 **重新參數化**
   - **匯出模組**：依目前參數另存至 `module/`
4. **預覽工具列**：滾輪縮放、框選縮放／平移；「重設視野」「重設全局 FOV」；**上一步 Ctrl+Z**、**下一步 Ctrl+Y**
5. **置入**：左鍵放置 module；尺寸衝突時左鍵選參照 cell、右鍵以新 module 為準
6. **點選／刪除**：左鍵選取／刪除；拖曳移動
7. **填補基板**：圈選空白 cell 填補介電＋上下銅箔
8. **切割基板**：圈選設定紅框外框（綠色填補預覽）；CST 輸出時以 **整框合併** 基板與上下銅箔，框內 module 僅保留 via
9. **防洩漏外框**：依 X 或 Y 軸自動推算外框
10. **Port**：移近 cell 邊緣，以兩顆 via 中心連線為 Port 寬度；左鍵新增
11. **清空** 會一併重設主預覽視野

### 組合 CST 輸出

1. **組合分頁**右下「組合結果輸出存取」→ **輸出 CST 套件**（或 **CST VBA** 分頁、來源選 **當前組合**）
2. 輸出至 `CST/{時間}_{組合名稱}/`，套件結構與單一 SIW 相同：

| 檔案 | 說明 |
|------|------|
| `compose_cst_macro.bas` | VBA 巨集（基板、via、Port） |
| `compose_cst.dxf` | 2D 圖層（基板 / 銅箔 / via / Port） |
| `compose_cst.stl` | 3D 實體 |
| `compose_params.txt` | 組合參數紀錄 |
| `CST_IMPORT.txt` | 匯入說明 |

3. 可勾選 **清除現有 component 與 port**（預設勾選）
4. **組合名稱** 留空時預設 `Compose`

**組合 Slot Via**

- 模組 JSON 中 `type: "slot"` 的孔，CST 以 **3 Brick + 4 圓角 Cylinder** 建立圓角長槽
- DXF / STL 亦以圓角輪廓輸出

---

## 說明分頁 — 系統 Log

左側導覽採半導體設備軟體風格（大字、選取套色）。**系統** 頁顯示本週操作紀錄：

- 模組儲存／載入／匯入／匯出
- 組合放置、刪除、Port、清空、Recipe 讀寫
- 頂部 Recipe 儲存／讀取

Log 目錄：`log/`，檔名 `siw_generator_YYYY-Www.log`，依 **ISO 週** 自動分割。切換至說明分頁或按 **重新整理** 可更新顯示。

---

## 範例：圓形 Via → CST 套件

### Step 1 — 設定 SIW 參數

1. 開啟 **圓形 Via** 分頁
2. 選擇 **基板材料**
3. 輸入頻率、Via 直徑、基板尺寸、銅厚等
4. 右側 **XY / YZ 預覽** 即時更新

![圓形 Via 預覽](images/step2_circular_preview.png)

### Step 2 — 轉換 CST VBA

1. 切換至 **CST VBA** 分頁
2. 選 **參數化 VBA (History+Rebuild)** 或 **參數化 VBA (重跑巨集)**，再按 **複製全部**
3. 在 CST：**Macro → Run Macro**（貼上或選取 `.bas` 檔）

> 需要 Parameter Sweep 時請用 History+Rebuild；若 CST 報 History 相關錯誤，可改試重跑巨集模式。

### Step 3 — 輸出 CST 套件

1. 在 **輸出設定** 填寫名稱（可空白，預設 SIW）
2. 按 **輸出 CST 套件**
3. 輸出至 `CST/{時間戳記}_{名稱}/`

套件內容：

| 檔案 | 說明 |
|------|------|
| `siw_cst_macro.bas` | History+Rebuild 參數化巨集 |
| `siw_cst_macro_direct.bas` | 重跑巨集參數化巨集 |
| `siw_cst.dxf` | 2D 圖層（CST 匯入） |
| `siw_cst.stl` | 3D 模型 |
| `siw_cst.step` | STEP（可選，需 cadquery） |
| `CST_IMPORT.txt` | CST 匯入與材料說明 |
| `siw_params.txt` | 參數報告 |
| `siw_hfss.vbs` | HFSS VBScript 巨集 |

---

## 輸出格式對照

| 格式 | 圓形 Via | Slot Via |
|------|----------|----------|
| VBA (History) | 迴圈圓柱 History + `via_radius=via_diameter/2` | 迴圈圓角矩形 History + `slot_corner_r` |
| VBA (direct) | 迴圈圓柱 `.Create` + 同上參數 | 迴圈圓角矩形 `.Create` + 同上參數 |
| 組合 VBA | — | `compose_cst_macro.bas`：直接 `.Create`；Slot 為 Brick + Cylinder 圓角長槽 |
| DXF | 圓孔圖層 | 圓角矩形輪廓（含 R 角） |
| STL | 圓柱擠出 | 圓角矩形擠出（含 R 角） |
| HFSS `.vbs` | 參數化圓柱 Via + Wave Port | 參數化 Slot + Wave Port |

---

## 啟動方式

### 發行版（0.9.1beta）

解壓或直接使用 `dist/SIW-Generator_0.9.1beta/`，執行 **`SIW-Generator.exe`**。同目錄已附：

| 目錄 | 說明 |
|------|------|
| `recipe/` | Recipe 與上次 session |
| `module/` | 模組 JSON |
| `combination/` | 組合存檔（可選，自行建立） |
| `CST/` | CST 套件輸出 |
| `log/` | 操作紀錄 |
| `docs/` | 使用說明與開發紀錄 |

### 開發環境

```powershell
cd D:\python\siw-generator
.\.venv-build\Scripts\python.exe -m siw_generator --gui
```

編譯發行包：

```powershell
.\scripts\build_exe.ps1
```

輸出：`dist/SIW-Generator_0.9.1beta/`

---

## 快捷操作

| 操作 | 說明 |
|------|------|
| 滾輪 | 預覽圖縮放 |
| 工具列 | 平移／重設視野 |
| Ctrl+滾輪 | 說明分頁文字縮放 |
| 還原建議值 | 依頻率重算 SIW 寬度、孔距、Via／Slot 個數 |
| Slot 疊圖 | 圓形 Via 分頁：疊加 Slot 幾何預覽 |
