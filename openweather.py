#!/usr/bin/env python3
import requests
import os

# for more details on openweathermap api please refer to https://openweathermap.org/current
OPENWEATHERMAP_URL = 'https://api.openweathermap.org/data/2.5/'
# a valid APPID is needed [Get by creating an openweathermap account (free)]
APPID = os.environ.get('OPENWEATHERMAP_APPID', '')
CITY_ID = os.environ.get('OPENWEATHERMAP_CITY_ID', '')


class Weather:
    def __init__(self, condition="", description="", temp=0.0, icon=""):
        self.condition = condition
        self.description = description
        self.temp = temp
        self.icon = icon


def apiGet(url):
    return requests.get(url)


def getWeather(city_id, appid, weather_mode='weather', units='metric'):
    '''
        Calls openweathermap url and returns a Weather object.
        Valid OPENWEATHERMAP_APPID and OPENWEATHERMAP_CITY_ID
        need to be defined as environment variables to get the correct results.
    '''
    if (appid is None) or (not isinstance(appid, str)):
        raise TypeError('appid must be a str')

    if units not in ['metric', 'imperial', '']:
        raise Exception('units not valid')

    # build url
    url = '{}{}?id={}&appid={}&units={}'.format(
        OPENWEATHERMAP_URL, weather_mode, city_id, appid, units)
    # get weather response
    resp = apiGet(url)

    # return response text if not sucessfull
    if resp.status_code != 200:
        raise Exception('GET /tasks/ status_code:{}'.format(resp.status_code))

    json_resp = resp.json()

    weather_condition_resp = ""
    weather_description_resp = ""
    weather_icon_resp = ""
    temp_resp = 0.0

    if 'weather' in json_resp:
        if len(json_resp['weather']) > 0:
            first_weather_elem = json_resp['weather'][0]
            weather_condition_resp = first_weather_elem['main']
            weather_description_resp = first_weather_elem['description']
            weather_icon_resp = first_weather_elem['icon']

    if 'main' in json_resp and 'temp' in json_resp['main']:
        temp_resp = json_resp['main']['temp']

    return Weather(weather_condition_resp, weather_description_resp, temp_resp, weather_icon_resp)


# e.g.
# weather_now = getWeather(city_id=CITY_ID, appid=APPID, units='imperial')
# print(weather_now.condition, weather_now.description, weather_now.temp)
# out:
#  Smoke smoke 72.46
