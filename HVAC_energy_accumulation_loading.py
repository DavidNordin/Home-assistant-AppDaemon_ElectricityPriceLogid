import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, timedelta

class BoilerAccumulator(hass.Hass):

    def initialize(self):
        self.learning_period = 7
        self.load_times = []
        self.unload_times = []
        self.run_daily(self.learn_load_time, self.datetime().time())

    def learn_load_time(self, kwargs):
        load_time = self.calculate_load_time()
        self.load_times.append(load_time)
        if len(self.load_times) > self.learning_period:
            self.load_times.pop(0)
        self.update_accumulator_settings()

    def learn_unload_time(self, kwargs):
        unload_time = self.calculate_unload_time()
        self.unload_times.append(unload_time)
        if len(self.unload_times) > self.learning_period:
            self.unload_times.pop(0)
        self.update_accumulator_settings()

    def calculate_load_time(self):
        # Assuming we have a sensor in Home Assistant that gives us the load time
        load_time = self.get_state("sensor.load_time")
        return load_time

    def calculate_unload_time(self):
        # Assuming we have a sensor in Home Assistant that gives us the unload time
        unload_time = self.get_state("sensor.unload_time")
        return unload_time

    def update_accumulator_settings(self):
        # Assuming we have a service in Home Assistant that allows us to update the accumulator settings
        average_load_time = sum(self.load_times) / len(self.load_times)
        average_unload_time = sum(self.unload_times) / len(self.unload_times)
        self.call_service("accumulator/update_settings", load_time=average_load_time, unload_time=average_unload_time)

    def on_load_start(self):
        self.load_start_time = self.datetime()

    def on_load_end(self):
        load_time = self.datetime() - self.load_start_time
        self.load_times.append(load_time)
        if len(self.load_times) > self.learning_period:
            self.load_times.pop(0)
        self.update_accumulator_settings()

    def on_unload_start(self):
        self.unload_start_time = self.datetime()

    def on_unload_end(self):
        unload_time = self.datetime() - self.unload_start_time
        self.unload_times.append(unload_time)
        if len(self.unload_times) > self.learning_period:
            self.unload_times.pop(0)
        self.update_accumulator_settings()

    def calculate_expected_runtime(self):
        # Assuming we have sensors in Home Assistant that give us the indoor and outdoor temperatures
        indoor_temp = self.get_state("sensor.indoor_temperature")
        outdoor_temp = self.get_state("sensor.outdoor_temperature")
        expected_runtime = (indoor_temp - outdoor_temp) * 10  # This is a simple formula, adjust as needed
        return expected_runtime

    def on_start(self):
        expected_runtime = self.calculate_expected_runtime()
        self.log(f"Expected runtime for fully loaded tanks: {expected_runtime} minutes")