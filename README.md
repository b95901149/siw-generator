# SIW Generator

Python 專案，用於產生 SIW 相關輸出。

## 環境

- Python 3.11+（建議使用 Anaconda `base` 環境）
- 解譯器路徑：`C:\ProgramData\anaconda3\python.exe`

在 Cursor 中開啟此資料夾後，應自動選用 Anaconda base。若未選中，執行 `Python: Select Interpreter` 並選擇 `base (conda)`。

## 安裝（開發模式）

```powershell
cd D:\python\siw-generator
pip install -e .
```

## 執行

```powershell
python -m siw_generator --name demo
python -m siw_generator --name demo --output output\result.json
```

或使用安裝後的指令：

```powershell
siw-generator --name demo
```

## 專案結構

```
siw-generator/
├── src/siw_generator/
│   ├── cli.py          # 命令列介面
│   ├── generator.py    # 核心產生邏輯
│   └── __main__.py
├── .vscode/settings.json
├── pyproject.toml
└── requirements.txt
```

## 下一步

在 `src/siw_generator/generator.py` 實作你的 SIW 產生規則與輸出格式。
