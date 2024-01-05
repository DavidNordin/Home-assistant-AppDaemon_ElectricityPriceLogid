import hassapi as hass
from datetime import datetime, timedelta

THERMAL_ADJUSTMENT_FACTOR = 0.1
RESPONSIVENESS_FACTOR = 0.01  # Adjust this based on your preferences
RATE_CHANGE_THRESHOLD = 0.5  # Adjust this based on your system's behavior
RATE_CHANGE_FACTOR = 0.01  # Adjust this based on your preferences
MIN_RESPONSIVENESS = 0.005  # Minimum value for responsiveness factor
MAX_RESPONSIVENESS = 0.02  # Maximum value for responsiveness factor
HEATED_AREA = 230  # Area of the heated space in square meters (m²)


class ThermalPropertiesClass(hass.Hass):

    def initialize(self):
        self.THERMAL_ADJUSTMENT_FACTOR = 0.1
        self.RESPONSIVENESS_FACTOR = 0.01
        state = self.get_state("sensor.santetorp_rumsgivare_temperature")
        if state == 'unavailable':
            self.previous_temperature = 0.0  # or any default value
        else:
            self.previous_temperature = float(state)
        self.previous_time = datetime.now()
        self.total_energy_consumption = 0.0  # Initialize total energy consumption

        # Run the function immediately
        self.calculate_thermal_accumulation()

        # Schedule the function to run every minute
        self.run_minutely(self.calculate_thermal_accumulation, datetime.now())

        # Listen for changes in the thermal_mass
        self.listen_state(self.on_thermal_mass_change, "input_number.thermal_mass")

        # Start the continuous updates
        self.continuous_factor_update_scheduler()

    def update_adjustment_factor(self, new_factor):
        self.THERMAL_ADJUSTMENT_FACTOR = new_factor

    def update_responsiveness_factor(self, new_factor):
        self.RESPONSIVENESS_FACTOR = new_factor

    def on_thermal_mass_change(self, entity, attribute, old, new, kwargs):
        self.calculate_thermal_accumulation()

    def calculate_heat_transfer_coefficient(self, outdoor_temperature, indoor_temperature, window_area, wall_area, underground_wall_area, roof_area):
        delta_temperature = indoor_temperature - outdoor_temperature
        window_coefficient = 1.3  # Adjust this based on window properties
        wall_coefficient = 0.8  # Adjust this based on wall properties
        underground_wall_coefficient = 1.0  # Adjust this based on underground wall properties
        roof_coefficient = 0.7  # Adjust this based on roof properties
        heat_transfer_coefficient = (window_area * window_coefficient + wall_area * wall_coefficient + underground_wall_area * underground_wall_coefficient + roof_area * roof_coefficient) / (window_area + wall_area + underground_wall_area + roof_area)
        return round(heat_transfer_coefficient, 3)  # rounding to 3 decimal places

    def calculate_thermal_accumulation(self, kwargs=None):
        if (datetime.now() - self.previous_time).total_seconds() < 60:
            return

        state = self.get_state("sensor.santetorp_rumsgivare_temperature")
        if state == 'unavailable':
            self.log("sensor.santetorp_rumsgivare_temperature is unavailable")
            return
        current_temperature = float(state)
        indoor_temperature = float(state)  # Use the same sensor for indoor temperature

        outdoor_temperature = float(self.get_state("sensor.santetorp_rumsgivare_utegivare_temperature"))

        window_area = 20  # Replace with the actual window area in square meters (m²)
        wall_area = 250  # Replace with the actual wall area in square meters (m²)
        underground_wall_area = 50  # Replace with the actual wall area in square meters (m²)
        roof_area = 100  # Replace with the actual roof area in square meters (m²)
        heat_transfer_coefficient = self.calculate_heat_transfer_coefficient(outdoor_temperature, indoor_temperature, window_area, wall_area, underground_wall_area, roof_area)
        # Use responsiveness factor to control the effect of thermal mass
        thermal_mass = float(self.get_state("input_number.thermal_mass"))
        adjusted_thermal_mass = thermal_mass * self.RESPONSIVENESS_FACTOR

        current_time = datetime.now()
        current_hour = current_time.replace(minute=0, second=0, microsecond=0)

        future_hour_start = current_time + timedelta(hours=int(adjusted_thermal_mass))
        future_hour_end = future_hour_start + timedelta(hours=1)
        future_hour = "{}-{}".format(future_hour_start.strftime("%Y%m%d %H:00"), future_hour_end.strftime("%H:00"))

        weather_forecast = self.get_state("sensor.weatherforecast_hvac", attribute=future_hour)

        if weather_forecast is not None and "feels_like" in weather_forecast:
            future_feels_like_temperature = float(weather_forecast["feels_like"])
        else:
            self.log(f"Attribute {future_hour} does not exist for sensor.weatherforecast_hvac")
            return

        temperature_difference = round(current_temperature - future_feels_like_temperature, 2)

        time_interval = round((current_time - self.previous_time).total_seconds(), 2)  # in seconds
        rate_of_change = round((current_temperature - self.previous_temperature) / (time_interval / 60), 2)  # in °C/minute

        # Calculate heat loss in kW
        heat_loss = round(heat_transfer_coefficient * (window_area + wall_area + underground_wall_area + roof_area) * temperature_difference, 2)  # in W

        # Convert heat loss to kWh
        heat_loss_kwh = round(heat_loss / 1000, 5)  # Convert watts to kilowatts


        # Accumulate energy consumption
        self.total_energy_consumption += heat_loss_kwh

        # Calculate thermal accumulation
        thermal_accumulation = round(adjusted_thermal_mass * rate_of_change * (time_interval / 60) * heat_transfer_coefficient, 2)
        new_temperature = round(current_temperature + thermal_accumulation, 2)
        self.log(f"Temperature Difference: {temperature_difference}")
        self.log(f"Rate of Change: {rate_of_change}")
        self.log(f"Heat Loss: {heat_loss}")

        error = round(current_temperature - new_temperature, 2)
        thermal_mass = round(thermal_mass + error * self.THERMAL_ADJUSTMENT_FACTOR, 2)

        # Calculate momentaneous consumption in kW based on a longer time interval (e.g., 1 minute)
        long_time_interval = 60  # set to 60 seconds (1 minute)
        momentaneous_consumption_kw = round(thermal_accumulation / long_time_interval, 2)  # Keep the value in kilowatts

        # Calculate heat requirement per square meter (W/m²)
        heat_requirement_per_m2 = round(heat_loss / HEATED_AREA, 2)

        # Set the state and attributes of the sensor
        self.set_state("sensor.thermal_properties", state=new_temperature, attributes={
            'indoor_temperature': current_temperature,
            'outdoor_temperature': outdoor_temperature,
            'future_feels_like_temperature': future_feels_like_temperature,
            'temperature_difference': temperature_difference,
            'rate_of_change': rate_of_change,
            'time_interval': time_interval,
            'current_responsiveness': self.RESPONSIVENESS_FACTOR,
            'adjusted_thermal_mass': adjusted_thermal_mass,
            'current_time': current_time.strftime("%Y-%m-%d %H:%M:%S"),
            'thermal_mass': thermal_mass,
            'thermal_accumulation': thermal_accumulation,
            'heat_loss': heat_loss,
            'heat_loss_kwh': heat_loss_kwh,
            'heat_transfer_coefficient': heat_transfer_coefficient,
            'momentaneous_consumption_kw': momentaneous_consumption_kw,
            'total_energy_consumption': self.total_energy_consumption,
            'heat_requirement_per_m2': heat_requirement_per_m2  # Add heat requirement per m² to attributes
        })

        self.call_service("input_number/set_value", entity_id="input_number.thermal_mass", value=thermal_mass)
        self.previous_temperature = current_temperature
        self.previous_time = current_time

    def continuous_factor_update_scheduler(self):
        self.run_every(self.intelligent_adjustment_factor_update, datetime.now(), 60*60)  # 60*60 seconds = 1 hour

    def intelligent_adjustment_factor_update(self, kwargs=None):
        # Implement logic to dynamically adjust the factor based on certain conditions

        # Example: If the rate of change in error is consistently high, increase the responsiveness factor
        error = self.get_state("sensor.thermal_properties", attribute="error")
        rate_of_change_error = self.get_state("sensor.thermal_properties", attribute="rate_of_change_error")

        if rate_of_change_error is not None and abs(rate_of_change_error) > RATE_CHANGE_THRESHOLD:
            self.update_responsiveness_factor(self.RESPONSIVENESS_FACTOR + RATE_CHANGE_FACTOR)

        # Make sure the responsiveness factor stays within a reasonable range
        self.RESPONSIVENESS_FACTOR = min(max(self.RESPONSIVENESS_FACTOR, MIN_RESPONSIVENESS), MAX_RESPONSIVENESS)
        self.log(f"Error: {error}")
        self.log(f"Rate of Change Error: {rate_of_change_error}")
        self.log(f"Adjusted Responsiveness Factor: {self.RESPONSIVENESS_FACTOR}")
