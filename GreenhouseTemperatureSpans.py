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
        # Retrieve the last temperature value from the previous day
        previous_day_end_time = start_time - datetime.timedelta(minutes=1)
        previous_day_start_time = previous_day_end_time - datetime.timedelta(minutes=1)
        previous_day_temperature_data = self.get_history(
            entity_id=self.TEMPERATURE_SENSOR,
            start_time=previous_day_start_time,
            end_time=previous_day_end_time
        )
        if previous_day_temperature_data is not None and len(previous_day_temperature_data) > 0:
            last_temperature = previous_day_temperature_data[0][0]["state"]
            if last_temperature not in ['unknown', 'unavailable']:
                temperature_data[start_time.strftime("%Y-%m-%dT%H:%M")] = float(last_temperature)
    
        temperature_state_history = self.get_history(
            entity_id=self.TEMPERATURE_SENSOR,
            start_time=start_time,
            end_time=end_time
        )
        if temperature_state_history is not None:
            for state_list in temperature_state_history:
                for state in state_list:
                    timestamp = state["last_changed"]
                    # Convert the timestamp string to a datetime object
                    try:
                        timestamp = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f%z")
                    except ValueError:
                        timestamp = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")
                    # Adjust the timestamp to match the format of the timestamps in all_timestamps
                    timestamp = timestamp.replace(second=0, microsecond=0)
                    # Convert the datetime object back to a string
                    timestamp = timestamp.strftime("%Y-%m-%dT%H:%M")
                    temperature = state["state"]
                    if temperature not in ['unknown', 'unavailable']:
                        temperature_data[timestamp] = float(temperature)
        return temperature_data

    def generate_timestamps(self, start_time, end_time):
        # Generate timestamps for each minute of the day from start_time to end_time
        timestamps = []
        current_time = start_time
        while current_time < end_time:
            timestamps.append((current_time, None))  # Add a tuple of timestamp and None
            current_time += datetime.timedelta(minutes=1)
        timestamps.append((end_time, None))
    
        # Log the number of timestamps generated
        #self.log("Generated {} timestamps".format(len(timestamps)))
    
        return timestamps

    def calculate_stats(self, kwargs):
        # Reset the minutes_in_span dictionary
        self.minutes_in_span = {span: 0 for span in self.TEMPERATURE_SPANS}
        # Check if the current day has changed
        now = datetime.datetime.now()
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        end_time = now.replace(tzinfo=None)

        # Log the start_time and end_time
        #self.log("Start time: {}".format(start_time))
        #self.log("End time: {}".format(end_time))

        # Retrieve historical temperature data
        temperature_data = self.get_temperature_data(start_time, end_time)

        # Generate timestamps for each minute of the day
        all_timestamps = self.generate_timestamps(start_time, end_time)

        # Populate temperature values for existing historical timestamps
        existing_timestamps_count = 0
        for timestamp, temp in temperature_data.items():
            dt = timestamp
            if dt in [ts[0].strftime("%Y-%m-%dT%H:%M") for ts in all_timestamps]:  # Check if the timestamp exists in all_timestamps
                index = [ts[0].strftime("%Y-%m-%dT%H:%M") for ts in all_timestamps].index(dt)  # Get the index of the timestamp
                all_timestamps[index] = (all_timestamps[index][0], temp)
                existing_timestamps_count += 1
        #self.log("Populated {} existing timestamps".format(existing_timestamps_count))

        # Interpolate missing values
        interpolated_values_count = 0
        for i, (timestamp, temp) in enumerate(all_timestamps):
            if temp is None:
                # Find adjacent timestamps with temperature values
                before = next((t for t in reversed(all_timestamps[:i]) if t[1] is not None), None)
                after = next((t for t in all_timestamps[i + 1:] if t[1] is not None), None)
                if before is not None and after is not None:
                    # Interpolate temperature value
                    before_time, before_temp = before
                    after_time, after_temp = after
                    interpolation_fraction = (timestamp - before_time) / (after_time - before_time)
                    interpolated_temp = before_temp + (after_temp - before_temp) * interpolation_fraction
                    all_timestamps[i] = (timestamp, interpolated_temp)
                    interpolated_values_count += 1
                else:
                    # If there are no adjacent timestamps with temperature values, use the last temperature value from the previous day
                    all_timestamps[i] = (timestamp, temperature_data[start_time.strftime("%Y-%m-%dT%H:%M")])
                    interpolated_values_count += 1

        # Log the number of interpolated values
        #self.log("Interpolated {} missing values".format(interpolated_values_count))  # Add this line
        
        # Log the number of unprocessed timestamps
        unprocessed_timestamps_count = len(all_timestamps) - existing_timestamps_count - interpolated_values_count
        #self.log("Unprocessed {} timestamps".format(unprocessed_timestamps_count))
    
        # Fill values from first occurrence of the day if midnight is missing
        if all_timestamps[0][1] is None:
            all_timestamps[0] = (all_timestamps[0][0], all_timestamps[1][1])
    
        # Update time in each temperature span
        for timestamp, temp in all_timestamps:
            for span in self.TEMPERATURE_SPANS:
                if span[0] <= temp < span[1]:
                    self.minutes_in_span[span] += 1
    
        # Log the total number of timestamps processed
        #self.log("Processed {} timestamps in total".format(len(all_timestamps)))
    
        # Update the sensor with the new temperature spans
        attributes = {"Temperature within {}-{}ºC".format(span[0], span[1]): minutes for span, minutes in self.minutes_in_span.items()}
        self.update_sensor('sensor.temperature_spans', attributes)

    def update_sensor(self, sensor_name, attributes):
        try:
            self.set_state(self.TEMPERATURE_SPANS_SENSOR, state="on", attributes=attributes)
        except Exception as e:
            self.log("Error updating sensor {}: {}".format(sensor_name, e))
