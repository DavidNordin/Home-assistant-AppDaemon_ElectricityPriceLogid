import appdaemon.plugins.hass.hassapi as hass
import math

class HumiditySensor(hass.Hass):
    def initialize(self):
        self.run_every(self.update_humidity_and_dew_point, "now", 60*60)

    def update_humidity_and_dew_point(self, kwargs):
        T = float(self.get_state("sensor.temperature"))  # Replace with your sensor
        RH = float(self.get_state("sensor.humidity"))  # Replace with your sensor

        AH = self.calculate_absolute_humidity(T, RH)
        dew_point = self.calculate_dew_point(T, RH)

        self.log(f"Absolute humidity: {AH} g/m³")
        self.log(f"Dew point: {dew_point} degrees Celsius")

        self.set_state("sensor.absolute_humidity", state=AH)
        self.set_state("sensor.dew_point", state=dew_point)

    def calculate_absolute_humidity(self, T, RH):
        e_s = 6.112 * math.exp((17.67 * T) / (T + 243.5))
        e = RH / 100 * e_s
        AH = 216.7 * (e / (T + 273.15))
        return AH

    def calculate_dew_point(self, T, RH):
        B = 17.27
        C = 237.7
        alpha = ((B * T) / (C + T)) + math.log(RH/100.0)
        dew_point = (C * alpha) / (B - alpha)
        return dew_point