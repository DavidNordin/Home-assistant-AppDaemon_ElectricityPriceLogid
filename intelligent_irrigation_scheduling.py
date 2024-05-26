import appdaemon.plugins.hass.hassapi as hass
import pytz
import datetime
import asyncio

TIMEZONE = 'Europe/Stockholm'
local_tz = pytz.timezone(TIMEZONE)

# Define the minimum and maximum values for temperature, cycles, and water
TEMP_MIN, TEMP_MAX = 5, 30
CYCLES_MIN, CYCLES_MAX = 0, 3
WATER_MIN, WATER_MAX = 1, 3  # Adjusted for 1..5L daily need
MAX_WATER_PER_CYCLE = 1.5  # Maximum permitted water per cycle in liters

TOLERANCE = 300  # Define your tolerance in seconds

WATER_OUTPUT_RATE = 4  # Liters per hour

FORECAST_SENSOR = 'sensor.sensor_greenhouse_intelligent_irrigation_forecasting'
SCHEDULE_SENSOR = 'sensor.sensor_greenhouse_intelligent_irrigation_scheduling'

IRRIGATION_ACTUATOR = 'switch.sonoff_smartrelay_1'

class intelligent_irrigation_scheduling(hass.Hass):

    def initialize(self):
        self.log("Initializing Intelligent Irrigation Scheduler")
        
        # Schedule daily tasks
        #self.run_daily(self.schedule_irrigation, "04:00:00")
        
        # Set up listeners
        self.listen_state(self.on_sensor_change, FORECAST_SENSOR, attribute="all")
        self.listen_state(self.irrigation_actuator_state_change, IRRIGATION_ACTUATOR)
        
        # Initial call to setup irrigation
        self.schedule_irrigation(None)
        
        # Schedule the background safety check
        self.background_task = self.create_task(self.periodic_check())
        
        self.log("Initialization complete")
        
        # TEMP Call the temporary method to log history data
        self.run_in(self.log_history_data, 1)

    async def log_history_data(self, kwargs):
        self.log("Logging history data for investigation")

        # Define the entity ID and time range for history data
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(days=1)  # Adjust as needed

        # Fetch the history data
        history = await self.get_history(entity_id=IRRIGATION_ACTUATOR, start_time=start_time, end_time=end_time)

        # Log the history data to investigate its structure
        self.log(f"History data: {history}")

        # If history is empty or None, log a message
        if history is None or not history:
            self.log("No history data found")
        
    async def periodic_check(self):
        while True:
            await asyncio.sleep(60)  # Wait for 60 seconds
            current_time = datetime.datetime.now().time()
            if self.get_state(IRRIGATION_ACTUATOR) == 'on' and not self.is_time_in_scheduled_range(current_time):
                self.log("Irrigation system is on outside of scheduled times, sending notification")
                self.call_service('notify/notify', message='Irrigation system turned on outside of scheduled times.')
                self.turn_off_irrigation()

    def on_sensor_change(self, entity, attribute, old, new, kwargs):
        self.log("Sensor change detected")
        self.schedule_irrigation(None)

    def clear_old_schedules(self):
        self.log("Clearing old schedules")
        # Set scheduled_times to an empty dictionary if there are no schedules
        self.set_state(SCHEDULE_SENSOR, attributes={})
        self.log("Cleared all scheduled times")
    
    def schedule_irrigation(self, kwargs):
        self.log("Scheduling irrigation check")
    
        # Clear old schedules
        self.clear_old_schedules()
    
        sensor_state = self.get_state(FORECAST_SENSOR, attribute="all")
        if sensor_state and "attributes" in sensor_state:
            temperature_str = sensor_state["attributes"].get("daily_mean_temperature", None)
            if temperature_str:
                try:
                    temperature = float(temperature_str[:-2])
                    self.log(f"Daily mean temperature: {temperature}°C")
                    self.determine_irrigation_parameters(temperature)
                    scheduled_times = self.schedule_watering_cycles()
                    self.schedule_watering_callbacks(scheduled_times)
                    self.set_sensor_state()
                except ValueError as e:
                    self.log(f"Error parsing temperature value: {e}")
            else:
                self.log("Daily mean temperature attribute not found")
        else:
            self.log("Sensor attributes not found")

    def determine_irrigation_parameters(self, greenhouse_daily_mean_temperature):
        self.log("Entered determine_irrigation_parameters")
        
        # Calculate the scale factors for cycles and water
        WATER_SCALE = (WATER_MAX - WATER_MIN) / (TEMP_MAX - TEMP_MIN)  # Adjusted for WATER_MIN..WATER_MAX daily need

        # Adjusted linear relationship for daily water need based on temperature
        if TEMP_MIN <= greenhouse_daily_mean_temperature <= TEMP_MAX:
            daily_water_need = ((greenhouse_daily_mean_temperature - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) * (WATER_MAX - WATER_MIN) + WATER_MIN
        elif greenhouse_daily_mean_temperature < TEMP_MIN:
            daily_water_need = WATER_MIN
        else:
            daily_water_need = WATER_MAX

        # Calculate the number of cycles and water per cycle
        num_cycles = 1
        water_per_cycle = daily_water_need

        # If the water per cycle exceeds MAX_WATER_PER_CYCLE, increase the number of cycles (up to a maximum of three)
        while water_per_cycle > MAX_WATER_PER_CYCLE and num_cycles < 3:
            num_cycles += 1
            water_per_cycle = daily_water_need / num_cycles

        # Round the water per cycle to two decimal places
        water_per_cycle = round(water_per_cycle, 2)

        self.log(f"Temperature is {greenhouse_daily_mean_temperature}°C, calculated {num_cycles} cycles and {water_per_cycle}L water per cycle")

        self.num_cycles = num_cycles
        self.water_per_cycle = water_per_cycle




    def did_i_water_yesterday(self):
        self.log("Checking if irrigation occurred yesterday")
        
        # Get yesterday's date
        yesterday_date = datetime.datetime.now() - datetime.timedelta(days=1)
        yesterday_start = yesterday_date.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Get the historical state of the sensor for yesterday
        yesterday_water_usage = self.get_state('sensor.greenhouse_water_usage_today', start_time=yesterday_start, end_time=yesterday_end)
        
        # If there's no historical state for yesterday, no irrigation happened
        if not yesterday_water_usage:
            return False
        
        # Get the final value of the sensor from yesterday
        yesterday_final_value = yesterday_water_usage[-1]['state']
        
        # Get the final value of the sensor for today
        today_final_value = self.get_state('sensor.greenhouse_water_usage_today')
        
        # Compare yesterday's final value with today's final value
        return yesterday_final_value != today_final_value

   
    def schedule_watering_cycles(self):
        self.log("Scheduling watering cycles")
        
        scheduled_times = []
        local_tz = pytz.timezone(TIMEZONE)
        
        def to_local_time_and_format(iso_str):
            utc_time = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(pytz.utc)
            local_time = utc_time.astimezone(local_tz)
            return local_time.strftime("%H:%M:%S")
        
        if (sunrise := self.get_state("sun.sun", attribute="next_rising")):
            formatted_sunrise = to_local_time_and_format(sunrise)
            scheduled_times.append(formatted_sunrise)
        
        if self.num_cycles >= 2:
            noon = self.get_state("sun.sun", attribute="next_noon")
            if noon:
                formatted_noon = to_local_time_and_format(noon)
                scheduled_times.append(formatted_noon)
        
        if self.num_cycles == 3:
            sunset = self.get_state("sun.sun", attribute="next_setting")
            if sunset:
                formatted_sunset = to_local_time_and_format(sunset)
                scheduled_times.append(formatted_sunset)

        scheduled_times.sort()

        self.scheduled_times = scheduled_times
        
        return scheduled_times

    def schedule_watering_callbacks(self, scheduled_times):
        self.log("Scheduling watering callbacks")
        if not scheduled_times:
            self.log("No scheduled times found, skipping watering callbacks")
            return
        for scheduled_time in scheduled_times:
            #self.log(f"Scheduling watering at {scheduled_time}")
            self.run_at(self.execute_watering_cycle, scheduled_time, scheduled_time=scheduled_time)

    async def execute_watering_cycle(self, kwargs):
        self.log("Executing watering cycle")

        scheduled_time = kwargs.get('scheduled_time', 'N/A')
        self.log(f"Scheduled time: {scheduled_time}")

        # Turn on the irrigation system
        self.call_service('switch/turn_on', entity_id=IRRIGATION_ACTUATOR)
        self.log("Called service to turn on the irrigation system")

        # Check the state up to 5 times to ensure it's on
        max_checks = 5
        system_started = False  # Flag to track if the system started
        for check in range(max_checks):
            await self.sleep(1)  # Wait 1 second between checks
            current_state = await self.get_state(IRRIGATION_ACTUATOR)
            self.log(f"Check {check + 1}/{max_checks}: Actuator state is '{current_state}'")
            if current_state == 'on':
                system_started = True  # Set flag to True
                break

        if not system_started:  # Check the flag here
            self.log("Failed to start irrigation system, sending notification")
            self.call_service('notify/notify', message='Failed to start irrigation system.')
            self.update_scheduled_time_status(scheduled_time, "missed")
            return

        self.set_state(SCHEDULE_SENSOR, attributes={'last_irrigation': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})
        self.log("Updated last irrigation timestamp")

        sleep_duration = int(self.water_per_cycle / WATER_OUTPUT_RATE * 3600)
        self.log(f"Sleeping for {sleep_duration} seconds")
        await self.sleep(sleep_duration)

        # Turn off the irrigation system
        self.call_service('switch/turn_off', entity_id=IRRIGATION_ACTUATOR)
        self.log("Called service to turn off the irrigation system")

        # Check the state up to 5 times to ensure it's off
        system_stopped = False  # Flag to track if the system stopped
        for check in range(max_checks):
            await self.sleep(1)  # Wait 1 second between checks
            current_state = await self.get_state(IRRIGATION_ACTUATOR)
            self.log(f"Check {check + 1}/{max_checks}: Actuator state is '{current_state}'")
            if current_state == 'off':
                system_stopped = True  # Set flag to True
                break

        if not system_stopped:  # Check the flag here
            self.log("Failed to stop irrigation system, sending notification")
            self.call_service('notify/notify', message='Failed to stop irrigation system.')
            self.update_scheduled_time_status(scheduled_time, "STOP-ERROR")
            return

        # Fetch the history of IRRIGATION_ACTUATOR
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(days=1)  # Adjust as needed
        history = await self.get_history(entity_id=IRRIGATION_ACTUATOR, start_time=start_time, end_time=end_time)

        if history is None or not history:
            self.log("Failed to retrieve history, sending notification")
            self.call_service('notify/notify', message='Failed to retrieve irrigation system history.')
            self.update_scheduled_time_status(scheduled_time, "HISTORY-ERROR")
            return

        # Check if there's an 'on' state followed by an 'off' state in the history
        for i in range(1, len(history[0])):
            if history[0][i - 1]['state'] == 'on' and history[0][i]['state'] == 'off':
                # Calculate the difference in seconds between the timestamps
                time_on_str = history[0][i - 1]['last_changed']
                time_off_str = history[0][i]['last_changed']

                try:
                    time_on = datetime.datetime.strptime(time_on_str, '%Y-%m-%dT%H:%M:%S.%f%z')
                except ValueError:
                    time_on = datetime.datetime.strptime(time_on_str, '%Y-%m-%dT%H:%M:%S%z')

                try:
                    time_off = datetime.datetime.strptime(time_off_str, '%Y-%m-%dT%H:%M:%S.%f%z')
                except ValueError:
                    time_off = datetime.datetime.strptime(time_off_str, '%Y-%m-%dT%H:%M:%S%z')

                runtime = (time_off - time_on).total_seconds()

                # Compare this difference with the expected cycle length
                if abs(runtime - self.water_per_cycle * 60) <= TOLERANCE:
                    # If the difference is within the tolerance, update the scheduled time status to 'cycle finished'
                    self.update_scheduled_time_status(scheduled_time, "verified cycle")
                    break
        else:
            # If there isn't, update the scheduled time status to 'missed'
            self.update_scheduled_time_status(scheduled_time, "unverified historical cycle")

        self.log("Watering cycle complete")


    def irrigation_actuator_state_change(self, entity, attribute, old, new, kwargs):
        self.log(f"Irrigation actuator state change detected: {old} -> {new}")

        if new == 'on':
            self.log("Irrigation system is on")
            current_time = datetime.datetime.now().time()

            if not self.is_time_in_scheduled_range(current_time):
                self.log("Irrigation system is on outside of scheduled times, sending notification")
                self.call_service('notify/notify', message='Irrigation system turned on outside of scheduled times.')
                self.turn_off_irrigation()

    def is_time_in_scheduled_range(self, current_time):
        for scheduled_time_str in self.scheduled_times:
            if scheduled_time_str != "missed":
                scheduled_time = datetime.datetime.strptime(scheduled_time_str, '%H:%M:%S').time()
                if current_time >= scheduled_time:
                    return True
        return False

    async def turn_off_irrigation(self):
        self.log("Attempting to turn off irrigation system")
    
        max_retries = 3
        for attempt in range(max_retries):
            self.call_service('switch/turn_off', entity_id=IRRIGATION_ACTUATOR)
            await self.sleep(5)  # Add await here
            current_state = self.get_state(IRRIGATION_ACTUATOR)
            if current_state == 'off':
                self.log("Irrigation system turned off successfully")
                break
        else:
            self.log("Failed to turn off irrigation system after multiple attempts, sending notification")
            self.call_service('notify/notify', message='Failed to turn off irrigation system after multiple attempts.')

    def set_sensor_state(self):
        current_time = datetime.datetime.now().time()
        scheduled_times = []
        for time in self.scheduled_times:
            if isinstance(time, str):
                scheduled_times.append(time)
            else:
                time_obj = datetime.datetime.strptime(time, '%H:%M:%S').time()
                if time_obj > current_time:
                    scheduled_times.append(time_obj.strftime('%H:%M:%S'))
                else:
                    scheduled_times.append("missed")

        def calculate_next_run_time():
            current_time = datetime.datetime.now().time()
            for time in scheduled_times:
                if time != "missed" and time != "cycle finished":
                    time_obj = datetime.datetime.strptime(time, '%H:%M:%S').time()
                    if time_obj > current_time:
                        return time
            return "N/A"

        attributes = {
            'next_run': calculate_next_run_time(),
            'num_cycles': self.num_cycles,
            'water_per_cycle': self.water_per_cycle,
            'duration_per_cycle': str(datetime.timedelta(hours=self.water_per_cycle / WATER_OUTPUT_RATE))
        }

        for i, scheduled_time in enumerate(scheduled_times, start=1):
            attributes[f'Scheduled cycle {i}/{self.num_cycles}'] = scheduled_time

        self.set_state(SCHEDULE_SENSOR, state="scheduled", attributes=attributes)
        self.log(f"Updated sensor state with: {attributes}")
    
    def update_scheduled_time_status(self, scheduled_time, status):
        self.log(f"Updating scheduled time {scheduled_time} to status: {status}")
        self.scheduled_times = [time if time != scheduled_time else status for time in self.scheduled_times]
        self.set_sensor_state()
