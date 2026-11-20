# Kindle Dashboard: biến Kindle thành màn hình Lịch + Việc cần làm

Bộ này biến chiếc Kindle đang để không thành một màn hình để bàn, hiện:
- **lịch Google** hôm nay và ngày mai,
- **việc cần làm** (Google Tasks),
- **thời tiết + chất lượng không khí**,
- (tuỳ chọn) **mức dùng Claude**.

Màn hình tự làm mới khoảng 15 phút/lần. E-ink nên để cả ngày không chói mắt, pin dùng được nhiều ngày. **Chi phí: 0 đồng**, mọi thứ chạy trên dịch vụ miễn phí của Google và GitHub.

```
Google Calendar + Tasks ──► Apps Script (của bạn) ──► GitHub Actions vẽ ảnh ──► GitHub Pages ──► Kindle tải ảnh về hiển thị
```

---

## Cần chuẩn bị

- **Kindle jailbreak được** (xem Phần 0).
- **Tài khoản Google** có lịch và việc cần làm muốn hiện lên.
- **Tài khoản GitHub** (miễn phí, đăng ký ở github.com).
- **Máy tính + cáp USB** để chép file vào Kindle.
- Khoảng **45–60 phút**, phần lâu nhất là jailbreak.

Trong bộ này có:

| File / thư mục | Dùng để |
|---|---|
| `apps_script.gs` | Code lấy lịch + việc cần làm (dán vào Apps Script, Phần 1) |
| `setup_github.sh` | Script tự tạo repo GitHub và cài mọi thứ (Phần 2) |
| `render.py`, `lunar.py`, `.github/` | Code vẽ ảnh dashboard, chạy trên GitHub |
| `kindle/` | File chép vào Kindle (Phần 3) |
| `mac/` | Chỉ dùng cho phần mức dùng Claude (Phần 5) |

---

## Phần 0: Jailbreak Kindle

Cách jailbreak phụ thuộc đời máy và phiên bản firmware, nên hãy làm theo hướng dẫn chính thức của cộng đồng:

1. Xem firmware: **Settings → Device Options → Device Info** (hoặc *Cài đặt → Tùy chọn thiết bị → Thông tin thiết bị*).
2. Vào **https://kindlemodding.org**, mục Jailbreaking, chọn cách phù hợp với firmware của bạn và làm đúng từng bước.
3. Jailbreak xong là được, **không cần cài KUAL**. Dashboard chạy bằng "scriptlet": một file `.sh` trong thư mục `documents`, hiện ra như một cuốn sách trong Thư viện.

> Jailbreak là tự chịu rủi ro. Đọc kỹ hướng dẫn, và tắt cập nhật firmware tự động theo hướng dẫn trên kindlemodding.org.

---

## Phần 1: Lấy dữ liệu Google bằng Apps Script (~10 phút)

1. Mở **https://script.google.com** (đúng tài khoản Google có lịch) → **New project**, đặt tên `Kindle Dashboard`.
2. Mở file **`apps_script.gs`** trong bộ này bằng Notepad/TextEdit, copy toàn bộ. Xoá code mẫu trong Apps Script rồi dán vào.
3. Tìm dòng:
   ```js
   const TOKEN = 'DOI-THANH-CHUOI-BI-MAT';
   ```
   Đổi phần trong nháy thành **một chuỗi bí mật của bạn** (chữ và số, 10–20 ký tự). Bấm **Save**.
4. Cột trái, mục **Services** → **+** → chọn **Google Tasks API** → **Add**.
5. Trên thanh công cụ chọn hàm **`testCollect`** → **Run** → cho phép quyền.
   Google sẽ báo *"Google hasn't verified this app"*: bấm **Advanced → Go to Kindle Dashboard (unsafe) → Allow**. Đây là script của chính bạn nên không sao.
   Phần *Execution log* hiện danh sách lịch/việc là đúng.
6. **Deploy → New deployment** → bánh răng → **Web app**:
   - *Execute as*: **Me**
   - *Who has access*: **Anyone**
   → **Deploy** → copy **Web app URL** (dạng `https://script.google.com/macros/s/AKfy…/exec`).
7. Ghép thành **DATA_URL**:
   ```
   <Web app URL>?token=<chuỗi bí mật ở bước 3>
   ```
   Dán thử vào trình duyệt, thấy chữ dạng JSON có tên sự kiện/việc là đúng.
   **Không gửi link này cho ai**: ai có link là đọc được lịch của bạn.

> Sau này nếu sửa code Apps Script: **Deploy → Manage deployments → ✏️ → Version: New version → Deploy** (link giữ nguyên).

---

## Phần 2: Tạo repo GitHub và cài đặt (~5 phút)

### Cách A (khuyên dùng): chạy 1 lệnh

Script `setup_github.sh` tự làm hết: tạo repo, lưu DATA_URL vào mục bí mật, bật GitHub Pages, chạy lần đầu, và điền sẵn link ảnh vào file cấu hình của Kindle.

**Bước 1: cài công cụ** (chỉ làm 1 lần)
- **macOS**: mở Terminal, chạy
  ```bash
  brew install gh git
  ```
  (chưa có Homebrew thì cài ở https://brew.sh trước)
- **Windows**: cài **Git for Windows** (https://git-scm.com/download/win) và **GitHub CLI** (https://cli.github.com). Sau đó dùng chương trình **Git Bash** (có sẵn khi cài Git) để chạy các lệnh bên dưới.

**Bước 2: chạy script**
```bash
cd đường-dẫn-tới/thư-mục-đã-giải-nén
bash setup_github.sh
```
Script sẽ lần lượt:
1. Mở trình duyệt cho bạn **đăng nhập GitHub** (copy mã 8 ký tự nó hiện ra, dán vào trang GitHub).
2. Hỏi **tên repo** (Enter để dùng `kindle-dashboard`).
3. Hỏi **toạ độ thành phố** cho thời tiết: mở Google Maps, chuột phải vào thành phố, dòng đầu là `vĩ độ, kinh độ` (TP.HCM: `10.7769`, `106.7009`; Hà Nội: Enter để dùng mặc định).
4. Hỏi **DATA_URL** (ở Phần 1, bước 7). Khi dán, chữ sẽ không hiện ra, cứ dán rồi Enter.
5. Tự làm phần còn lại trong khoảng 1–2 phút, cuối cùng in ra **link repo** và **link ảnh**.

Mở link ảnh trên trình duyệt, thấy ảnh dashboard là thành công. Sang Phần 3.

### Cách B: làm tay trên web (nếu không chạy được script)

1. **Tạo repo**: vào https://github.com/new → tên `kindle-dashboard` → **Public** → **Create repository**.
2. **Upload code**: trong repo mới bấm **uploading an existing file** → kéo toàn bộ nội dung thư mục này vào (kể cả thư mục `.github`) → **Commit changes**.
   Nếu không kéo được thư mục `.github` (hay gặp trên Windows): bấm **Add file → Create new file**, gõ tên `.github/workflows/update.yml`, dán nội dung file đó → **Commit**.
3. **Đặt toạ độ thời tiết**: mở `.github/workflows/update.yml` → ✏️ → sửa 2 dòng `DASH_LAT` và `DASH_LON` thành toạ độ thành phố của bạn → **Commit**.
4. **Lưu thông tin bí mật**: **Settings → Secrets and variables → Actions → New repository secret**, tạo 2 cái:
   - `DATA_URL` = link ở Phần 1, bước 7
   - `SECRET_PATH` = một chuỗi ngẫu nhiên bất kỳ (chữ thường và số, khoảng 12 ký tự), dùng để giấu đường dẫn ảnh
5. **Bật Pages**: **Settings → Pages** → *Source*: **GitHub Actions**.
6. **Chạy lần đầu**: tab **Actions** → **Cập nhật dashboard Kindle** → **Run workflow** → nút xanh **Run workflow**. Chờ dấu ✅ (khoảng 1 phút).
7. Link ảnh của bạn là:
   ```
   https://<tên-github-của-bạn>.github.io/kindle-dashboard/<SECRET_PATH>/dashboard.png
   ```

Từ giờ GitHub tự vẽ lại ảnh khoảng 15 phút/lần từ 8h–24h, và 4 tiếng/lần ban đêm. GitHub đôi khi chạy trễ 10–30 phút, chuyện bình thường.

---

## Phần 3: Cài lên Kindle (~10 phút)

1. Mở file **`kindle/dashboard/config.sh`**:
   - Nếu dùng **Cách A**, dòng `IMAGE_URL=` đã được điền sẵn link ảnh của bạn.
   - Nếu dùng **Cách B**, sửa dòng `IMAGE_URL="..."` thành link ảnh ở Phần 2.

   Các tuỳ chọn khác trong file (có chú thích sẵn):
   - `INTERVAL_MIN=15`: ban ngày bao nhiêu phút làm mới 1 lần.
   - `NIGHT_START=0`, `NIGHT_END=8`, `NIGHT_INTERVAL_MIN=240`: từ 0h–8h làm mới 4 tiếng/lần cho đỡ tốn pin.
   - `LOW_BATTERY=15`: pin dưới 15% sẽ hiện chữ cảnh báo ở góc màn hình.
2. Cắm Kindle vào máy tính, chép:
   - cả thư mục **`kindle/dashboard/`** vào **gốc ổ Kindle**, để thành `Kindle/dashboard/`
   - file **`kindle/documents/Dashboard.sh`** vào thư mục **`documents`** của Kindle
3. Rút cáp. Trong Thư viện sẽ có "cuốn sách" **Dashboard Lich & Todo**. Bấm vào để bật.
   Kindle tắt giao diện thường, hiện dashboard, rồi cứ đến giờ lại tự bật Wi-Fi, tải ảnh mới, tắt Wi-Fi và ngủ.

**Thoát về Kindle bình thường:** bấm nút nguồn **1 lần**. Nếu không được thì giữ nút nguồn khoảng 40 giây cho máy khởi động lại.
**Bật lại:** bấm "Dashboard Lich & Todo" trong Thư viện. Mỗi lần mở là tải ảnh mới ngay.

---

## Phần 4: Tuỳ chỉnh

Hầu hết tuỳ chỉnh nằm trong file `.github/workflows/update.yml` trên GitHub: mở file → ✏️ → sửa → **Commit changes**. Workflow sẽ tự chạy lại, không cần đụng vào Kindle.

| Muốn | Sửa gì |
|---|---|
| Cập nhật ngay, không chờ | Tab **Actions** → Cập nhật dashboard Kindle → **Run workflow**. Có ✅ thì thoát và mở lại Dashboard trên Kindle. |
| Đổi thành phố thời tiết | `DASH_LAT`, `DASH_LON` trong `update.yml` |
| Chữ to/nhỏ hơn | `DASH_SCALE` trong `update.yml`: mặc định `"1.3"`. Số nhỏ hơn (ví dụ `"1.15"`) thì chữ nhỏ hơn, hiện được nhiều việc/sự kiện hơn. |
| Ẩn bớt lịch | **Settings → Secrets and variables → Actions → tab Variables** → tạo `DASH_SKIP_CALENDARS` = tên các lịch muốn ẩn, cách nhau dấu phẩy (ví dụ `Holidays in Vietnam,Birthdays`) |
| Đổi giờ ngủ đêm, tần suất làm mới | `config.sh` trên Kindle (cắm cáp, mở `dashboard/config.sh`) |
| Màn hình bị bóng mờ | Trong `dashboard/loop.sh` trên Kindle, đổi `eips -g "$IMG"` thành `eips -f -g "$IMG"` (làm mới toàn màn hình, nháy đen 1 cái mỗi lần) |

---

## Phần 5 (tuỳ chọn): Hiện mức dùng Claude

Phần này dành cho người **dùng gói Claude Pro/Max** và **có một chiếc Mac luôn bật**. Mac sẽ đọc mức dùng (phiên 5 giờ + giới hạn tuần) 10 phút/lần, gửi lên Apps Script, dashboard hiện thành số % cỡ lớn kèm thanh tiến độ.

> Mức dùng được lấy qua một địa chỉ nội bộ chưa công bố của Claude, có thể ngừng hoạt động bất cứ lúc nào. Coi như tính năng cho vui.

1. Trên Mac, mở Terminal kiểm tra Claude Code: `claude --version`. Chưa có thì cài:
   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   ```
   Mở tab Terminal mới, gõ `claude`, đăng nhập bằng tài khoản Claude, xong gõ `/exit`.
2. Chép thư mục **`mac/`** trong bộ này vào thư mục nhà, đổi tên thành `kindle-dashboard-mac`. Hoặc tải từ repo của bạn (thay `<tên-github>` và `<tên-repo>`):
   ```bash
   mkdir -p ~/kindle-dashboard-mac && cd ~/kindle-dashboard-mac
   for f in claude_usage.sh install.sh; do curl -fsSL -o "$f" "https://raw.githubusercontent.com/<tên-github>/<tên-repo>/main/mac/$f"; done
   ```
3. Lưu DATA_URL vào máy: copy DATA_URL vào clipboard, rồi chạy lệnh dưới (lệnh không in token ra màn hình):
   ```bash
   pbpaste | tr -d ' \n\r' > ~/.kindle-dashboard-url && chmod 600 ~/.kindle-dashboard-url
   ```
4. Cài job chạy ngầm:
   ```bash
   bash ~/kindle-dashboard-mac/install.sh
   ```
   Khi macOS hỏi quyền truy cập *"Claude Code-credentials"*: nhập mật khẩu Mac rồi bấm **Always Allow** (đừng chỉ bấm Allow).
5. Kiểm tra: `tail -3 ~/kindle-dashboard-mac/claude_usage.log` có dòng `OK {"five_hour":...` là được.
6. Chuyển dashboard sang bố cục Claude: tab **Variables** tạo `DASH_LAYOUT` = `claude`. Hoặc chạy lệnh:
   ```bash
   gh variable set DASH_LAYOUT --body claude -R <tên-github>/<tên-repo>
   ```
   Bố cục này bỏ phần ngày/thời tiết ở đầu, thay bằng mục Claude cỡ lớn. Muốn quay lại bố cục lịch thì đặt `DASH_LAYOUT` = `lich`.
   - Đổi tiêu đề: sửa `DASH_TITLE` trong `update.yml` (ví dụ `"Claude của Lan"`).
   - Thêm logo cạnh tiêu đề: upload một ảnh tên `logo.png` (nên là PNG nền trong suốt) vào thư mục gốc repo.

Để Mac không làm gián đoạn: **System Settings → Energy** bật *Prevent automatic sleeping* và *Start up automatically after a power failure*; **Users & Groups** bật tự đăng nhập.

---

## Xử lý sự cố

| Hiện tượng | Cách sửa |
|---|---|
| Script báo "Chưa có GitHub CLI (gh)" / "Chưa có git" | Cài theo Phần 2, Cách A, bước 1. Windows nhớ chạy trong **Git Bash**. |
| Script báo repo đã tồn tại | Chạy lại, chọn tên repo khác. |
| Kindle báo "Chua sua IMAGE_URL" | Chưa có link ảnh trong `dashboard/config.sh` (Phần 3, bước 1). |
| Kindle hiện ảnh cũ | GitHub chạy lịch trễ, hoặc Kindle chưa đến giờ tải. Run workflow tay, rồi thoát và mở lại Dashboard. Xem thêm `dashboard/log.txt` trên Kindle. |
| Actions báo ❌ ở bước "Tải font Inter" | Lỗi mạng thoáng qua, bấm **Re-run jobs**. Nếu vẫn lỗi thì dashboard dùng font dự phòng. |
| Actions báo ❌ ở bước deploy ("No artifacts…") | Lỗi phía GitHub, tự hết ở lượt sau. Muốn ngay thì bấm **Re-run failed jobs**. |
| Actions báo lỗi "Apps Script báo lỗi… kiểm tra token" | DATA_URL sai token. Dán DATA_URL vào trình duyệt: ra `{"error":"forbidden"}` là sai. Sửa secret `DATA_URL`. |
| Mở link ảnh báo 404 | Chưa bật **Settings → Pages → Source: GitHub Actions**, workflow chưa chạy xong, hoặc gõ sai `SECRET_PATH` trong link. |
| Mục Claude ghi "SỐ LIỆU CŨ" | Mac ngừng gửi quá 2 giờ (máy ngủ, mất điện, hết đăng nhập Claude Code). Xem `~/kindle-dashboard-mac/claude_usage.log`. Nếu báo "Không đọc được token" thì chạy `claude` để đăng nhập lại. |

---

## Bảo mật: 2 điều nhớ

1. **Không gửi DATA_URL, TOKEN hay link ảnh cho ai**, kể cả dán vào chat. Lỡ lộ thì đổi TOKEN trong Apps Script (Deploy → New version), rồi cập nhật secret `DATA_URL` trên GitHub (và file `~/.kindle-dashboard-url` trên Mac nếu dùng Phần 5).
2. Repo là **công khai**, nên **không dán token thật vào file `apps_script.gs` trên GitHub**. Token chỉ nằm trong Apps Script và trong mục Secrets.

---

*Phần tắt giao diện và hẹn giờ đánh thức Kindle dựa theo dự án mã nguồn mở usetrmnl/trmnl-kindle (MIT). Thời tiết: Open-Meteo. Font Inter (SIL Open Font License), tự tải khi chạy.*
