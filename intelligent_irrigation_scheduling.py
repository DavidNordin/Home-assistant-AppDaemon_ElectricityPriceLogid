import appdaemon.plugins.hass.hassapi as hass
import pytz
import datetime
import asyncio

TIMEZONE = 'Europe/Stockholm'
local_tz = pytz.timezone(TIMEZONE)

# Define the minimum and maximum values for temperature, cycles, and water
TEMP_MIN, TEMP_MAX = 5, 25
CYCLES_MIN, CYCLES_MAX = 0, 3
WATER_MIN, WATER_MAX = 0, 1.5
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

    def schedule_irrigation(self, kwargs):
        self.log("Scheduling irrigation check")
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
        CYCLES_SCALE = (CYCLES_MAX - CYCLES_MIN) / (TEMP_MAX - TEMP_MIN)
        WATER_SCALE = (WATER_MAX - WATER_MIN) / (TEMP_MAX - TEMP_MIN)

        # Calculate the number of cycles and water per cycle based on the temperature
        num_cycles = max(min(int((greenhouse_daily_mean_temperature - TEMP_MIN) * CYCLES_SCALE + CYCLES_MIN), CYCLES_MAX), CYCLES_MIN)
        water_per_cycle = max(min((greenhouse_daily_mean_temperature - TEMP_MIN) * WATER_SCALE + WATER_MIN, WATER_MAX), WATER_MIN)

        self.log(f"Temperature is {greenhouse_daily_mean_temperature}°C, calculated {num_cycles} cycles and {water_per_cycle} water per cycle")

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

        self.call_service('switch/turn_on', entity_id=IRRIGATION_ACTUATOR)
        self.log("Called service to turn on the irrigation system")

        # Check the state up to 5 times
        max_checks = 5
        system_started = False  # Flag to track if the system started
        for check in range(max_checks):
            await self.sleep(1)  # Wait 1 second between checks
            current_state = self.get_state(IRRIGATION_ACTUATOR)
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

        max_retries = 5
        for attempt in range(max_retries):
            self.call_service('switch/turn_off', entity_id=IRRIGATION_ACTUATOR)
            self.log(f"Attempt {attempt + 1} to turn off the irrigation system")
            await self.sleep(5)
            current_state = self.get_state(IRRIGATION_ACTUATOR)
            self.log(f"Check {attempt + 1}/{max_retries}: Actuator state is '{current_state}'")
            if current_state == 'off':
                self.log("Irrigation system turned off successfully")
                self.update_scheduled_time_status(scheduled_time, "cycle finished")
                break
        else:
            self.log("Failed to turn off irrigation system after multiple attempts, sending notification")
            self.call_service('notify/notify', message='Failed to turn off irrigation system after multiple attempts.')
            self.update_scheduled_time_status(scheduled_time, "missed")

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

    def turn_off_irrigation(self):
        self.log("Attempting to turn off irrigation system")

        max_retries = 3
        for attempt in range(max_retries):
            self.call_service('switch/turn_off', entity_id=IRRIGATION_ACTUATOR)
            self.sleep(5)
            if self.get_state(IRRIGATION_ACTUATOR) == 'off':
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
