import appdaemon.plugins.hass.hassapi as hass
import datetime
import pytz

class TemperatureStats(hass.Hass):
    TEMPERATURE_SENSOR = 'sensor.sensor_i_vaxthuset_temperature'
    TEMPERATURE_SPANS_SENSOR = 'sensor.greenhousetemperaturespans'
    TEMPERATURE_SPANS = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 35), (35, 40)]

    def initialize(self):
        self.log("initialize called")
        # Set up the scheduled callback
        self.run_minutely(self.calculate_stats, start=datetime.time(0, 0, 0))
        self.current_day = datetime.datetime.now().date()
        self.minutes_in_span = {span: 0 for span in self.TEMPERATURE_SPANS}

    def get_temperature_data(self, start_time, end_time):
        temperature_data = {}
        previous_day_end_time = start_time - datetime.timedelta(minutes=1)
        previous_day_start_time = previous_day_end_time - datetime.timedelta(minutes=1)
        previous_day_temperature_data = self.get_history(
            entity_id=self.TEMPERATURE_SENSOR,
            start_time=previous_day_start_time,
            end_time=previous_day_end_time
        )
        if previous_day_temperature_data and previous_day_temperature_data[0]:
            last_temperature = previous_day_temperature_data[0][0]["state"]
            if last_temperature not in ['unknown', 'unavailable']:
                temperature_data[start_time.strftime("%Y-%m-%dT%H:%M")] = float(last_temperature)
                #self.log(f"Added last temperature of previous day: {last_temperature} at {start_time.strftime('%Y-%m-%dT%H:%M')}")
    
        temperature_state_history = self.get_history(
            entity_id=self.TEMPERATURE_SENSOR,
            start_time=start_time,
            end_time=end_time
        )
        if temperature_state_history:
            for state_list in temperature_state_history:
                for state in state_list:
                    timestamp = state["last_changed"]
                    try:
                        timestamp = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f%z")
                    except ValueError:
                        timestamp = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")
                    timestamp = timestamp.replace(second=0, microsecond=0)
                    timestamp = timestamp.strftime("%Y-%m-%dT%H:%M")
                    temperature = state["state"]
                    if temperature not in ['unknown', 'unavailable']:
                        temperature_data[timestamp] = float(temperature)
        return temperature_data

    def generate_timestamps(self, start_time, end_time):
        timestamps = []
        current_time = start_time
        while current_time < end_time:
            timestamps.append((current_time, None))
            current_time += datetime.timedelta(minutes=1)
        timestamps.append((end_time, None))
        return timestamps

    def calculate_stats(self, kwargs):
        self.minutes_in_span = {span: 0 for span in self.TEMPERATURE_SPANS}
        now = datetime.datetime.now()
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        end_time = now.replace(tzinfo=None)

        temperature_data = self.get_temperature_data(start_time, end_time)
        #self.log(f"Temperature data keys: {temperature_data.keys()}")  # Log the keys in temperature_data

        all_timestamps = self.generate_timestamps(start_time, end_time)

        existing_timestamps_count = 0
        for timestamp, temp in temperature_data.items():
            dt = timestamp
            if dt in [ts[0].strftime("%Y-%m-%dT%H:%M") for ts in all_timestamps]:
                index = [ts[0].strftime("%Y-%m-%dT%H:%M") for ts in all_timestamps].index(dt)
                all_timestamps[index] = (all_timestamps[index][0], temp)
                existing_timestamps_count += 1

        interpolated_values_count = 0
        for i, (timestamp, temp) in enumerate(all_timestamps):
            if temp is None:
                before = next((t for t in reversed(all_timestamps[:i]) if t[1] is not None), None)
                after = next((t for t in all_timestamps[i + 1:] if t[1] is not None), None)
                if before is not None and after is not None:
                    before_time, before_temp = before
                    after_time, after_temp = after
                    interpolation_fraction = (timestamp - before_time) / (after_time - before_time)
                    interpolated_temp = before_temp + (after_temp - before_temp) * interpolation_fraction
                    all_timestamps[i] = (timestamp, interpolated_temp)
                    interpolated_values_count += 1
                else:
                    if start_time.strftime("%Y-%m-%dT%H:%M") in temperature_data:
                        all_timestamps[i] = (timestamp, temperature_data[start_time.strftime("%Y-%m-%dT%H:%M")])
                        interpolated_values_count += 1

        #self.log(f"Interpolated {interpolated_values_count} missing values")

        if all_timestamps[0][1] is None and len(all_timestamps) > 1:
            all_timestamps[0] = (all_timestamps[0][0], all_timestamps[1][1])

        for timestamp, temp in all_timestamps:
            for span in self.TEMPERATURE_SPANS:
                if temp is not None and span[0] <= temp < span[1]:
                    self.minutes_in_span[span] += 1


        attributes = {"Temperature within {}-{}ºC".format(span[0], span[1]): minutes for span, minutes in self.minutes_in_span.items()}
        self.update_sensor('sensor.temperature_spans', attributes)

    def update_sensor(self, sensor_name, attributes):
        try:
            self.set_state(self.TEMPERATURE_SPANS_SENSOR, state="on", attributes=attributes)
        except Exception as e:
            self.log(f"Error updating sensor {sensor_name}: {e}")
