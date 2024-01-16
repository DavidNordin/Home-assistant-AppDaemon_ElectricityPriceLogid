import appdaemon.plugins.hass.hassapi as hass
import datetime
from collections import deque

class QuantitativeTemperatureComparison(hass.Hass):
    COOLING_BASE_TEMPERATURE = 26.0
    HEATING_BASE_TEMPERATURE = 18.0
    OUTDOOR_SENSOR = "sensor.santetorp_rumsgivare_utegivare_temperature"
    INDOOR_SENSOR = "sensor.santetorp_rumsgivare_temperature"
    DVUT_SENSOR = "sensor.DVUT"
    DVUT_DAYS = 2
    daily_temps = deque(maxlen=DVUT_DAYS)

    def initialize(self):
        self.run_minutely(self.calculate_degree_minutes, datetime.time(minute=0, second=0))
        self.run_hourly(self.calculate_degree_hours, datetime.time(hour=0, minute=0, second=0))
        self.run_daily(self.calculate_degree_days, datetime.time(hour=0, minute=0, second=0))
        self.run_hourly(self.calculate_dvut, datetime.time(hour=0, minute=0, second=0))

    def calculate_degree_minutes(self, kwargs):
        temperature_data = self.get_temperature_data()
        CDM = round(sum(max(temp - self.COOLING_BASE_TEMPERATURE, 0) for temp in temperature_data) * 60, 1)
        HDM = round(sum(min(self.HEATING_BASE_TEMPERATURE - temp, 0) for temp in temperature_data) * 60, 1)
        self.set_state("sensor.CoolingDegreeMinutes", state=CDM, attributes={"device_class": None, "state_class": "measurement"})
        self.set_state("sensor.HeatingDegreeMinutes", state=HDM, attributes={"device_class": None, "state_class": "measurement"})

    def calculate_degree_hours(self, kwargs):
        temperature_data = self.get_temperature_data()
        CDH = round(sum(max(temp - self.COOLING_BASE_TEMPERATURE, 0) for temp in temperature_data), 1)
        HDH = round(sum(min(self.HEATING_BASE_TEMPERATURE - temp, 0) for temp in temperature_data), 1)
        self.set_state("sensor.CoolingDegreeHours", state=CDH, attributes={"device_class": None, "state_class": "measurement"})
        self.set_state("sensor.HeatingDegreeHours", state=HDH, attributes={"device_class": None, "state_class": "measurement"})

    def calculate_degree_days(self, kwargs):
        temperature_data = self.get_temperature_data()
        CDD = round(sum(max(temp - self.COOLING_BASE_TEMPERATURE, 0) for temp in temperature_data), 1)
        HDD = round(sum(min(self.HEATING_BASE_TEMPERATURE - temp, 0) for temp in temperature_data), 1)
        self.set_state("sensor.CoolingDegreeDays", state=CDD, attributes={"device_class": None, "state_class": "measurement"})
        self.set_state("sensor.HeatingDegreeDays", state=HDD, attributes={"device_class": None, "state_class": "measurement"})

    def get_temperature_data(self):
        outdoor_temp = self.get_state(self.OUTDOOR_SENSOR)
        indoor_temp = self.get_state(self.INDOOR_SENSOR)
        return [float(outdoor_temp), float(indoor_temp)]

    def calculate_dvut(self, kwargs):
        daily_mean_temp = round(sum(self.daily_temps) / len(self.daily_temps), 1) if self.daily_temps else None
        outdoor_temp = self.get_state(self.OUTDOOR_SENSOR)
        if outdoor_temp is not None:
            self.daily_temps.append(float(outdoor_temp))
        current_dvut = self.get_state(self.DVUT_SENSOR)
        if daily_mean_temp is not None and (current_dvut is None or daily_mean_temp < float(current_dvut)):
            self.set_state(self.DVUT_SENSOR, state=daily_mean_temp, attributes={"device_class": "temperature", "state_class": "measurement"})