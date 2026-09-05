# Video Finder — 影片重複偵測

掃描指定資料夾(含子資料夾)內的影片檔,依「檔案名稱」判斷是否重複,並用 FFmpeg 抓一幀截圖幫助判斷。

## 功能
- 掃描常見影片格式:MKV / MP4 / WMV / AVI 等,可在「設定」中新增/移除
- 依檔名正規化分組;`CD1 / CD2 / DISC 1 / 碟1 / 第1碟 / PART 2` 會合併為同一部影片(不重複顯示)
- 可選項:比對時忽略畫質/編碼字樣(1080p、x264、BluRay、年份…);預設只顯示重複
- 用 FFmpeg 抓一幀截圖(時間點、寬度可在設定調整),縮圖快取於程式目錄 `.thumbnails`
- 雙擊或「▶ 播放」→ 用系統預設播放器開啟影片
- 右選單或「📂 資料夾」→ 開啟影片所在資料夾(並選取該檔案)
- 現代化 Qt(PySide6)介面

## 執行(開發)
```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

## FFmpeg
- 程式會依序尋找:「設定」指定的路徑 → 程式目錄 `ffmpeg.exe` → 資料夾 `ffmpeg\ffmpeg.exe` → 系統 PATH
- 建議將 `ffmpeg.exe` / `ffprobe.exe` 與本程式放同一資料夾

## 打包成 EXE(PyInstaller)
```powershell
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name VideoFinder `
    --add-data "ffmpeg.exe;." --add-data "ffprobe.exe;." main.py
```
- 產出於 `dist\VideoFinder.exe`
- `--add-data` 的分隔符在 Windows 用 `;`;打包後 `ffmpeg.exe` 會與 exe 同一層,程式可直接找到
- 若使用 `--onefile`,建議把 `ffmpeg.exe` 與 `VideoFinder.exe` 一起放進同一資料夾(此專案目前的 `--add-data` 已內嵌)

## 資料
- 設定檔:`settings.json`(位於程式目錄)
- 縮圖快取:`.thumbnails\`
