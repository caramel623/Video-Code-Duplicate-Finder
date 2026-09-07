# Video Finder — 影片重複偵測

掃描指定資料夾(含子資料夾)內的影片檔,依「檔案名稱」判斷是否重複,並用 FFmpeg 抓一幀截圖幫助判斷;另可依影片編碼掃描,並用 HandBrake 將非 AV1 / HEVC 的影片轉碼後替換原檔。

## 功能

### 重複偵測
- 掃描常見影片格式:MKV / MP4 / WMV / AVI 等,可在「設定」中新增/移除
- 依檔名正規化分組;`CD1 / CD2 / DISC 1 / 碟1 / 第1碟 / PART 2` 會合併為同一部影片(不重複顯示)
- 可選項:比對時忽略畫質/編碼字樣(1080p、x264、BluRay、年份…);預設只顯示重複
- 用 FFmpeg 抓一幀截圖(時間點、寬度可在設定調整),縮圖快取於程式目錄 `.thumbnails`
- 「掃描編碼」選項:在重複清單中一併顯示各檔案的影片/音訊編碼
- 雙擊或「▶ 播放」→ 用系統預設播放器開啟影片
- 右選單或「📂 資料夾」→ 開啟影片所在資料夾(並選取該檔案)

### 編碼掃描
- 掃描資料夾內影片的編碼(FFprobe 偵測),可搜尋、可只看「非 AV1 / HEVC 的影片」
- 「轉碼選取並替換」:用 HandBrake 將選取的影片轉碼為 AV1 或 HEVC,完成後**替換原檔案**
  - 編碼器:AV1 10-bit / AV1 8-bit (SVT-AV1)、HEVC 10-bit / HEVC 8-bit (x265)
  - 品質:CRF 手動輸入
  - 輸出容器:**MP4(預設)** 或 MKV;容器與原副檔名不同時,輸出會連同副檔名一起改名(如 `clip.mkv` → `clip.mp4`)
  - 音訊:AAC/AC3/TrueHD/DTS/Opus/FLAC 等直接「複製」不重壓,其餘轉 AAC 128k
  - SVT-AV1 預設 `--encoder-preset 8 --encoder-tune vq`(較快、畫質更好);x265 預設 `--encoder-preset slower`
  - 右鍵選單可對單一檔案「轉碼此項並替換」

### 轉碼結果
- 獨立分頁顯示「最近一筆」轉碼批次:檔案、輸出路徑、原檔備份、大小、成功/失敗
- **▶ 播放選取** / 雙擊 → 用系統預設撥放器開啟輸出檔,確認轉碼品質
- 「開啟原檔備份資料夾」→ 直接開啟程式目錄的 `hb_originals`(原檔所在地)
- 本次沒有轉碼時,自動顯示上一次的批次結果
- 每次轉碼批次會記錄在程式目錄的 `transcode_log.json`(最多留最近 20 筆)

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

## HandBrake
- 轉碼需要 [HandBrake](https://handbrake.fr/) 1.6 或更新的 CLI(`HandBrakeCLI.exe` / `hb`)
- 程式會依序尋找:「設定」指定的路徑 → 程式目錄 → 常見安裝位置(`Program Files\HandBrake`、WinGet 連結) → 系統 PATH
- 建議將 `HandBrakeCLI.exe` 與本程式放同一資料夾
- 轉碼中的進度(百分比、階段)會即時顯示在「編碼掃描」分頁

## 打包成 EXE(PyInstaller)
```powershell
.venv\Scripts\pyinstaller --noconfirm VideoFinder.spec
```
- 產出於 `dist\VideoFinder.exe`(onefile,已內嵌 `ffmpeg.exe` / `ffprobe.exe` 與授權檔)

## 資料(皆位於程式目錄)
- 設定檔:`settings.json`
- 縮圖快取:`.thumbnails\`
- 轉碼原檔備份:`hb_originals\`(轉碼成功後原檔會移動至此,由您決定是否刪除;同名自動加副序號,不覆蓋)
- 轉碼記錄:`transcode_log.json`(「轉碼結果」分頁讀取此檔)

## 授權
- 本專案:GPL-3.0(見 `LICENSE`)
- 內嵌 FFmpeg 為 GPL 構建,見 `licenses/ffmpeg-GPL.txt`;完整第三方聲明見 `THIRD_PARTY_NOTICES.md`
