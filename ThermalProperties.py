import hassapi as hass
from datetime import datetime, timedelta, time  # Import time from datetime module

class ThermalPropertiesClass(hass.Hass):

    def initialize(self):
        # Initialize previous temperature and time
        self.previous_temperature = float(self.get_state("sensor.santetorp_rumsgivare_temperature"))
        self.previous_time = datetime.now()

        # Run the function immediately
        self.calculate_thermal_accumulation()

        # Schedule the function to run every hour
        self.run_hourly(self.calculate_thermal_accumulation, time(minute=0, second=0))  # Use time() instead of datetime.time()

    def calculate_thermal_accumulation(self):
        # Fetch the current indoor and outdoor temperatures from the sensors
        current_temperature = float(self.get_state("sensor.santetorp_rumsgivare_temperature"))
        outdoor_temperature = float(self.get_state("sensor.santetorp_rumsgivare_utegivare_temperature"))

        # Get the current thermal mass
        thermal_mass = float(self.get_state("input_number.thermal_mass"))

        # Get the current time rounded down to the nearest full hour
        current_time = datetime.now()
        current_hour = current_time.replace(minute=0, second=0, microsecond=0)

        # Calculate the future hour based on the current hour and the thermal mass
        future_hour_start = (current_hour + timedelta(hours=int(thermal_mass))).strftime("%Y%m%d %H:00")
        future_hour_end = (current_hour + timedelta(hours=int(thermal_mass) + 1)).strftime("%H:00")
        future_hour = future_hour_start + "-" + future_hour_end

        # Fetch the forecast data for the future hour
        weather_forecast = self.get_state("sensor.weatherforecast_hvac", attribute=future_hour)

        # Check if the forecast data exists and contains a feels_like temperature
        if weather_forecast is not None and "feels_like" in weather_forecast:
            future_feels_like_temperature = float(weather_forecast["feels_like"])
        else:
            self.log(f"Attribute {future_hour} does not exist for sensor.weatherforecast_hvac")
            return

        # Calculate the temperature difference between indoor and future feels_like temperature
        temperature_difference = current_temperature - future_feels_like_temperature

        # Calculate the rate of change
        current_time = datetime.now()
        time_interval = (current_time - self.previous_time).total_seconds() / 3600  # in hours
        rate_of_change = (current_temperature - self.previous_temperature) / time_interval  # in °C/hour

        thermal_accumulation = thermal_mass * rate_of_change * time_interval
        new_temperature = current_temperature + thermal_accumulation

        # Adjust the thermal mass based on the observed vs predicted temperature
        error = current_temperature - new_temperature
        thermal_mass += error * 0.1  # Adjust this factor as needed

        # Set the state and attributes of the sensor
        self.set_state("sensor.thermal_properties", state=new_temperature, attributes={
            'indoor_temperature': current_temperature,
            'outdoor_temperature': outdoor_temperature,
            'future_feels_like_temperature': future_feels_like_temperature,
            'temperature_difference': temperature_difference,
            'rate_of_change': rate_of_change,
            'time_interval': time_interval,
            'thermal_mass': thermal_mass,
            'thermal_accumulation': thermal_accumulation
        })

        # Update the thermal mass
        self.call_service("input_number/set_value", entity_id="input_number.thermal_mass", value=thermal_mass)
        # Update previous temperature and time
        self.previous_temperature = current_temperature
        self.previous_time = current_time

        return new_temperature