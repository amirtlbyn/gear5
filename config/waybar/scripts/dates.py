#!/usr/bin/env python3
# Waybar: Gregorian + Persian date in one pill, full dates in tooltip
import datetime, json


def to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100
            + (gy2 + 399) // 400 + gd + g_d_m[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
RLI, PDI = "\u2067", "\u2069"   # keep Persian text right-to-left without messing up the rest

t = datetime.date.today()
y, m, d = to_jalali(t.year, t.month, t.day)
fa_short = f"{d} {MONTHS[m-1]}".translate(FA)
fa_full  = f"{WEEKDAYS[t.weekday()]} {d} {MONTHS[m-1]} {y}".translate(FA)

print(json.dumps({
    "text": f"{t:%A, %B %d} · {RLI}" + f"{d} {MONTHS[m-1]}".translate(FA) + PDI,
    "tooltip": f"{t:%A, %d %B %Y}\n{RLI}{fa_full}{PDI}",
}, ensure_ascii=False))
