#!/usr/bin/env python3
# -*- coding: utf-8 -*-s
# MIT License
#
# Copyright (c) 2018 Pimoroni Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import logging
from openweather import APPID, CITY_ID, Weather,  getWeather
from datetime import datetime, timedelta
from astral.sun import sun
from astral.geocoder import database, lookup
from pytz import timezone
import pytz
from ltr559 import LTR559
from bme280 import BME280
import ST7735
from fonts.ttf import RobotoMedium as UserFont
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import colorsys
import numpy
import time
import os
f"Sorry! This program requires Python >= 3.6 😅"


logger = logging.getLogger('enviro')
hdlr = logging.FileHandler('./error.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.WARNING)

try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus


def calculate_y_pos(x, centre):
    """Calculates the y-coordinate on a parabolic curve, given x."""
    centre = 80
    y = 1 / centre * (x - centre) ** 2

    return int(y)


def circle_coordinates(x, y, radius):
    """Calculates the bounds of a circle, given centre and radius."""

    x1 = x - radius  # Left
    x2 = x + radius  # Right
    y1 = y - radius  # Bottom
    y2 = y + radius  # Top

    return (x1, y1, x2, y2)


def map_colour(x, centre, start_hue, end_hue, day):
    """Given an x coordinate and a centre point, a start and end hue (in degrees),
       and a Boolean for day or night (day is True, night False), calculate a colour
       hue representing the 'colour' of that time of day."""

    start_hue = start_hue / 360  # Rescale to between 0 and 1
    end_hue = end_hue / 360

    sat = 1.0

    # Dim the brightness as you move from the centre to the edges
    val = 1 - (abs(centre - x) / (2 * centre))

    # Ramp up towards centre, then back down
    if x > centre:
        x = (2 * centre) - x

    # Calculate the hue
    hue = start_hue + ((x / centre) * (end_hue - start_hue))

    # At night, move towards purple/blue hues and reverse dimming
    if not day:
        hue = 1 - hue
        val = 1 - val

    r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, sat, val)]

    return (r, g, b)


def x_from_sun_moon_time(progress, period, x_range):
    """Recalculate/rescale an amount of progress through a time period."""

    x = int((progress / period) * x_range)

    return x


def sun_moon_time(city_name, time_zone):
    """Calculate the progress through the current sun/moon period (i.e day or
       night) from the last sunrise or sunset, given a datetime object 't'."""

    city = lookup(city_name, database())

    # Datetime objects for yesterday, today, tomorrow
    utc = pytz.utc
    utc_dt = datetime.now(tz=utc)
    local_dt = utc_dt.astimezone(pytz.timezone(time_zone))
    today = local_dt.date()
    yesterday = today - timedelta(1)
    tomorrow = today + timedelta(1)

    # Sun objects for yesterday, today, tomorrow
    sun_yesterday = sun(city.observer, date=yesterday)
    sun_today = sun(city.observer, date=today)
    sun_tomorrow = sun(city.observer, date=tomorrow)

    # Work out sunset yesterday, sunrise/sunset today, and sunrise tomorrow
    sunset_yesterday = sun_yesterday["sunset"]
    sunrise_today = sun_today["sunrise"]
    sunset_today = sun_today["sunset"]
    sunrise_tomorrow = sun_tomorrow["sunrise"]

    # Work out lengths of day or night period and progress through period
    if sunrise_today < local_dt < sunset_today:
        day = True
        period = sunset_today - sunrise_today
        # mid = sunrise_today + (period / 2)
        progress = local_dt - sunrise_today

    elif local_dt > sunset_today:
        day = False
        period = sunrise_tomorrow - sunset_today
        # mid = sunset_today + (period / 2)
        progress = local_dt - sunset_today

    else:
        day = False
        period = sunrise_today - sunset_yesterday
        # mid = sunset_yesterday + (period / 2)
        progress = local_dt - sunset_yesterday

    # Convert time deltas to seconds
    progress = progress.total_seconds()
    period = period.total_seconds()

    return (progress, period, day, local_dt)


def draw_background(progress, period, day):
    """Given an amount of progress through the day or night, draw the
       background colour and overlay a blurred sun/moon."""

    # x-coordinate for sun/moon
    x = x_from_sun_moon_time(progress, period, WIDTH)

    # If it's day, then move right to left
    if day:
        x = WIDTH - x

    # Calculate position on sun/moon's curve
    centre = WIDTH / 2
    y = calculate_y_pos(x, centre)

    # Background colour
    background = map_colour(x, 80, mid_hue, day_hue, day)

    # New image for background colour
    img = Image.new('RGBA', (WIDTH, HEIGHT), color=background)
    # draw = ImageDraw.Draw(img)

    # New image for sun/moon overlay
    overlay = Image.new('RGBA', (WIDTH, HEIGHT), color=(0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Draw the sun/moon
    circle = circle_coordinates(x, y, sun_radius)
    overlay_draw.ellipse(circle, fill=(200, 200, 50, opacity))

    # Overlay the sun/moon on the background as an alpha matte
    composite = Image.alpha_composite(img, overlay).filter(
        ImageFilter.GaussianBlur(radius=blur))

    return composite


def overlay_text(img, position, text, font, align_right=False, rectangle=False):
    draw = ImageDraw.Draw(img)
    w, h = font.getsize(text)
    if align_right:
        x, y = position
        x -= w
        position = (x, y)
    if rectangle:
        x += 1
        y += 1
        position = (x, y)
        border = 1
        rect = (x - border, y, x + w, y + h + border)
        rect_img = Image.new('RGBA', (WIDTH, HEIGHT), color=(0, 0, 0, 0))
        rect_draw = ImageDraw.Draw(rect_img)
        rect_draw.rectangle(rect, (255, 255, 255))
        rect_draw.text(position, text, font=font, fill=(0, 0, 0, 0))
        img = Image.alpha_composite(img, rect_img)
    else:
        draw.text(position, text, font=font, fill=(255, 255, 255))
    return img


def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = f.read()
        temp = int(temp) / 1000.0
    return temp


def correct_humidity(humidity, temperature, corr_temperature):
    dewpoint = temperature - ((100 - humidity) / 5)
    corr_humidity = 100 - (5 * (corr_temperature - dewpoint))
    return min(100, corr_humidity)


def analyse_pressure(pressure, t):
    global time_vals, pressure_vals, trend
    if len(pressure_vals) > num_vals:
        pressure_vals = pressure_vals[1:] + [pressure]
        time_vals = time_vals[1:] + [t]

        # Calculate line of best fit
        line = numpy.polyfit(time_vals, pressure_vals, 1, full=True)

        # Calculate slope, variance, and confidence
        slope = line[0][0]
        intercept = line[0][1]
        variance = numpy.var(pressure_vals)
        residuals = numpy.var([(slope * x + intercept - y)
                               for x, y in zip(time_vals, pressure_vals)])
        r_squared = 1 - residuals / variance

        # Calculate change in pressure per hour
        change_per_hour = slope * 60 * 60
        # variance_per_hour = variance * 60 * 60

        mean_pressure = numpy.mean(pressure_vals)

        # Calculate trend
        if r_squared > 0.5:
            if change_per_hour > 0.5:
                trend = ">"
            elif change_per_hour < -0.5:
                trend = "<"
            elif -0.5 <= change_per_hour <= 0.5:
                trend = "-"

            if trend != "-":
                if abs(change_per_hour) > 3:
                    trend *= 2
    else:
        pressure_vals.append(pressure)
        time_vals.append(t)
        mean_pressure = numpy.mean(pressure_vals)
        change_per_hour = 0
        trend = "-"

    # time.sleep(interval)
    return (mean_pressure, change_per_hour, trend)


def describe_pressure(pressure):
    """Convert pressure into barometer-type description."""
    if pressure < 970:
        description = "storm"
    elif 970 <= pressure < 990:
        description = "rain"
    elif 990 <= pressure < 1010:
        description = "change"
    elif 1010 <= pressure < 1030:
        description = "fair"
    elif pressure >= 1030:
        description = "dry"
    else:
        description = ""
    return description


def describe_humidity(humidity):
    """Convert relative humidity into good/bad description."""
    # description str will be used to fetch the humidity's icon
    if 40 < humidity < 60:
        # description = "good"
        description = "ok"
    else:
        # description = "bad"
        description = "high"
    return description


def describe_light(light):
    """Convert light level in lux to descriptive value."""
    if light < 50:
        description = "dark"
    elif 50 <= light < 100:
        description = "dim"
    elif 100 <= light < 500:
        description = "light"
    elif light >= 500:
        description = "bright"
    return description


# Initialise the LCD
disp = ST7735.ST7735(
    port=0,
    cs=1,
    dc=9,
    backlight=12,
    rotation=270,
    spi_speed_hz=10000000
)

disp.begin()

WIDTH = disp.width
HEIGHT = disp.height

# The city and timezone that you want to display.
# For other cities refer to https://astral.readthedocs.io/en/latest/#cities
city_name = "San Francisco"
# For other timezones please refer to pytz.all_timezones
time_zone = "America/Los_Angeles"

# Values that alter the look of the background
blur = 50
opacity = 125

mid_hue = 0
day_hue = 25

sun_radius = 50

# Fonts
font_sm = ImageFont.truetype(UserFont, 12)
font_lg = ImageFont.truetype(UserFont, 14)
font_xxl = ImageFont.truetype(UserFont, 24)

# Margins
margin = 3


# Set up BME280 weather sensor
bus = SMBus(1)
bme280 = BME280(i2c_dev=bus)

min_temp = None
max_temp = None

factor = 2.25
cpu_temps = [get_cpu_temperature()] * 5

# Set up light sensor
ltr559 = LTR559()

# Pressure variables
pressure_vals = []
time_vals = []
num_vals = 1000
interval = 1
trend = "-"

# display toggle variables
display_delay = 0.5  # Debounce the proximity tap
last_display = 0
display_on = True

# out weather variables
wsample_t = 900  # weather sampling time in seconds
last_wsample = 0
out_weather_now = Weather()  # initialize variable
wicon_size = (40, 40)

# Keep track of time elapsed
start_time = time.time()

try:
    while True:
        proximity = ltr559.get_proximity()
        # If the proximity crosses the threshold, toggle the mode
        if proximity > 1500 and time.time() - last_display > display_delay:
            display_on = not(display_on)
            last_display = time.time()

        # sample weather if weather sampling time arrives
        if time.time() - last_wsample > wsample_t:
            out_weather_now = getWeather(CITY_ID, APPID)
            last_wsample = time.time()

        if display_on:
            # turn backlight on
            disp.set_backlight(12)

            path = os.path.dirname(os.path.realpath(__file__))
            progress, period, day, local_dt = sun_moon_time(
                city_name, time_zone)
            background = draw_background(progress, period, day)

            # Time.
            time_elapsed = time.time() - start_time
            date_string = local_dt.strftime("%d %b %y").lstrip('0')
            time_string = local_dt.strftime("%H:%M")
            img = overlay_text(
                background, (0 + margin, 0 + margin), time_string, font_lg)
            img = overlay_text(img, (WIDTH - margin, 0 + margin),
                               date_string, font_lg, align_right=True)

            # Temperature
            temperature = bme280.get_temperature()

            # Corrected temperature
            cpu_temp = get_cpu_temperature()
            cpu_temps = cpu_temps[1:] + [cpu_temp]
            avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
            corr_temperature = temperature - \
                ((avg_cpu_temp - temperature) / factor)

            if time_elapsed > 30:
                if min_temp is not None and max_temp is not None:
                    if corr_temperature < min_temp:
                        min_temp = corr_temperature
                    elif corr_temperature > max_temp:
                        max_temp = corr_temperature
                else:
                    min_temp = corr_temperature
                    max_temp = corr_temperature

            temp_string = f"{corr_temperature:.0f}°C"
            img = overlay_text(img, (68, 18), temp_string,
                               font_lg, align_right=True)
            spacing = font_lg.getsize(temp_string)[1] + 1
            if min_temp is not None and max_temp is not None:
                range_string = f"{min_temp:.0f}-{max_temp:.0f}"
            else:
                range_string = "------"
            img = overlay_text(img, (68, 18 + spacing), range_string,
                               font_sm, align_right=True, rectangle=True)
            temp_icon = Image.open(f"{path}/icons/temperature.png")
            img.paste(temp_icon, (margin, 20), mask=temp_icon)

            # Humidity
            humidity = bme280.get_humidity()
            corr_humidity = correct_humidity(
                humidity, temperature, corr_temperature)
            humidity_string = f"{corr_humidity:.0f}%"
            img = overlay_text(img, (68, 48), humidity_string,
                               font_lg, align_right=True)
            spacing = font_lg.getsize(humidity_string)[1] + 1
            humidity_desc = describe_humidity(corr_humidity).upper()
            img = overlay_text(img, (68, 48 + spacing), humidity_desc,
                               font_sm, align_right=True, rectangle=True)
            humidity_icon = Image.open(
                f"{path}/icons/humidity-{humidity_desc.lower()}.png")
            img.paste(humidity_icon, (margin, 50), mask=humidity_icon)

            # Outside weather
            out_temp_string = f"{out_weather_now.temp:.0f}°C"
            img = overlay_text(img, (WIDTH - margin, 18),
                               out_temp_string, font_xxl, align_right=True)
            # outside weather icon
            out_weather_icon = Image.open(
                f"{path}/icons/openweathermap/{out_weather_now.icon.lower()}2.png")
            out_weather_icon = out_weather_icon.resize(wicon_size)
            img.paste(out_weather_icon, (74, 14), mask=out_weather_icon)
            # Outside Weather description
            wcondition = out_weather_now.condition
            img = overlay_text(img, (WIDTH - margin - 1, 45),
                               wcondition, font_lg, align_right=True, rectangle=True)

            # Pressure
            pressure = bme280.get_pressure()
            t = time.time()
            mean_pressure, change_per_hour, _ = analyse_pressure(pressure, t)
            pressure_string = f"{int(mean_pressure):,} hPa"
            # sums height of text plus rectangle extra pixels
            spacing_y = font_lg.getsize(wcondition)[1] + 2
            img = overlay_text(img, (WIDTH - margin, 48 + spacing_y),
                               pressure_string, font_lg, align_right=True)

            # Display image
            disp.display(img)
        else:
            # turn off backlight
            disp.set_backlight(0)

# Turn off backlight on control-c
except KeyboardInterrupt:
    logger.info('KeyboardInterrupt')
    disp.set_backlight(0)

except Exception as e:
    disp.set_backlight(0)
    logger.error(e)
