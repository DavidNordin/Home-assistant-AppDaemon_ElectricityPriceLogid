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

    # Calculate the temperature difference between indoor and outdoor
    temperature_difference = current_temperature - outdoor_temperature

    # Calculate the rate of change
    current_time = datetime.datetime.now()
    time_interval = (current_time - self.previous_time).total_seconds() / 3600  # in hours
    rate_of_change = (current_temperature - self.previous_temperature) / time_interval  # in °C/hour

    # Assume a thermal mass for now
    thermal_mass = 1  # This should be replaced with a more accurate value

    thermal_accumulation = thermal_mass * rate_of_change * time_interval
    new_temperature = current_temperature + thermal_accumulation

    # Set the state and attributes of the sensor
    self.set_state("sensor.thermal_properties", state=new_temperature, attributes={
        'indoor_temperature': current_temperature,
        'outdoor_temperature': outdoor_temperature,
        'temperature_difference': temperature_difference,
        'rate_of_change': rate_of_change,
        'time_interval': time_interval,
        'thermal_mass': thermal_mass,
        'thermal_accumulation': thermal_accumulation
    })

    # Update previous temperature and time
    self.previous_temperature = current_temperature
    self.previous_time = current_time

    return new_temperature