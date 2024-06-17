import appdaemon.plugins.hass.hassapi as hass
import pytz
import datetime
import asyncio

TIMEZONE = 'Europe/Stockholm'
local_tz = pytz.timezone(TIMEZONE)

# Define the minimum and maximum values for temperature, cycles, and water
TEMP_MIN, TEMP_MAX = 5, 30
CYCLES_MIN, CYCLES_MAX = 0, 3
WATER_MIN, WATER_MAX = 0, 2  # Adjusted for 1..5L daily need
MAX_WATER_PER_CYCLE = 1.5  # Maximum permitted water per cycle in liters

# Define the temperature below which no irrigation is needed
NO_IRRIGATION_TEMP = 15
        
# Define the maximum number of consecutive days without irrigation
SKIP_LIMIT = 1

MINIMUM_DURATION = 1  # Minimum duration in minutes

TOLERANCE = 300  # Define your tolerance in seconds

WATER_OUTPUT_RATE = 4  # Liters per hour

FORECAST_SENSOR = 'sensor.sensor_greenhouse_intelligent_irrigation_forecasting'
SCHEDULE_SENSOR = 'sensor.sensor_greenhouse_intelligent_irrigation_scheduling'

IRRIGATION_ACTUATOR = 'switch.sonoff_smartrelay_1'

class intelligent_irrigation_scheduling(hass.Hass):

    def initialize(self):
        self.log("Initializing Intelligent Irrigation Scheduler")
        self.WATER_OUTPUT_RATE = WATER_OUTPUT_RATE
        # Initialize skipped_days attribute
        self.skipped_days = 0
        
        # Schedule daily tasks
        #self.run_daily(self.schedule_irrigation, "04:00:00")
        
        # Set up listeners
        self.listen_state(self.on_sensor_change, FORECAST_SENSOR, attribute="all")
        self.listen_state(self.irrigation_actuator_state_change, IRRIGATION_ACTUATOR)
        
        # Initial call to setup irrigation
        self.schedule_irrigation(None)
        
        # Schedule the background safety check
        self.background_task = self.create_task(self.periodic_check())
               
        self.watering_cycle_in_progress = False
        
        self.log("Initialization complete")
        
    async def periodic_check(self):
        while True:
            try:
                await asyncio.sleep(60)  # Wait for 300 seconds
                current_time = datetime.datetime.now().time()
                
                # Await the get_state call
                current_state = await self.get_state(IRRIGATION_ACTUATOR)
                
                if current_state == 'on' and not self.is_time_in_scheduled_range(current_time):
                    self.log("Irrigation system is on outside of scheduled times, sending notification")
                    
                    # Await the service call
                    await self.call_service('notify/notify', message='Irrigation system turned on outside of scheduled times.')
                    
                    # Await the turn off function
                    await self.turn_off_irrigation()
            except Exception as e:
                self.log(f"An error occurred during periodic check: {e}")




    def on_sensor_change(self, entity, attribute, old, new, kwargs):
        self.log("Sensor change detected")
        self.schedule_irrigation(kwargs)


    def clear_old_schedules(self):
        self.log("Clearing old schedules")
        # Ensure that the 'state' key is present in the attributes dictionary
        new_state = {
            'state': 'idle',
            'attributes': {}
        }
        try:
            self.set_state(SCHEDULE_SENSOR, **new_state)
            self.log("Cleared all scheduled times")
        except KeyError as e:
            self.log(f"Error clearing old schedules: {e}")

    
    def schedule_irrigation(self, kwargs):
        self.log("Scheduling irrigation check")

        # Clear old schedules
        self.clear_old_schedules()

        sensor_state = self.get_state(FORECAST_SENSOR, attribute="all")
        if sensor_state and "attributes" in sensor_state:
            temperature_str = sensor_state["attributes"].get("daily_mean_temperature", None)
            if temperature_str:
                try:
                    temperature = float(temperature_str)
                    self.log(f"Daily mean temperature: {temperature}")
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
        if greenhouse_daily_mean_temperature <= NO_IRRIGATION_TEMP:
            if self.skipped_days < SKIP_LIMIT:
                daily_water_need = 0
                self.skipped_days += 1
            else:
                daily_water_need = WATER_MIN
                self.skipped_days = 0
        elif TEMP_MIN <= greenhouse_daily_mean_temperature <= TEMP_MAX:
            daily_water_need = ((greenhouse_daily_mean_temperature - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) * (WATER_MAX - WATER_MIN) + WATER_MIN
            self.skipped_days = 0
        elif greenhouse_daily_mean_temperature < TEMP_MIN:
            daily_water_need = WATER_MIN
            self.skipped_days = 0
        else:
            daily_water_need = WATER_MAX
            self.skipped_days = 0
    
        # Fetch today's irrigation data
        try:
            cycles_today, total_on_time_today, total_liters_irrigated_today = self.get_today_irrigation_data()
        except ValueError as e:
            self.log(f"Error parsing today's irrigation data: {e}")
        
        # Calculate the remaining water need for today
        remaining_water_need = max(0, daily_water_need - total_liters_irrigated_today)
        
        # Fetch yesterday's irrigation data
        try:
            cycles_yesterday, total_on_time_yesterday, total_liters_irrigated_yesterday = self.get_yesterday_irrigation_data()
        except ValueError as e:
            self.log(f"Error parsing yesterday's irrigation data: {e}")
    
        # Calculate the deviation between yesterday's liters irrigated and the calculated daily water need
        deviation = total_liters_irrigated_yesterday - daily_water_need
    
        # Define a reduction factor based on the deviation
        if daily_water_need != 0:
            reduction_factor = 1.0 - (deviation / daily_water_need)
        else:
            reduction_factor = 1.0  # or any other value you consider appropriate
    
        # Ensure the reduction factor is within a reasonable range (e.g., between 0 and 1.0)
        reduction_factor = max(0, min(1.0, reduction_factor))
    
        # Apply the reduction factor to adjust today's daily water need
        daily_water_need *= reduction_factor
    
        # Calculate the number of cycles and water per cycle
        num_cycles = 1
        water_per_cycle = remaining_water_need
    
        # If the water per cycle exceeds MAX_WATER_PER_CYCLE, increase the number of cycles (up to a maximum of three)
        while water_per_cycle > MAX_WATER_PER_CYCLE and num_cycles < 3:
            num_cycles += 1
            water_per_cycle = remaining_water_need / num_cycles
    
        # Round the water per cycle to two decimal places
        water_per_cycle = round(water_per_cycle, 2)
    
        self.log(f"Temperature is {greenhouse_daily_mean_temperature}°C, calculated {num_cycles} cycles and {water_per_cycle}L water per cycle")
    
        self.num_cycles = num_cycles
        self.water_per_cycle = water_per_cycle

    def get_yesterday_irrigation_data(self):
        self.log("Checking if irrigation occurred yesterday")
        
        # Get yesterday's date
        yesterday_date = datetime.datetime.now() - datetime.timedelta(days=1)
        yesterday_start = yesterday_date.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Get the historical state of the irrigation actuator for yesterday
        try:
            history_data = self.get_history(entity_id=IRRIGATION_ACTUATOR, start_time=yesterday_start, end_time=yesterday_end)

        except Exception as e:
            self.log(f"Error retrieving history for yesterday: {e}")
            return False
        
        # Flatten the list of lists into a single list of dictionaries
        history = [item for sublist in history_data for item in sublist]
        
        # If there's no historical state for yesterday, no irrigation happened
        if not history:
            self.log("No irrigation occurred yesterday")
            return False
        
        # Initialize variables to track cycles, on-time, and total liters irrigated
        cycles_yesterday = 0
        total_on_time_yesterday = datetime.timedelta()
        total_liters_irrigated_yesterday = 0
        irrigation_start_time = None

        # Helper function to parse datetime
        def parse_datetime(datetime_str):
            try:
                return datetime.datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                return datetime.datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S%z")
        
        # Iterate through the history to calculate metrics
        for i in range(len(history)):
            current_entry = history[i]
            
            # Check if the entry contains state information and last changed time
            if 'state' in current_entry and 'last_changed' in current_entry:
                current_state = current_entry['state']
                current_time = parse_datetime(current_entry['last_changed'])

                # If the current state is 'on' and the irrigation system was not already on, record the start time
                if current_state == 'on' and irrigation_start_time is None:
                    irrigation_start_time = current_time

                # If the current state is 'off' and the irrigation system was on, calculate the on-time and reset the start time
                elif current_state == 'off' and irrigation_start_time is not None:
                    on_time = current_time - irrigation_start_time
                    total_on_time_yesterday += on_time
                    self.log(f"Irrigation started at {irrigation_start_time.strftime('%H:%M:%S')} and ended at {current_time.strftime('%H:%M:%S')}, duration: {on_time}")
                    total_liters_irrigated_yesterday += on_time.total_seconds() / 3600 * WATER_OUTPUT_RATE
                    cycles_yesterday += 1
                    irrigation_start_time = None
            else:
                self.log("State information or last changed time not found in history data.")

        # Log the calculated metrics
        self.log(f"Total cycles yesterday: {cycles_yesterday}")
        self.log(f"Total on-time yesterday: {total_on_time_yesterday}")
        self.log(f"Total liters irrigated yesterday: {total_liters_irrigated_yesterday}")

        
        return cycles_yesterday, total_on_time_yesterday, total_liters_irrigated_yesterday


    def get_today_irrigation_data(self):
        self.log("Checking if irrigation occurred today")

        # Get the local timezone from the TIMEZONE variable
        local_tz = pytz.timezone(TIMEZONE)

        # Get today's date range in local time
        now = datetime.datetime.now(local_tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now

        # Convert the local time range to UTC
        today_start_utc = today_start.astimezone(pytz.utc).replace(tzinfo=None)
        today_end_utc = today_end.astimezone(pytz.utc).replace(tzinfo=None)

        # Get the historical state of the irrigation actuator for today in UTC
        try:
            history_data = self.get_history(entity_id=IRRIGATION_ACTUATOR, start_time=today_start_utc, end_time=today_end_utc)
            if history_data is None:
                raise ValueError("No history data returned")
        except Exception as e:
            self.log(f"Error retrieving history for today: {e}")
            return 0, datetime.timedelta(), 0

        # Flatten the list of lists into a single list of dictionaries
        history = [item for sublist in history_data for item in sublist]

        # If there's no historical state for today, no irrigation happened
        if not history:
            self.log("No irrigation occurred today")
            return 0, datetime.timedelta(), 0

        # Initialize variables to track cycles, on-time, and total liters irrigated
        cycles_today = 0
        total_on_time_today = datetime.timedelta()
        total_liters_irrigated_today = 0
        irrigation_start_time = None

        # Helper function to parse datetime and convert to local timezone
        def parse_datetime(datetime_str):
            try:
                utc_time = datetime.datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                utc_time = datetime.datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S%z")
            return utc_time.astimezone(local_tz)

        # Iterate through the history to calculate metrics
        for i in range(len(history)):
            current_entry = history[i]

            # Check if the entry contains state information and last changed time
            if 'state' in current_entry and 'last_changed' in current_entry:
                current_state = current_entry['state']
                current_time = parse_datetime(current_entry['last_changed'])

                # If the current state is 'on' and the irrigation system was not already on, record the start time
                if current_state == 'on' and irrigation_start_time is None:
                    irrigation_start_time = current_time

                # If the current state is 'off' and the irrigation system was on, calculate the on-time and reset the start time
                elif current_state == 'off' and irrigation_start_time is not None:
                    on_time = current_time - irrigation_start_time
                    total_on_time_today += on_time
                    self.log(f"Irrigation started at {irrigation_start_time.strftime('%H:%M:%S')} and ended at {current_time.strftime('%H:%M:%S')}, duration: {on_time}")
                    total_liters_irrigated_today += on_time.total_seconds() / 3600 * self.WATER_OUTPUT_RATE
                    cycles_today += 1
                    irrigation_start_time = None
            else:
                self.log("State information or last changed time not found in history data.")

        # Log the calculated metrics
        self.log(f"Total cycles today: {cycles_today}")
        self.log(f"Total on-time today: {total_on_time_today}")
        self.log(f"Total liters irrigated today: {total_liters_irrigated_today}")

        return cycles_today, total_on_time_today, total_liters_irrigated_today

   
    def schedule_watering_cycles(self):
        self.log("Scheduling watering cycles")

        scheduled_times = []

        def to_local_time_and_format(iso_str):
            utc_time = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(pytz.utc)
            local_time = utc_time.astimezone(local_tz)
            return local_time

        # Get the current time in the local timezone
        current_time = datetime.datetime.now(local_tz)

        # Check if any irrigation events were missed today
        cycles_today, total_on_time_today, total_liters_today = self.get_today_irrigation_data()

        # Print out the value of cycles_today
        self.log(f"Number of cycles today: {cycles_today}")

        # Define the timeframes to check for scheduling
        timeframes = [('sunrise', 'next_rising'), ('noon', 'next_noon'), ('sunset', 'next_setting')]
        nearest_time_difference = None
        nearest_time = None

        for timeframe, attribute in timeframes:
            if (time := self.get_state("sun.sun", attribute=attribute)):
                local_time = to_local_time_and_format(time)
                time_difference = local_time - current_time
                # If the current time is before the scheduled time and either nearest time is not set or
                # the new scheduled time is closer to the current time, set it as the next scheduled time
                if time_difference.total_seconds() > 0 and (nearest_time is None or time_difference < nearest_time_difference):
                    nearest_time_difference = time_difference
                    nearest_time = local_time

        # If nearest_time is set, add it to the scheduled times
        if nearest_time:
            scheduled_times.append(nearest_time.strftime("%H:%M:%S"))
        else:
            # If all timeframes are passed or no scheduled time was set, mark it as N/A
            scheduled_times.append("N/A")

        self.scheduled_times = scheduled_times
        self.log(f"Scheduled watering times: {scheduled_times}")

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
        if self.watering_cycle_in_progress:
            self.log("A watering cycle is already in progress. Exiting.")
            return
    
        # Convert 'HH:MM:SS' to minutes
        def convert_to_minutes(time_str):
            t = datetime.datetime.strptime(time_str, "%H:%M:%S")
            return t.hour*60 + t.minute + t.second/60

        # Calculate duration_per_cycle
        duration_per_cycle = str(datetime.timedelta(hours=self.water_per_cycle / WATER_OUTPUT_RATE))

        # Check if the scheduled duration is too short
        duration_in_minutes = convert_to_minutes(duration_per_cycle)
        if duration_in_minutes < MINIMUM_DURATION:
            self.log("Scheduled duration is too short. Exiting.")
            return

        self.watering_cycle_in_progress = True
        try:
            self.log("Executing watering cycle")

            scheduled_time = kwargs.get('scheduled_time', 'N/A')
            self.log(f"Scheduled time: {scheduled_time}")

            # Turn on the irrigation system
            await self.call_service('switch/turn_on', entity_id=IRRIGATION_ACTUATOR)
            self.log("Called service to turn on the irrigation system")

            # Check the state up to 5 times to ensure it's on
            max_checks = 5
            system_started = False
            for check in range(max_checks):
                await self.sleep(1)
                current_state = await self.get_state(IRRIGATION_ACTUATOR)
                self.log(f"Check {check + 1}/{max_checks}: Actuator state is '{current_state}'")
                if current_state == 'on':
                    system_started = True
                    break

            if not system_started:
                self.log("Failed to start irrigation system, sending notification")
                await self.call_service('notify/notify', message='Failed to start irrigation system.')
                self.update_scheduled_time_status(scheduled_time, "missed")
                return

            self.set_state(SCHEDULE_SENSOR, attributes={'last_irrigation': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})
            self.log("Updated last irrigation timestamp")

            sleep_duration = int(self.water_per_cycle / WATER_OUTPUT_RATE * 3600)
            self.log(f"Sleeping for {sleep_duration} seconds")
            await self.sleep(sleep_duration)

            # Turn off the irrigation system
            await self.call_service('switch/turn_off', entity_id=IRRIGATION_ACTUATOR)
            self.log("Called service to turn off the irrigation system")

            # Check the state up to 5 times to ensure it's off
            system_stopped = False
            for check in range(max_checks):
                await self.sleep(1)
                current_state = await self.get_state(IRRIGATION_ACTUATOR)
                self.log(f"Check {check + 1}/{max_checks}: Actuator state is '{current_state}'")
                if current_state == 'off':
                    system_stopped = True
                    break

            if not system_stopped:
                self.log("Failed to stop irrigation system, sending notification")
                await self.call_service('notify/notify', message='Failed to stop irrigation system.')
                self.update_scheduled_time_status(scheduled_time, "STOP-ERROR")
                return

            # Fetch the history of IRRIGATION_ACTUATOR
            try:
                # Fetch the history of IRRIGATION_ACTUATOR
                end_time = datetime.datetime.now(tz=pytz.utc).replace(tzinfo=None)
                start_time = (end_time - datetime.timedelta(days=1)).replace(tzinfo=None)

                history = await self.get_history(entity_id=IRRIGATION_ACTUATOR, start_time=start_time, end_time=end_time)

                if not history:
                    self.log("Failed to retrieve history, sending notification")
                    await self.call_service('notify/notify', message='Failed to retrieve irrigation system history.')
                    self.update_scheduled_time_status(scheduled_time, "HISTORY-ERROR")
                    return

                # Check if there's an 'on' state followed by an 'off' state in the history
                verified_cycle = False
                for state_list in history:
                    for i in range(1, len(state_list)):
                        if state_list[i - 1]['state'] == 'on' and state_list[i]['state'] == 'off':
                            time_on = datetime.datetime.fromisoformat(state_list[i - 1]['last_changed'].replace("Z", "+00:00"))
                            time_off = datetime.datetime.fromisoformat(state_list[i]['last_changed'].replace("Z", "+00:00"))
                            runtime = (time_off - time_on).total_seconds()

                            # Compare this difference with the expected cycle length
                            if abs(runtime - self.water_per_cycle * 60) <= TOLERANCE:
                                # If the difference is within the tolerance, update the scheduled time status to 'cycle finished'
                                self.update_scheduled_time_status(datetime.datetime.now().strftime('%H:%M:%S'), "verified cycle")
                                verified_cycle = True
                                break
                    if verified_cycle:
                        break
                else:
                    # If there isn't, update the scheduled time status to 'missed'
                    self.update_scheduled_time_status(scheduled_time, "unverified historical cycle")
            except Exception as e:
                self.log(f"An error occurred while processing history: {e}")
                self.update_scheduled_time_status(scheduled_time, "HISTORY-ERROR")

            self.log("Watering cycle complete")

        finally:
            self.watering_cycle_in_progress = False



    async def irrigation_actuator_state_change(self, entity, attribute, old, new, kwargs):
        self.log(f"Irrigation actuator state change detected: {old} -> {new}")

        if new == 'on':
            self.log("Irrigation system is on")
            current_time = datetime.datetime.now().time()

            if not self.is_time_in_scheduled_range(current_time):
                self.log("Irrigation system is on outside of scheduled times, sending notification")
                self.call_service('notify/notify', message='Irrigation system turned on outside of scheduled times.')
                await self.turn_off_irrigation()



    def is_time_in_scheduled_range(self, current_time):
        self.log(f"Checking if {current_time} is in any scheduled range")
        for scheduled_time_str in self.scheduled_times:
            self.log(f"Checking scheduled time entry: {scheduled_time_str}")
            if scheduled_time_str != "missed":
                scheduled_time = datetime.datetime.strptime(scheduled_time_str, '%H:%M:%S').time()
                scheduled_time_dt = datetime.datetime.combine(datetime.date.today(), scheduled_time)
                
                # Calculate the end time based on the cycle length
                cycle_length_seconds = self.water_per_cycle / WATER_OUTPUT_RATE * 3600
                cycle_length = datetime.timedelta(seconds=cycle_length_seconds)
                end_time_dt = scheduled_time_dt + cycle_length
                start_time = scheduled_time_dt.time()
                end_time = end_time_dt.time()
                
                self.log(f"Time range: {start_time} - {end_time} (Cycle length: {cycle_length}, Start time DT: {scheduled_time_dt}, End time DT: {end_time_dt})")
                
                # Handle the case where the cycle might span midnight
                if start_time <= end_time:
                    # Case 1: Same day range
                    if start_time <= current_time <= end_time:
                        self.log(f"{current_time} is within range {start_time} - {end_time}")
                        return True
                else:
                    # Case 2: Span across midnight
                    if current_time >= start_time or current_time <= end_time:
                        self.log(f"{current_time} is within range {start_time} - {end_time} spanning midnight")
                        return True
        self.log(f"{current_time} is not in any scheduled range")
        return False


    async def turn_off_irrigation(self):
        self.log("Attempting to turn off irrigation system")

        max_retries = 5
        for attempt in range(max_retries):
            await self.call_service('switch/turn_off', entity_id=IRRIGATION_ACTUATOR)  
            self.log(f"Called service to turn off the irrigation system, attempt {attempt + 1}")

            # Add a delay to allow the state to update
            await self.sleep(5)  # Adjust the delay time as needed

            current_state = self.get_state(IRRIGATION_ACTUATOR)
            self.log(f"Attempt {attempt + 1}/{max_retries}: Actuator state is '{current_state}'")

            if current_state == 'off':
                self.log("Irrigation system turned off successfully")
                return

        self.log("Failed to turn off irrigation system after multiple attempts, sending notification")
        await self.call_service('notify/notify', message='Failed to turn off irrigation system after multiple attempts.')




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
                    try:
                        time_obj = datetime.datetime.strptime(time, '%H:%M:%S').time()
                        if time_obj > current_time:
                            return time
                    except ValueError:
                        continue
            return "N/A"

        attributes = {
            'next_run': calculate_next_run_time(),
            'num_cycles': self.num_cycles,
            'water_per_cycle': self.water_per_cycle,
            'duration_per_cycle': str(datetime.timedelta(hours=self.water_per_cycle / WATER_OUTPUT_RATE))
        }

        for i, scheduled_time in enumerate(scheduled_times, start=1):
            attributes[f'Scheduled cycle {i}/{self.num_cycles}'] = scheduled_time

        # Ensure that the 'state' key is present in the attributes dictionary
        new_state = {
            'state': "scheduled",
            'attributes': attributes
        }

        # Set the state with the updated new_state dictionary
        try:
            self.set_state(SCHEDULE_SENSOR, **new_state)
            self.log(f"Updated sensor state with: {attributes}")
        except KeyError as e:
            self.log(f"Error setting sensor state: {e}")

    def update_scheduled_time_status(self, scheduled_time, status):
        self.log(f"Updating scheduled time {scheduled_time} to status: {status}")
        if not hasattr(self, 'scheduled_time_statuses'):
            self.scheduled_time_statuses = {}
        self.scheduled_time_statuses[scheduled_time] = status
        self.set_sensor_state()
