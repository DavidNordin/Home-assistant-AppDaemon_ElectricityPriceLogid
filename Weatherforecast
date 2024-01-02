import requests
import math
from datetime import datetime, timedelta
import hassapi as hass
import json  # Add this line

class WeatherForecast(hass.Hass):

    def initialize(self):
        # Get the current time
        now = datetime.now()

        # Calculate the next hour
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        # Run fetch_weather_data immediately
        self.fetch_weather_data({})

        # Schedule the first run at the next hour
        self.run_at(self.fetch_weather_data, next_hour)

        # Schedule subsequent runs every hour
        self.run_hourly(self.fetch_weather_data, next_hour)

    def fetch_weather_data(self, kwargs):
        # Fetch the current state and attributes of the sensor
        old_state = self.get_state("sensor.weatherforecast_HVAC")
        old_attributes = self.get_state("sensor.weatherforecast_HVAC", attribute="all")
        
        # Check if the sensor's state is None
        if old_attributes is None:
            old_attributes = {}
        else:
            old_attributes = old_attributes['attributes']

        # Constants for the supply temperature calculation
        X1 = -18.0
        X2 = 15.0
        Y1 = 55.0  # Replace with your actual value
        Y2 = 20.0  # Replace with your actual value
        MIN = -30.0  # Replace with your actual value
        MAX = 30.0  # Replace with your actual value

        # Constants for the wind chill index calculation
        A = 13.12
        B = 0.6215
        C = -11.37
        D = 0.3965

        # Constants for the heat index calculation
        c = [0, -42.379, 2.04901523, 10.14333127, -0.22475541, -6.83783e-3, -5.481717e-2, 1.22874e-3, 8.5282e-4, -1.99e-6]

        # Replace 'YOUR_LATITUDE' and 'YOUR_LONGITUDE' with your actual latitude and longitude
        latitude = '56.918100'
        longitude = '12.730500'

        # Make a GET request to the SMHI API
        url = f'https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2/geotype/point/lon/{longitude}/lat/{latitude}/data.json'
        response = requests.get(url)
        
        # Log the status code and response text
        # self.log(f"Status Code: {response.status_code}, Response: {response.text}")

        # Check if the request was successful
        if response.status_code == 200:
            # Parse the response JSON
            data = response.json()

            # Extract the forecast data
            forecast = data['timeSeries']

            # Get the "validTime" from the latest forecast entry
            latest_valid_time = forecast[0]['validTime']

            # Get the current date and the date of tomorrow
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)

            # Initialize an empty dictionary for the hourly values
            hourly_values = {}

            # Process the forecast data
            for entry in forecast:
                #Extract the date and time from the valid time
                time = datetime.strptime(entry['validTime'], "%Y-%m-%dT%H:%M:%SZ")
                date = time.date()  # Add this line

                # Format the time as "YYYYMMDD HH:MM-HH:MM"
                formatted_time = f"{date.year}{date.month:02d}{date.day:02d} {time.hour:02d}:{time.minute:02d}-{(time.hour+1)%24:02d}:{time.minute:02d}"

                # Skip this entry if the date is not today or tomorrow
                if date != today and date != tomorrow:
                    continue

                # Extract relevant information from each entry
                parameters = {parameter['name']: parameter['values'][0] for parameter in entry['parameters']}

                # Extract the temperature, wind speed, and relative humidity
                t = parameters.get('t', 'N/A')
                ws = parameters.get('ws', 'N/A')
                r = parameters.get('r', 'N/A')

                # Calculate the "feels like" temperature
                if t <= 15.0:
                    # Use the wind chill index for cold weather
                    feels_like = A + B * t + C * math.pow(ws, 0.16) + D * t * math.pow(ws, 0.16)
                else:
                    # Use the heat index for warm weather
                    feels_like = c[1] + c[2] * t + c[3] * r + c[4] * t * r + c[5] * t * t + c[6] * r * r + c[7] * t * t * r + c[8] * t * r * r + c[9] * t * t * r * r

                # Calculate the supply temperature
                supply_temp = Y1 + ((t - X1) * (Y2 - Y1)) / (X2 - X1)

                # Round down the values to one decimal place
                t = math.floor(t * 10) / 10
                feels_like = math.floor(feels_like * 10) / 10
                supply_temp = math.floor(supply_temp * 10) / 10

                # Add the data to the hourly values
                hourly_values[formatted_time] = {
                    'temperature': t,
                    'feels_like': feels_like,
                    'supply_temp': supply_temp,
                }

                # Calculate the minimum and maximum supply temperatures
                min_supply_temp = Y1 + ((MIN - X1) * (Y2 - Y1)) / (X2 - X1)
                max_supply_temp = Y1 + ((MAX - X1) * (Y2 - Y1)) / (X2 - X1)
            
            # Prepare the new attributes
            new_attributes = {**hourly_values, "time of forecast": latest_valid_time}
            
            # Check if the forecast data has changed
            if old_state != "on" or old_attributes != new_attributes:
                # Set the state of the sensor
                self.set_state("sensor.weatherforecast_HVAC", state="on", attributes=new_attributes)

                # Log a message after setting the state of the sensor
                self.log("State set successfully")
            else:
                self.log("Forecast data has not changed")

            # Print the hourly values
            for formatted_time, data in hourly_values.items():
                self.log(f"Time: {formatted_time}, Temperature: {data['temperature']:.1f}, Feels Like: {data['feels_like']:.1f}, Supply Temp: {data['supply_temp']:.1f}")
        else:
            self.log('Error: Failed to retrieve forecast data')

    def terminate(self):
        pass