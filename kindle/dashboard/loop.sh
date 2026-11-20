#!/bin/sh
# Vòng lặp dashboard: bật Wi-Fi → tải PNG → hiển thị bằng eips → tắt Wi-Fi → ngủ (RTC) → lặp lại.
# Được chạy nền bởi documents/Dashboard.sh. Thoát: bấm nút nguồn 1 lần (dự phòng: giữ ~40 giây để khởi động lại).
# Cách tắt giao diện, đánh thức bằng RTC dựa theo usetrmnl/trmnl-kindle (MIT).

DIR="${DASH_DIR:-/mnt/us/dashboard}"
LOG="$DIR/log.txt"
IMG="/tmp/dashboard.png"
. "$DIR/config.sh"
# Đồng hồ Kindle chưa đăng ký thường để giờ UTC → ép giờ Việt Nam (POSIX: ICT-7 = UTC+7)
export TZ="${DASH_TZ:-ICT-7}"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"
  # giữ log nhỏ
  if [ "$(wc -c < "$LOG")" -gt 200000 ]; then tail -n 300 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
}

wifi() { lipc-set-prop com.lab126.cmd wirelessEnable "$1" 2>/dev/null; }

battery() {
  b=$(lipc-get-prop com.lab126.powerd battLevel 2>/dev/null)
  [ -n "$b" ] || b=$(lipc-get-prop com.lab126.powerd status 2>/dev/null | grep "Battery Level:" | cut -d: -f2 | tr -d '% ')
  echo "${b:-100}"
}

init() {
  log "=== Khởi động dashboard ==="
  # Tắt giao diện Kindle để icon trạng thái không vẽ đè lên ảnh và cho phép ngủ sâu.
  /etc/init.d/framework stop 2>/dev/null || {
    stop framework >/dev/null 2>&1 || initctl stop framework >/dev/null 2>&1
    stop lab126_gui >/dev/null 2>&1
  }
  initctl stop webreader >/dev/null 2>&1
  { echo powersave > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor; } 2>/dev/null
  lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
}

wait_net() {
  # chờ tối đa 45 giây đến khi có Internet
  i=0
  while [ $i -lt 45 ]; do
    curl -s -m 5 -o /dev/null -I "$IMAGE_URL" && return 0
    sleep 1
    i=$((i + 1))
  done
  return 1
}

# Vẽ % pin ở góc dưới bên phải (đè lên ảnh). Ưu tiên FBInk (Universal Hotfix có cài), không có thì dùng eips.
find_fbink() {
  for f in "$(command -v fbink 2>/dev/null)" /usr/bin/fbink /usr/local/bin/fbink /mnt/us/libkh/bin/fbink \
           /var/local/kmc/bin/fbink /mnt/us/extensions/MRInstaller/bin/KHF/fbink /mnt/us/extensions/MRInstaller/bin/PW2/fbink; do
    [ -n "$f" ] && [ -x "$f" ] && { echo "$f"; return; }
  done
  f=$(find /var/local /mnt/us/libkh /mnt/us/extensions -name fbink -type f 2>/dev/null | head -n 1)
  [ -n "$f" ] && [ -x "$f" ] && echo "$f"
}

draw_battery() {
  [ "${SHOW_BATTERY:-1}" = 1 ] || return 0
  txt="Pin $1%"
  [ -z "$FBINK" ] && FBINK=$(find_fbink)
  if [ -n "$FBINK" ]; then
    # cột/dòng âm = đếm từ mép phải/mép dưới
    "$FBINK" -q -x -$(( ${#txt} + ${BATTERY_COL_PAD:-2} )) -y -${BATTERY_ROW:-2} "$txt" 2>>"$LOG" && return 0
  fi
  # dự phòng: eips (lưới ô chữ 16x24 px trên màn 300ppi)
  xres=$(cut -d, -f1 /sys/class/graphics/fb0/virtual_size 2>/dev/null); xres=${xres:-1072}
  yres=$(cut -d, -f2 /sys/class/graphics/fb0/virtual_size 2>/dev/null); yres=${yres:-1448}
  cols=$(( xres / 16 )); rows=$(( yres / 24 ))
  eips $(( cols - ${#txt} - 2 )) $(( rows - 3 )) "$txt"
}

# Gửi % pin lên Apps Script để GitHub vẽ vào ảnh (cần DATA_URL trong config.sh)
send_battery() {
  [ -n "$DATA_URL" ] || return 0
  curl -s -L -m 30 -o /dev/null -H 'Content-Type: application/json' \
    --data "{\"battery\":$1}" "$DATA_URL&kind=kindle" 2>/dev/null || log "Gửi pin thất bại"
}

fetch_and_show() {
  wifi 1
  if ! wait_net; then
    log "Không có mạng"
    wifi 0; sleep 15; wifi 1          # thử bật lại Wi-Fi một lần
    wait_net || { eips 1 1 "Khong co Wi-Fi - se thu lai sau"; return 1; }
  fi
  send_battery "$(battery)"
  rm -f "$IMG"
  # thêm ?t=... để không bị bộ nhớ đệm CDN trả ảnh cũ
  curl -s -L -m 60 -o "$IMG" "$IMAGE_URL?t=$(date +%s)"
  if [ ! -s "$IMG" ]; then
    log "Tải ảnh thất bại"
    eips 1 1 "Tai anh that bai - se thu lai sau"
    return 1
  fi
  eips -c
  sleep 1
  eips -g "$IMG"
  b=$(battery)
  draw_battery "$b"
  if [ "$b" -lt "${LOW_BATTERY:-15}" ] 2>/dev/null; then
    eips 1 1 "PIN YEU ${b}% - HAY SAC"
  fi
  log "Đã cập nhật (pin ${b}%, vẽ pin bằng: ${FBINK:-eips})"
  return 0
}

# "HH:MM" hoặc "HH" -> số phút tính từ 0h
to_min() {
  hh=$(echo "$1" | cut -d: -f1 | sed 's/^0//'); mm=$(echo "$1" | grep ':' | cut -d: -f2 | sed 's/^0//')
  echo $(( ${hh:-0} * 60 + ${mm:-0} ))
}

sleep_secs() {
  mins=${INTERVAL_MIN:-30}
  [ "$mins" -ge 5 ] 2>/dev/null || mins=5
  ns=$(to_min "${NIGHT_START:-23}"); ne=$(to_min "${NIGHT_END:-6}")
  now=$(( $(date +%H | sed 's/^0//;s/^$/0/') * 60 + $(date +%M | sed 's/^0//;s/^$/0/') ))
  if [ "$ns" != "$ne" ]; then
    night=0
    if [ "$ns" -gt "$ne" ]; then { [ "$now" -ge "$ns" ] || [ "$now" -lt "$ne" ]; } && night=1
    else { [ "$now" -ge "$ns" ] && [ "$now" -lt "$ne" ]; } && night=1; fi
    if [ $night -eq 1 ]; then
      until_end=$(( ((ne - now + 1440) % 1440) * 60 ))
      [ $until_end -eq 0 ] && until_end=86400
      # NIGHT_INTERVAL_MIN > 0: ban đêm vẫn dậy làm mới mỗi N phút (không quá giờ NIGHT_END)
      nim=${NIGHT_INTERVAL_MIN:-0}
      if [ "$nim" -ge 5 ] 2>/dev/null && [ $(( nim * 60 )) -lt $until_end ]; then
        echo $(( nim * 60 ))
      else
        echo $until_end
      fi
      return
    fi
    # sắp tới giờ nghỉ đêm thì dậy đúng giờ đó, rồi ngủ thẳng tới sáng
    to_night=$(( ((ns - now + 1440) % 1440) * 60 ))
    if [ $to_night -gt 0 ] && [ $to_night -lt $(( mins * 60 )) ]; then echo $to_night; return; fi
  fi
  echo $(( mins * 60 ))
}

go_to_sleep() {
  secs=$1
  [ "${WIFI_OFF_WHILE_SLEEP:-1}" = 1 ] && wifi 0
  log "Ngủ ${secs}s"
  sleep 10   # chờ màn hình vẽ xong; cũng là khoảng để dừng script nếu cần
  [ -n "$DASH_ONCE" ] && exit 0
  RTC=/sys/class/rtc/rtc1
  [ -d "$RTC" ] || RTC=/sys/class/rtc/rtc0
  wake_at=$(( $(date +%s) + secs ))
  # đặt báo thức RTC rồi ngủ sâu; nếu không được thì sleep thường
  if { echo 0 > "$RTC/wakealarm" &&
       echo "+${secs}" > "$RTC/wakealarm" &&
       echo mem > /sys/power/state; } 2>/dev/null; then
    # Tỉnh dậy sớm hơn giờ hẹn quá 60 giây = có người bấm nút nguồn → thoát dashboard
    if [ "$(date +%s)" -lt $(( wake_at - 60 )) ]; then
      exit_dashboard
    fi
  else
    sleep "$secs"
  fi
}

exit_dashboard() {
  log "Bấm nút nguồn → thoát dashboard, bật lại giao diện Kindle"
  echo 0 > "$RTC/wakealarm" 2>/dev/null
  eips -c
  eips 1 1 "Dang thoat dashboard, cho chut..."
  lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
  wifi 1
  /etc/init.d/framework start 2>/dev/null || {
    start lab126_gui >/dev/null 2>&1
    start framework >/dev/null 2>&1 || initctl start framework >/dev/null 2>&1
  }
  exit 0
}

init
while true; do
  if fetch_and_show; then
    go_to_sleep "$(sleep_secs)"
  else
    go_to_sleep 300   # lỗi thì 5 phút sau thử lại
  fi
done
