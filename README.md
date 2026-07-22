# Video Code Duplicate Finder

Windows 11 的 Python／PySide6 影音番號重複整理工具。掃描資料夾後，依影片檔名辨識番號並顯示重複項目；刪除功能預設關閉，啟用後仍會先顯示內容預覽與兩階段確認，且預設將直接父資料夾送至 Windows 資源回收筒。

## 目前功能

- 背景掃描與停止控制，掃描期間自動停用刪除操作。
- 「重複番號結果」與「影片瀏覽結果」分頁，顯示資料夾影片數、檔案數與總大小。
- 影片瀏覽結果可快速切換詳細表格與縮圖預覽；縮圖以 FFmpeg 非同步產生並快取，雙擊會交給 Windows 預設播放器播放。
- FFmpeg 與主程式分開發布；可在設定頁指定同時包含 `ffmpeg.exe`、`ffprobe.exe` 的資料夾，未指定時才自動偵測。
- 依解析度、長度、大小、位元率、修改時間排序的「建議保留」標示。
- 同步勾選、批次去重、父子目標合併，以及快速選取非建議版本。
- 樹狀刪除預覽、混合番號警告、兩階段確認與永久刪除額外確認。
- 批次結果摘要、逐項錯誤資訊，以及 UTF-8 JSON Lines 刪除日誌。
- 設定頁可開關刪除功能；資源回收筒模式為安全預設值。

## 安裝與執行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## 刪除安全性

- 只能刪除掃描根目錄之下的影片直接父資料夾；掃描根目錄、磁碟根目錄、使用者家目錄與 Windows 目錄一律拒絕。
- 以 `Path.resolve()` 與 `relative_to()` 驗證父子關係，不使用字串前綴比對。
- 掃描、預覽與大小計算不跟隨 symbolic link／junction；資料夾本身若是連結也不可刪除。
- 同資料夾只會列為一個實際目標；同時選到父子資料夾時只保留最上層。
- 正式刪除預設使用 `Send2Trash`；永久刪除設定預設關閉，且目前 UI 不提供啟用入口。

## 測試

```powershell
pytest -q
```

所有刪除測試均使用 pytest 暫存資料夾，不會操作真實影音資料。

## 授權

主程式採用 [MIT License](LICENSE)。FFmpeg／ffprobe 是另外取得與設定的第三方工具，不屬於本專案 MIT 授權範圍；若隨應用程式重新散布，請依實際 FFmpeg build 遵守 LGPL、GPL 或相關元件的授權條款，詳見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
