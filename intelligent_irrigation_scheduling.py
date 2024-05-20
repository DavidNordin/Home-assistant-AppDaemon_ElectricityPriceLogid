import appdaemon.plugins.hass.hassapi as hass
import pytz
import datetime

TIMEZONE = 'Europe/Stockholm'
local_tz = pytz.timezone(TIMEZONE)
HIGH_TEMPERATURE_THRESHOLD = 20
LOW_TEMPERATURE_THRESHOLD = 10
WATER_OUTPUT_RATE = 4  # Liters per hour

FORECAST_SENSOR = 'sensor.sensor_greenhouse_intelligent_irrigation_forecasting'
SCHEDULE_SENSOR = 'sensor.sensor_greenhouse_intelligent_irrigation_scheduling'

IRRIGATION_ACTUATOR = 'switch.sonoff_smartrelay_1'

class intelligent_irrigation_scheduling(hass.Hass):

    def initialize(self):
        self.log("Initializing Intelligent Irrigation Scheduler")        
        self.log(f"Timezone: {TIMEZONE}")
        self.accumulated_irrigation = {'daily': 0, 'weekly': 0, 'monthly': 0}
        
        # Schedule daily tasks
        self.run_daily(self.schedule_irrigation, "04:00:00")
        
        # Set up listeners
        self.listen_state(self.on_sensor_change, FORECAST_SENSOR, attribute="all")
        
        # Initial call to setup irrigation
        self.schedule_irrigation(None)
        self.log("Initialization complete")

    def on_sensor_change(self, entity, attribute, old, new, kwargs):
        self.log("Sensor change detected")
        self.schedule_irrigation(None)

    def schedule_irrigation(self, kwargs):
        self.log("Scheduling irrigation check")
        
        sensor_state = self.get_state(FORECAST_SENSOR, attribute="all")
        if sensor_state and "attributes" in sensor_state:
            attributes = sensor_state["attributes"]
            temperature_str = attributes.get("daily_mean_temperature", None)
            
            if temperature_str:
                try:
                    greenhouse_daily_mean_temperature = float(temperature_str[:-2])
                    self.log(f"Daily mean temperature: {greenhouse_daily_mean_temperature}°C")
                    
                    if greenhouse_daily_mean_temperature:
                        self.determine_irrigation_parameters(greenhouse_daily_mean_temperature)
                        scheduled_times = self.schedule_watering_cycles()
                        self.schedule_watering_callbacks(scheduled_times)
                        self.set_sensor_state()
                    else:
                        self.log("Temperature value not found")
                except ValueError as e:
                    self.log(f"Error parsing temperature value: {e}")
            else:
                self.log("Daily mean temperature attribute not found")
        else:
            self.log("Sensor attributes not found")

    def determine_irrigation_parameters(self, greenhouse_daily_mean_temperature):
        self.log("Entered determine_irrigation_parameters")
        
        if greenhouse_daily_mean_temperature < 5:
            self.log("Temperature is below 5°C, no irrigation required")
            num_cycles, water_per_cycle = 0, 0
        elif 5 <= greenhouse_daily_mean_temperature < 10:
            self.log("Temperature is between 5°C and 10°C")
            num_cycles = 1 if self.did_i_water_yesterday() else 0
            water_per_cycle = 2
        elif 10 <= greenhouse_daily_mean_temperature < 15:
            self.log("Temperature is between 10°C and 15°C")
            num_cycles, water_per_cycle = 1, 2
        elif 15 <= greenhouse_daily_mean_temperature < 20:
            self.log("Temperature is between 15°C and 20°C")
            num_cycles, water_per_cycle = 1, 2
        elif 20 <= greenhouse_daily_mean_temperature < 25:
            self.log("Temperature is between 20°C and 25°C")
            num_cycles, water_per_cycle = 2, 1.5
        else:
            self.log("Temperature is above 25°C")
            num_cycles, water_per_cycle = 3, 1

        self.num_cycles = num_cycles
        self.water_per_cycle = water_per_cycle

        self.log(f"Determined irrigation parameters: {num_cycles} cycles, {water_per_cycle} liters per cycle")

    def did_i_water_yesterday(self):
        self.log("Checking if irrigation occurred yesterday")
        
        last_irrigation_timestamp = self.get_state(SCHEDULE_SENSOR, attribute='last_irrigation')
        
        if last_irrigation_timestamp is None or last_irrigation_timestamp == 'N/A':
            return False

        last_irrigation_date = datetime.datetime.strptime(last_irrigation_timestamp, '%Y-%m-%d %H:%M')
        current_date = datetime.datetime.now().date()
        return (current_date - last_irrigation_date.date()).days == 1
   
    def schedule_watering_cycles(self):
        self.log("Scheduling watering cycles")
        
        scheduled_times = []
        local_tz = pytz.timezone(TIMEZONE)
        
        # Helper function to convert ISO datetime strings to local time zone and format to "HH:MM:SS"
        def to_local_time_and_format(iso_str):
            utc_time = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(pytz.utc)
            local_time = utc_time.astimezone(local_tz)
            return local_time.strftime("%H:%M:%S")
        
        # Get the next sunrise time in local timezone
        sunrise = self.get_state("sun.sun", attribute="next_rising")
        if sunrise:
            self.log(f"Next sunrise datetime-format: {sunrise}")
            formatted_sunrise = to_local_time_and_format(sunrise)
            scheduled_times.append(formatted_sunrise)
        
        # Get the next noon time in local timezone if num_cycles >= 2
        if self.num_cycles >= 2:
            noon = self.get_state("sun.sun", attribute="next_noon")
            if noon:
                formatted_noon = to_local_time_and_format(noon)
                scheduled_times.append(formatted_noon)
        
        # Get the next sunset time in local timezone if num_cycles == 3
        if self.num_cycles == 3:
            sunset = self.get_state("sun.sun", attribute="next_setting")
            if sunset:
                formatted_sunset = to_local_time_and_format(sunset)
                scheduled_times.append(formatted_sunset)

        scheduled_times.sort()

        #self.log(f"Scheduled watering cycles at: {scheduled_times}")
        self.scheduled_times = scheduled_times
        
        return scheduled_times



    def schedule_watering_callbacks(self, scheduled_times):
        self.log("Scheduling watering callbacks")
        if not scheduled_times:
            self.log("No scheduled times found, skipping watering callbacks")
            return
        for scheduled_time in scheduled_times:
            self.log(f"Scheduling watering at {scheduled_time}")
            self.run_at(self.execute_watering_cycle, scheduled_time, scheduled_time=scheduled_time)


    def execute_watering_cycle(self, kwargs):
        self.log("Executing watering cycle")

        # Log information about the scheduled callback
        scheduled_time = kwargs.get('scheduled_time', 'N/A')
        self.log(f"Scheduled time: {scheduled_time}")

        # Turn on the irrigation system
        self.call_service('switch/turn_on', entity_id=IRRIGATION_ACTUATOR)
        self.log("Called service to turn on the irrigation system")

        # Check if the irrigation system is on
        if self.get_state(IRRIGATION_ACTUATOR) != 'on':
            self.log("Failed to start irrigation system, sending notification")
            self.call_service('notify/notify', message='Failed to start irrigation system.')
            return

        # Update the timestamp of the last irrigation
        self.set_state(SCHEDULE_SENSOR, attributes={'last_irrigation': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})
        self.log("Updated last irrigation timestamp")

        # Calculate and sleep for the duration of the watering cycle
        sleep_duration = int(self.water_per_cycle / WATER_OUTPUT_RATE * 3600)
        self.log(f"Sleeping for {sleep_duration} seconds")

        # Try to turn off the irrigation system with retries
        max_retries = 3
        for attempt in range(max_retries):
            self.call_service('switch/turn_off', entity_id=IRRIGATION_ACTUATOR)
            self.log(f"Attempt {attempt + 1} to turn off the irrigation system")
            if self.get_state(IRRIGATION_ACTUATOR) == 'off':
                self.log("Irrigation system turned off successfully")
                break
        else:
            self.log("Failed to turn off irrigation system after multiple attempts, sending notification")
            self.call_service('notify/notify', message='Failed to turn off irrigation system after multiple attempts.')

        self.log("Watering cycle complete")


    def set_sensor_state(self):
        # Convert scheduled times strings to datetime objects
        scheduled_times = [datetime.datetime.strptime(time_str, '%H:%M:%S') for time_str in self.scheduled_times]

        def calculate_next_run_time():
            current_time = datetime.datetime.now().time()
            # Find the next run time after the current time
            next_run = None
            for time in scheduled_times:
                if time.time() > current_time:
                    next_run = time
                    break
            # If all scheduled times have passed or there are no scheduled times, set next_run to "N/A"
            if next_run is None:
                return "N/A"
            return next_run.strftime("%H:%M:%S")


        # Set sensor state
        attributes = {
            'next_run': calculate_next_run_time(),
            'num_cycles': self.num_cycles,
            'water_per_cycle': self.water_per_cycle,
            'duration_per_cycle': str(datetime.timedelta(hours=self.water_per_cycle / WATER_OUTPUT_RATE))
        }

        for i, scheduled_time in enumerate(scheduled_times, start=1):
            attributes[f'Scheduled cycle {i}/{self.num_cycles}'] = scheduled_time.strftime('%H:%M')

        self.set_state("sensor.sensor_greenhouse_intelligent_irrigation_scheduling", state="scheduled", attributes=attributes)
        self.log(f"Updated sensor state with: {attributes}")

