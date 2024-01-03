def initialize(self):
    # Initialize previous temperature and time
    self.previous_temperature = float(self.get_state("sensor.santetorp_rumsgivare_temperature"))
    self.previous_time = datetime.datetime.now()

    # Run the function immediately
    self.calculate_thermal_accumulation()

    # Schedule the function to run every hour
    self.run_hourly(self.calculate_thermal_accumulation, datetime.time(minute=0, second=0))

def calculate_thermal_accumulation(self):
    # Fetch the current indoor and outdoor temperatures from the sensors
    current_temperature = float(self.get_state("sensor.santetorp_rumsgivare_temperature"))
    outdoor_temperature = float(self.get_state("sensor.outdoor_temperature"))

    # Get the current thermal mass
    thermal_mass = float(self.get_state("input_number.thermal_mass"))

    # Fetch the feels_like temperature for the future hour that matches the thermal mass from the weather forecast sensor
    future_hour = (datetime.datetime.now() + datetime.timedelta(hours=int(thermal_mass))).strftime("%Y%m%d %H:00-%H:59")
    future_feels_like_temperature = float(self.get_state("sensor.weatherforecast_hvac", attribute=future_hour)["feels_like"])

    # Calculate the temperature difference between indoor and future feels_like temperature
    temperature_difference = current_temperature - future_feels_like_temperature

    # Calculate the rate of change
    current_time = datetime.datetime.now()
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
    self.call_service("input_number/set", entity_id="input_number.thermal_mass", value=thermal_mass)

    # Update previous temperature and time
    self.previous_temperature = current_temperature
    self.previous_time = current_time

    return new_temperature