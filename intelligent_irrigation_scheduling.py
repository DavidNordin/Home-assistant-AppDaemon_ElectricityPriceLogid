import appdaemon.plugins.hass.hassapi as hass
import datetime
from dateutil.parser import parse
import numpy as np
import pandas as pd
import inspect

BASE_QUOTA = 1  # Liters
HIGH_TEMPERATURE_THRESHOLD = 30
LOW_TEMPERATURE_THRESHOLD = 10
IRRIGATION_INTERVAL = datetime.timedelta(hours=8)
WATER_OUTPUT_RATE = 4  # Liters per hour
SOIL_TYPE = 1.2
GROWTH_STAGE = 1.5
OUTSIDE_TEMPERATURE_SENSOR = 'sensor.santetorp_rumsgivare_utegivare_temperature'
GREENHOUSE_TEMPERATURE_SENSOR = 'sensor.sensor_i_vaxthuset_temperature'
GREENHOUSE_HUMIDITY_SENSOR = 'sensor.sensor_i_vaxthuset_humidity'

class intelligent_irrigation_scheduling(hass.Hass):


    def initialize(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.log("Initializing Irrigation Scheduler")
        
        self.listen_event(self.log_irrigation_event, "irrigation_event")
        self.run_daily(self.schedule_irrigation, datetime.time(4, 0, 0))  # Run this function daily at 04:00
        # Schedule the reset methods to run at the appropriate times
        self.run_daily(self.reset_accumulated_irrigation_daily, datetime.time(0, 0, 0))  # Reset daily accumulation at midnight
        self.run_daily(self.reset_accumulated_irrigation_weekly, datetime.time(0, 0, 0))  # Check for weekly reset at midnight
        self.run_daily(self.reset_accumulated_irrigation_monthly, datetime.time(0, 0, 0))  # Check for monthly reset at midnight
        # Call schedule_irrigation to start the irrigation scheduling process immediately
        self.listen_event(self.on_sensor_attributes_changed, "attributes_changed", entity_id="sensor.sensor_greenhouse_intelligent_irrigation_forecasting")
        self.schedule_irrigation(None)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        
    def reset_accumulated_irrigation_daily(self, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.accumulated_irrigation_daily = 0
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def reset_accumulated_irrigation_weekly(self, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # If today is the start of the week (e.g., Sunday)
        if datetime.datetime.today().weekday() == 6:
            self.accumulated_irrigation_weekly = 0
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def reset_accumulated_irrigation_monthly(self, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # If today is the first day of the month
        if datetime.datetime.today().day == 1:
            self.accumulated_irrigation_monthly = 0
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")


#Event handlers section start
    def on_sensor_change(self, entity, attribute, old, new, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        greenhouse_daily_mean_temperature = new['attributes']['daily_mean_temperature']
        greenhouse_daily_mean_temperature = float(greenhouse_daily_mean_temperature.replace('°C', ''))  # convert string to float
        self.determine_irrigation_parameters(greenhouse_daily_mean_temperature)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def log_irrigation_event(self, event_name, data, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        water_amount = data.get("water_amount", "N/A")
        duration = data.get("duration", "N/A")
        self.log(f"Irrigation event - Water amount: {water_amount} liters, Duration: {duration}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
#Event handlers section end

#Irrigation scheduling start
    def schedule_irrigation(self, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Check if irrigation is needed
        if self.is_irrigation_needed():
            self.log("Scheduling irrigation")
            num_cycles, duration = self.determine_irrigation_parameters()
            time_until_run, scheduled_times = self.schedule_watering_cycles(num_cycles, duration)
            self.did_i_water_yesterday()
            self.get_current_duration()
            # Now that all necessary methods have been called and all necessary variables have been defined,
            # we can safely call set_sensor_state

            # Fetch the current attributes of the sensor
            sensor_attributes = self.get_state("sensor.sensor_greenhouse_intelligent_irrigation_forecasting", attribute="all")
            if sensor_attributes and "attributes" in sensor_attributes:
                attributes = sensor_attributes["attributes"]
                # Extract daily mean temperature from sensor attributes
                temperature_str = attributes.get("daily_mean_temperature", None)
                if temperature_str:
                    try:
                        # Clean the temperature string to remove non-numeric characters
                        temperature_str_cleaned = ''.join(filter(str.isdigit, temperature_str))
                        # Convert the cleaned temperature string to a float
                        temperature_value = float(temperature_str_cleaned) / 100  # Assuming the temperature is in Celsius
                        # Use the temperature value for determining irrigation parameters
                        num_cycles, water_per_cycle = self.determine_irrigation_parameters(temperature_value)

                        # Define self.num_cycles
                        self.num_cycles = num_cycles

                        water_amount = num_cycles * water_per_cycle
                        runtime_hours = water_per_cycle / WATER_OUTPUT_RATE
                        duration = datetime.timedelta(hours=runtime_hours)

                        # Call set_sensor_state with predicted_temperature argument
                        # Assuming current_cycle starts from 1
                        self.current_cycle = 1  # Set current cycle
                        self.set_sensor_state(duration, self.current_cycle, num_cycles)

                        # Fire event
                        self.fire_event("irrigation_started")
                    except ValueError as e:
                        self.log(f"Error parsing temperature value: {e}")
                else:
                    self.log("Daily mean temperature attribute not found")
            else:
                self.log("Sensor attributes not found")
        else:
            self.log("Irrigation not needed")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def is_irrigation_needed(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Retrieve the timestamp of the last irrigation from a state or attribute
        last_irrigation_timestamp = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation_scheduling', attribute='last_irrigation')

        # If the timestamp is None or 'N/A', then irrigation is needed
        if last_irrigation_timestamp is None or last_irrigation_timestamp == 'N/A':
            return True

        # Convert the timestamp to a datetime object
        last_irrigation_date = datetime.datetime.strptime(last_irrigation_timestamp, '%Y-%m-%d %H:%M')

        # Get the current date and time
        current_date = datetime.datetime.now()

        # Check if the last irrigation occurred today
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        return last_irrigation_date.date() < current_date.date()


    def determine_irrigation_parameters(self, greenhouse_daily_mean_temperature):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        # If the mean temperature is less than 5 degrees, no irrigation is needed
        if greenhouse_daily_mean_temperature < 5:
            return 0, 0

        # If the mean temperature is between 5 and 10 degrees (inclusive)
        # Check if irrigation was done yesterday
        # If irrigation was done yesterday, no cycles are scheduled for today
        # If irrigation was not done yesterday, schedule 1 cycle today
        # Each cycle will use 2 units of water
        elif 5 <= greenhouse_daily_mean_temperature < 10:
            return 1 if self.did_water_yesterday() else 0, 2
        
        # If the mean temperature is between 10 and 20 degrees (inclusive)
        # Schedule 1 cycle with 2 units of water
        elif 10 <= greenhouse_daily_mean_temperature < 20:
            return 1, 2
        
        # If the mean temperature is between 20 and 25 degrees (inclusive)
        # Schedule 1 cycle with 2 units of water
        elif 20 <= greenhouse_daily_mean_temperature < 25:
            return 1, 2
        
        # If the mean temperature is between 25 and 30 degrees (inclusive)
        # Schedule 2 cycles with 1.5 units of water each
        elif 25 <= greenhouse_daily_mean_temperature < 30:
            return 2, 1.5
        
        # If the mean temperature is greater than or equal to 35 degrees
        # Schedule 3 cycles with 1 unit of water each
        else:  # greenhouse_daily_mean_temperature >= 35
            self.log(f"Entered {inspect.currentframe().f_code.co_name}")
            return 3, 1

#Irrigation scheduling end

#Utility methods start

    def start_irrigation(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Turn on the irrigation system
        self.call_service('switch/turn_on', entity_id='switch.sonoff_smartrelay_1')

        # Check if the irrigation system is on
        if self.get_state('switch.sonoff_smartrelay_1') != 'on':
            self.call_service('notify/notify', message='Failed to start irrigation system.')
            return

        # Update the timestamp of the last irrigation
        self.set_state('sensor.sensor_greenhouse_intelligent_irrigation_scheduling', attribute='last_irrigation', value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        
        # Define the water output rate of your irrigation system (in liters per hour)
        water_output_rate = 4

        # Get the duration of the last irrigation (in hours)
        # If the duration is not already in hours, convert it
        last_irrigation_duration = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation_scheduling', attribute='last_irrigation_duration') / 3600  # Convert from seconds to hours

        # Calculate the amount of water used in the last irrigation
        last_irrigation_amount = water_output_rate * last_irrigation_duration
        
        #Calculate the accumulated irrigation per day
        self.accumulated_irrigation_daily += last_irrigation_amount
        
        #Calculate the accumulated irrigation per week
        self.accumulated_irrigation_weekly += last_irrigation_amount
        
        #Calculate the accumulated irrigation per month
        self.accumulated_irrigation_monthly += last_irrigation_amount
        
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def schedule_watering_cycles(self, num_cycles, duration):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # If num_cycles is not a number (int or float), set it to 0
        if not isinstance(num_cycles, (int, float)) or num_cycles not in [1, 2, 3]:
            num_cycles = 0

        self.current_cycle = 1
        scheduled_times = []  # Initialize the list of scheduled times
        now = datetime.datetime.now()

        delays = []
        time_until_run = 0  # Initialize time_until_run to 0

        if num_cycles >= 1:
            next_morning = self.calculate_seconds_until_morning()
            delay_morning = (next_morning - now).total_seconds()
            delays.append(delay_morning)
            scheduled_times.append(next_morning.strftime('%H:%M:%S'))
            self.run_in(self.start_irrigation, delay_morning, cycle=f"{self.current_cycle}/{num_cycles}")
        if num_cycles >= 2:
            next_evening = self.calculate_seconds_until_evening()
            delay_evening = (next_evening - now).total_seconds()
            delays.append(delay_evening)
            self.current_cycle += 1
            scheduled_times.append(next_evening.strftime('%H:%M:%S'))
            self.run_in(self.start_irrigation, delay_evening, cycle=f"{self.current_cycle}/{num_cycles}")
        if num_cycles == 3:
            next_afternoon = self.calculate_seconds_until_afternoon()
            delay_afternoon = (next_afternoon - now).total_seconds()
            delays.append(delay_afternoon)
            self.current_cycle += 1
            scheduled_times.append(next_afternoon.strftime('%H:%M:%S'))
            self.run_in(self.start_irrigation, delay_afternoon, cycle=f"{self.current_cycle}/{num_cycles}")

        # Update time_until_run based on delays if delays exist
        if delays:
            time_until_run = min(delays) / 60

        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return time_until_run, scheduled_times   
  
    
    def calculate_seconds_until_morning(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        now = datetime.datetime.now()
        next_morning = datetime.datetime(now.year, now.month, now.day, 6, 0)  # 6 AM
        if now > next_morning:
            next_morning += datetime.timedelta(days=1)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return next_morning
        
    
    def calculate_seconds_until_afternoon(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        now = datetime.datetime.now()
        next_afternoon = datetime.datetime(now.year, now.month, now.day, 14, 0)  # 2 PM
        if now > next_afternoon:
            next_afternoon += datetime.timedelta(days=1)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return next_afternoon
        
    
    def calculate_seconds_until_evening(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        now = datetime.datetime.now()
        next_evening = datetime.datetime(now.year, now.month, now.day, 18, 0)  # 6 PM
        if now > next_evening:
            next_evening += datetime.timedelta(days=1)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return next_evening

    def did_water_yesterday(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Retrieve the timestamp of the last irrigation from a state or attribute
        last_irrigation_timestamp = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation_scheduling', attribute='last_irrigation')

        # If the timestamp is None or 'N/A', then irrigation has never occurred
        if last_irrigation_timestamp is None or last_irrigation_timestamp == 'N/A':
            return False

        # Convert the timestamp to a datetime object
        last_irrigation_date = datetime.datetime.strptime(last_irrigation_timestamp, '%Y-%m-%d %H:%M')

        # Get the current date
        current_date = datetime.datetime.now().date()

        # Check if the last irrigation occurred yesterday
        return (current_date - last_irrigation_date.date()).days == 1
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
#Utility methods end


    def handle_irrigation_state_change(self, entity, attribute, old, new, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        if old == "pending" and new == "running":
            self.fire_event("irrigation_started")
        elif old == "running" and new == "none":
            self.fire_event("irrigation_completed")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
  
    def get_current_duration(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Check if self.greenhouse_temperature is set
        if not hasattr(self, 'greenhouse_temperature'):
            # If not, raise an exception (or return a default value)
            return "00:00:00"
    
        # Determine the number of watering cycles and the amount of water per cycle based on the ambient temperature
        num_cycles, water_per_cycle = self.determine_irrigation_parameters(self.greenhouse_daily_mean_temperature)
        
        # Define self.num_cycles
        self.num_cycles = num_cycles
    
        # Define the water output rate of your irrigation system (in liters per hour)
        water_output_rate = 4  # Adjust this value based on your irrigation system
    
        # Calculate the duration of the current cycle (in hours)
        current_cycle_duration_hours = water_per_cycle / water_output_rate
    
        # Convert the duration from hours to a time string in the format 'HH:MM:SS'
        current_cycle_duration_seconds = int(current_cycle_duration_hours * 3600)
        current_cycle_duration_str = str(datetime.timedelta(seconds=current_cycle_duration_seconds))

        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return current_cycle_duration_str

#Attribute change event handler
    def on_sensor_attributes_changed(self, event_name, data, kwargs):
        self.log("Sensor attributes changed")
        new_attributes = data.get("new_state", {}).get("attributes", {})
        if 'daily_mean_temperature' in new_attributes:
            temperature_str = new_attributes['daily_mean_temperature']
            temperature_value = float(temperature_str.split(':')[1].strip().replace('°C', ''))
            self.greenhouse_daily_mean_temperature = temperature_value
            self.log(f"Greenhouse daily mean temperature: {self.greenhouse_daily_mean_temperature}")
        else:
            self.log("Daily mean temperature attribute not found")
   
#State management section start

    def set_sensor_state(self, duration, current_cycle, num_cycles, predicted_temperature=None):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        total_cycles = num_cycles

        # If the irrigation is not scheduled to run today
        if current_cycle > total_cycles or total_cycles == 0:
            next_running_cycle = "Tomorrow"
            cycle_no = "0/0"
            current_cycle_length = "N/A"
            time_until_run = "N/A"
            next_running_cycle_time = "N/A"
        else:
            # Calculate the next running cycle
            next_running_cycle = current_cycle + 1
            
            # Convert duration to a string in the format 'HH:MM:SS'
            duration_str = str(duration)
            
            cycle_no = f"{self.current_cycle}/{total_cycles}"
            current_cycle_length = duration_str
            time_left = duration_str
            
            # Convert time_until_run to a timedelta
            time_until_run_timedelta = datetime.timedelta(seconds=time_until_run)
            
            # Format the timedelta as HH:MM:SS
            time_until_run = str(time_until_run_timedelta)

        # Convert duration to a string in the format 'HH:MM:SS'
        duration_str = str(duration)
                
        # Extract hours, minutes, and seconds from the duration string
        duration_parts = duration_str.split(':')
        duration_hours = int(duration_parts[0]) + int(duration_parts[1]) / 60 + int(duration_parts[2]) / 3600

        # Handle the case where duration is a string in the format 'HH:MM:SS'
        last_irrigation_duration_str = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation_scheduling', attribute='current_cycle_length')
        if last_irrigation_duration_str is None:
            last_irrigation_duration = 0
        else:
            # Parse the duration string and calculate the total number of hours
            last_irrigation_duration = sum(float(x) * 60 ** i for i, x in enumerate(reversed(last_irrigation_duration_str.split(':')))) / 3600

        water_output_rate = 4  # Liters per hour
        last_irrigation_amount = water_output_rate * last_irrigation_duration
        if last_irrigation_amount is None:
            last_irrigation_amount = "N/A"
        else:
            last_irrigation_amount = f"{last_irrigation_amount} L"
        last_irrigation = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation_scheduling', attribute='last_irrigation')
        if last_irrigation is None:
            last_irrigation = "N/A"
        last_updated = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        did_water_yesterday = 'YES' if self.did_water_yesterday() else 'NO'
        time_until_run, scheduled_times = self.schedule_watering_cycles(num_cycles, duration)
        if time_until_run is None:
            time_until_run = "N/A"
        if not scheduled_times:
            scheduled_times = ["N/A"]
            
        self.set_state('sensor.sensor_greenhouse_intelligent_irrigation_scheduling', state='ON', attributes={
            'planned_irrigation': scheduled_times,
            'next_running_cycle(s) #': f"{next_running_cycle} ({next_running_cycle_time})",
            'cycle_no': f"{self.current_cycle}/{total_cycles}",
            'current_cycle_length': duration_str,
            'last_updated': last_updated,
            'last_irrigation': last_irrigation,
            'last_irrigation_amount': last_irrigation_amount,
            'accumulated_irrigation': self.accumulated_irrigation_daily,
            'accumulated_irrigation_weekly': self.accumulated_irrigation_weekly,
            'accumulated_irrigation_monthly': self.accumulated_irrigation_monthly,
            'did_water_yesterday': did_water_yesterday
        })
        
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
