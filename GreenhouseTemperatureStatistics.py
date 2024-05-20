import appdaemon.plugins.hass.hassapi as hass
import datetime

class GreenhouseTemperatureStats(hass.Hass):
    
    def initialize(self):
        # Calculate the time until the next minute
        now = datetime.datetime.now()
        seconds_until_next_minute = 60 - now.second
    
        # Calculate the time until the next hour
        minutes_until_next_hour = 60 - now.minute
        seconds_until_next_hour = minutes_until_next_hour * 60
    
        # Schedule the function to update daily values every minute, starting from the next minute
        self.run_in(self.start_update_daily_values, seconds_until_next_minute)
        self.run_in(self.start_update_weekly_highest_lowest_temperatures, seconds_until_next_hour)
        self.run_in(self.start_update_monthly_highest_lowest_temperatures, seconds_until_next_hour)
    
        # Calculate the time until the next half hour
        minutes_until_next_half_hour = 30 - (now.minute % 30)
        seconds_until_next_half_hour = minutes_until_next_half_hour * 60
    
        # Schedule the function to update daily average temperature every 30 minutes, starting from the next half hour
        self.run_in(self.start_update_daily_average_temperature, seconds_until_next_half_hour)
    
        # Schedule the functions to update weekly and monthly average temperatures every hour, starting from the next hour
        self.run_in(self.start_update_weekly_average_temperature, seconds_until_next_hour)
        self.run_in(self.start_update_monthly_average_temperature, seconds_until_next_hour)
    
        # Schedule the functions to reset temperature data and daily values at midnight
        start_time = datetime.time(0, 0, 0)  # Midnight
        self.run_daily(self.reset_temperature_data, start_time)
        self.run_daily(self.reset_daily_values, start_time)
    
    def start_update_daily_values(self, kwargs):
        # Start running the update_daily_values function every minute
        self.run_every(self.update_daily_values, "now", 60)
        
    def start_update_weekly_highest_lowest_temperatures(self, kwargs):
        # Start running the update_weekly_highest_lowest_temperatures function every hour
        self.run_every(self.update_weekly_values, "now", 60 * 60)

    def start_update_monthly_highest_lowest_temperatures(self, kwargs):
        # Start running the update_monthly_highest_lowest_temperatures function every hour
        self.run_every(self.update_monthly_values, "now", 60 * 60)
    
    def start_update_daily_average_temperature(self, kwargs):
        # Start running the update_daily_average_temperature function every 30 minutes
        self.run_every(self.update_daily_average_temperature, "now", 30 * 60)
    
    def start_update_weekly_average_temperature(self, kwargs):
        # Start running the update_weekly_average_temperature function every hour
        self.run_every(self.update_weekly_average_temperature, "now", 60 * 60)
    
    def start_update_monthly_average_temperature(self, kwargs):
        # Start running the update_monthly_average_temperature function every hour
        self.run_every(self.update_monthly_average_temperature, "now", 60 * 60)

    def update_daily_average_temperature(self, kwargs):
        # Get current date and time
        now = datetime.datetime.now()
        date_string = now.strftime("%Y-%m-%d %H:%M")
    
        # Calculate daily average temperature for the current day
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        data = self.get_temperature_data(start_time, now)
        daily_average_temp = round(sum(data) / len(data), 2) if data else None
    
        # Update sensor entity with the calculated average temperature
        self.set_state("sensor.greenhouse_daily_average_temperature", state=daily_average_temp, attributes={"unit_of_measurement": "°C", "Timestamp": date_string})

    def update_weekly_average_temperature(self, kwargs):
        # Get current date and time
        now = datetime.datetime.now()
        week_number = now.strftime("%U")
        date_string = now.strftime("%Y-%m-%d %H:%M")
    
        # Calculate weekly average temperature from the start of the current week
        start_of_week = now - datetime.timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
        temperatures = self.get_temperature_data(start_of_week, now)
        weekly_average_temp = round(sum(temperatures) / len(temperatures), 2) if temperatures else None
    
        # Update sensor entity with the calculated weekly average temperature
        self.set_state("sensor.greenhouse_weekly_average_temperature", state=weekly_average_temp, attributes={"unit_of_measurement": "°C", "Timestamp": f"Week {week_number} {date_string}"})


    def update_monthly_average_temperature(self, kwargs):
        # Get current date and time
        now = datetime.datetime.now()
        month_name = now.strftime("%B")
        date_string = now.strftime("%Y-%m-%d %H:%M")

        # Calculate monthly average temperature for the current month
        start_time = datetime.datetime(now.year, now.month, 1)
        temperatures = self.get_temperature_data(start_time, now)
        monthly_average_temp = round(sum(temperatures) / len(temperatures), 2) if temperatures else None
        
        # Update sensor entity with the calculated monthly average temperature
        self.set_state("sensor.greenhouse_monthly_average_temperature", state=monthly_average_temp, attributes={"unit_of_measurement": "°C", "Timestamp": f"{month_name} {date_string}"})
    
    def update_daily_values(self, kwargs):
        # Get current date and time
        now = datetime.datetime.now()
    
        # Get temperature data for the current day
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        data = self.get_temperature_data(start_time, now)
        temperatures = data
    
        # Update daily lowest and highest temperatures
        self.set_state("sensor.greenhouse_daily_lowest_temperature", state=round(min(temperatures), 2) if temperatures else "n/a", attributes={"unit_of_measurement": "°C"})
        self.set_state("sensor.greenhouse_daily_highest_temperature", state=round(max(temperatures), 2) if temperatures else "n/a", attributes={"unit_of_measurement": "°C"})
    
    def update_weekly_values(self, kwargs):
        # Get current date and time
        now = datetime.datetime.now()
        week_number = now.strftime("%U")
        date_string = now.strftime("%Y-%m-%d %H:%M")

        # Calculate weekly min and max temperatures from the start of the current week
        start_of_week = now - datetime.timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
        temperatures = self.get_temperature_data(start_of_week, now)
        weekly_min_temp = round(min(temperatures), 2) if temperatures else None
        weekly_max_temp = round(max(temperatures), 2) if temperatures else None

        # Update sensor entities with the calculated weekly min and max temperatures
        self.set_state("sensor.greenhouse_weekly_lowest_temperature", state=weekly_min_temp, attributes={"unit_of_measurement": "°C", "Timestamp": f"Week {week_number} {date_string}"})
        self.set_state("sensor.greenhouse_weekly_highest_temperature", state=weekly_max_temp, attributes={"unit_of_measurement": "°C", "Timestamp": f"Week {week_number} {date_string}"})

    def update_monthly_values(self, kwargs):
        # Get current date and time
        now = datetime.datetime.now()
        month_name = now.strftime("%B")
        date_string = now.strftime("%Y-%m-%d %H:%M")

        # Calculate monthly min and max temperatures for the current month
        start_time = datetime.datetime(now.year, now.month, 1)
        temperatures = self.get_temperature_data(start_time, now)
        monthly_min_temp = round(min(temperatures), 2) if temperatures else None
        monthly_max_temp = round(max(temperatures), 2) if temperatures else None

        # Update sensor entities with the calculated monthly min and max temperatures
        self.set_state("sensor.greenhouse_monthly_lowest_temperature", state=monthly_min_temp, attributes={"unit_of_measurement": "°C", "Timestamp": f"{month_name} {date_string}"})
        self.set_state("sensor.greenhouse_monthly_highest_temperature", state=monthly_max_temp, attributes={"unit_of_measurement": "°C", "Timestamp": f"{month_name} {date_string}"})
        
    def reset_daily_values(self, kwargs):
        # Get current date and time
        now = datetime.datetime.now()

        # Get temperature data for the past day
        start_time = now - datetime.timedelta(days=1)
        data = self.get_temperature_data(start_time, now)
        temperatures = [temp for temp, _ in data]

        # Reset daily lowest and highest temperatures at midnight
        self.set_state("sensor.greenhouse_daily_lowest_temperature", state="n/a", attributes={"unit_of_measurement": "°C"})
        self.set_state("sensor.greenhouse_daily_highest_temperature", state="n/a", attributes={"unit_of_measurement": "°C"})
        
    def reset_temperature_data(self, kwargs):
        # Reset temperature data at midnight
        self.temperature_data = []

    def get_temperature_data(self, start_time, end_time):
        try:
            # Get the historical data from the sensor
            history = self.get_history(entity_id='sensor.sensor_i_vaxthuset_temperature', start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values from the history
                data = [float(state['state']) for state in history[0] if state['state'] not in ['unknown', 'unavailable']]
            else:
                data = []
        except Exception as e:
            self.log(f"Error getting temperature data: {e}")
            data = []
            
        return data