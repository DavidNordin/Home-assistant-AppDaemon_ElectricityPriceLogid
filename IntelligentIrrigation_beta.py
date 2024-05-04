import appdaemon.plugins.hass.hassapi as hass
import datetime
from dateutil.parser import parse
import requests
import numpy as np
import pandas as pd
import inspect
from sklearn.linear_model import LinearRegression
from sklearn.impute import SimpleImputer

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

class GreenhouseController(hass.Hass):
    
    def initialize(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.log("Initializing Greenhouse Controller")
        self.model = LinearRegression()  # Create the model object here
        self.train_model_and_predict() # Train the model with historical data
        self.run_forecast() # Run the forecast function
        self.run_hourly(self.train_model_and_predict, datetime.time(0, 0, 0))   # Train the model every hour
        self.run_hourly(self.run_forecast, datetime.time(0, 0, 0))  # Run the forecast every hour
        self.listen_event(self.log_irrigation_event, "irrigation_event")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        
    def update_sensor_state(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Fetch the current values of duration, current_cycle, num_cycles, and predicted_temperature
        duration = getattr(self, 'get_current_duration', None)
        current_cycle = getattr(self, 'current_cycle', None)
        num_cycles = getattr(self, 'num_cycles', None)
        predicted_temperature = getattr(self, 'get_predicted_temperature', None)

        # Call set_sensor_state with the current values
        self.set_sensor_state(duration, current_cycle, num_cycles, predicted_temperature)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def train_model_and_predict(self, weather_data=None):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Fetch historical data for training the model
        start_time = datetime.datetime.now() - datetime.timedelta(days=30)  # Fetch data from the last 30 days
        end_time = datetime.datetime.now()
        historical_data = self.get_historical_data(start_time, end_time)
        
        # Use historical data for training the model
        if not historical_data.empty:
            # Ensure the index is a datetime index
            historical_data.index = pd.to_datetime(historical_data.index)
        
            # Extract hour, day and month from timestamp
            historical_data['month'] = historical_data.index.month
            historical_data['day_of_month'] = historical_data.index.day
            historical_data['hour_of_day'] = historical_data.index.hour
        
            X_train = historical_data[['ambient_temperature', 'cloudiness', 'bell_curve_adjustment', 'month', 'day_of_month', 'hour_of_day']]
            print("Training Feature Dimensions:", X_train.shape)
            print("Training Feature Types:", X_train.dtypes)
            y_train = historical_data['greenhouse_temperature']  # Target variable
            self.model.fit(X_train, y_train)  # Fit the model with historical data
        else:
            self.log("Failed to fetch historical data for training the model")
            return None
    
        # If weather data is provided, make a prediction
        if weather_data is not None:
            # Use the real-time cloud coverage and forecast data for prediction
            daily_cloudiness = self.aggregate_daily_cloudiness(weather_data)
            forecast_X = pd.DataFrame(daily_cloudiness, columns=['cloudiness'])
            
            # Ensure 'ambient_temperature', 'cloudiness', 'bell_curve_adjustment' columns are correctly populated with actual data
            # forecast_X['ambient_temperature'] = ...
            # forecast_X['cloudiness'] = ...
            # forecast_X['bell_curve_adjustment'] = ...
        
            # Convert 'timestamp' to datetime and extract features
            forecast_X['timestamp'] = pd.to_datetime(forecast_X['timestamp'])
            forecast_X.set_index('timestamp', inplace=True)
            forecast_X['month'] = forecast_X.index.month
            forecast_X['day_of_month'] = forecast_X.index.day
            forecast_X['hour_of_day'] = forecast_X.index.hour
        
            # Predict temperature using the trained model
            try:
                X = forecast_X[['ambient_temperature', 'cloudiness', 'bell_curve_adjustment', 'month', 'day_of_month', 'hour_of_day']]
                predicted_temperature = self.model.predict(X)
                predicted_temperature = np.clip(predicted_temperature, a_min=LOW_TEMPERATURE_THRESHOLD, a_max=HIGH_TEMPERATURE_THRESHOLD)  # Ensure that the predicted temperature is within a reasonable range
                self.log(f"Predicted temperature: {predicted_temperature}")
                return predicted_temperature
            except Exception as e:
                self.log(f"Error predicting temperature: {e}")
                return None
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
            
# Historical section start
    def get_historical_data(self, start_time, end_time):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Round start_time to the nearest hour
        start_time = start_time.replace(minute=0, second=0, microsecond=0)
    
        # Fetch historical cloudiness data
        cloudiness_data = self.get_historical_cloudiness_data(start_time, end_time)['cloudiness'].tolist()
        
        # Fetch historical outside temperature data
        ambient_temperature_data = self.get_historical_outside_temperature_data(start_time, end_time, OUTSIDE_TEMPERATURE_SENSOR)['temperature'].tolist()
    
        # Fetch historical greenhouse temperature data
        greenhouse_temperature_data = self.get_historical_greenhouse_temperature_data(start_time, end_time, GREENHOUSE_TEMPERATURE_SENSOR)['temperature'].tolist()
    
        # Determine the minimum length of all data arrays
        min_length = min(len(ambient_temperature_data), len(cloudiness_data), len(greenhouse_temperature_data))
    
        # Truncate arrays to the minimum length
        ambient_temperature_data = ambient_temperature_data[:min_length]
        cloudiness_data = cloudiness_data[:min_length]
        greenhouse_temperature_data = greenhouse_temperature_data[:min_length]
    
        # Generate timestamps for each data point
        timestamp = pd.date_range(start=start_time, periods=min_length, freq='H')
        
        # Calculate bell curve adjustment for each hour based on the timestamp
        bell_curve_adjustment = [self.adjust_temperature_bell_curve(hour) for hour in timestamp.hour]
    
        # Combine data into a DataFrame
        historical_data = pd.DataFrame({
            'timestamp': timestamp,
            'ambient_temperature': ambient_temperature_data,
            'cloudiness': cloudiness_data,
            'bell_curve_adjustment': bell_curve_adjustment,
            'greenhouse_temperature': greenhouse_temperature_data
        })
        
        # Log the generated features
        self.log("Generated features for historical data: {}".format(historical_data.columns.tolist()))
        self.log("Historical data size: {}".format(historical_data.shape))
        self.log("Historical data sample:\n{}".format(historical_data.head(24).to_string(index=False)))
    
        return historical_data
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def get_historical_greenhouse_temperature_data(self, start_time, end_time, sensor_name):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Get the historical data from the sensor
            history = self.get_history(entity_id=GREENHOUSE_TEMPERATURE_SENSOR, start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values and the associated timestamps from the history
                data = [(pd.to_datetime(state['last_changed']).round('H'), float(state['state'])) for state in history[0] if state['state'] not in ['unknown', 'unavailable']]
                
                # Convert the data to a DataFrame
                data = pd.DataFrame(data, columns=['timestamp', 'temperature'])
    
                # Convert 'timestamp' to datetime format
                data['timestamp'] = pd.to_datetime(data['timestamp'])
    
                # Set 'timestamp' as the index
                data.set_index('timestamp', inplace=True)
    
                # Interpolate missing data
                data['temperature'] = data['temperature'].interpolate(method='time')
            else:
                data = pd.DataFrame(columns=['timestamp', 'temperature'])
        except Exception as e:
            self.log(f"Error getting temperature data: {e}")
            data = pd.DataFrame(columns=['timestamp', 'temperature'])
            
        return data
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def get_historical_outside_temperature_data(self, start_time, end_time, sensor_name):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Get the historical data from the sensor
            history = self.get_history(entity_id=OUTSIDE_TEMPERATURE_SENSOR, start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values and the associated timestamps from the history
                data = [(pd.to_datetime(state['last_changed']).round('H'), float(state['state'])) for state in history[0] if state['state'] not in ['unknown', 'unavailable']]
                # Convert the data to a DataFrame
                data = pd.DataFrame(data, columns=['timestamp', 'temperature'])
                # Set 'timestamp' as the index
                data.set_index('timestamp', inplace=True)
                # Interpolate missing data
                data['temperature'] = data['temperature'].interpolate(method='time')
            else:
                data = pd.DataFrame(columns=['timestamp', 'temperature'])
        except Exception as e:
            self.log(f"Error getting temperature data: {e}")
            data = pd.DataFrame(columns=['timestamp', 'temperature'])
            
        return data
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def get_historical_cloudiness_data(self, start_time, end_time):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Get historical cloud coverage data from the sensor
            history = self.get_history(entity_id='sensor.openweathermap_cloud_coverage', start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values and the associated timestamps from the history
                data = [(pd.to_datetime(state['last_changed']).round('H').strftime('%Y-%m-%d %H:%M:%S'), float(state['state'])) for state in history[0] if state['state'] not in ['unknown', 'unavailable']]
                # Convert the data to a DataFrame
                data = pd.DataFrame(data, columns=['timestamp', 'cloudiness'])
                # Set 'timestamp' as the index
                data.set_index('timestamp', inplace=True)
            else:
                data = pd.DataFrame(columns=['timestamp', 'cloudiness'])
        except Exception as e:
            self.log(f"Error getting cloudiness data: {e}")
            data = pd.DataFrame(columns=['timestamp', 'cloudiness'])
            
        return data
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
# Historical section end
    
# Forecast section start
    def run_forecast(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Fetch forecast data
        latitude = float(self.get_state('zone.home', attribute='latitude'))
        longitude = float(self.get_state('zone.home', attribute='longitude'))
        weather_data = self.fetch_weather_forecast(latitude, longitude)
    
        # Prepare forecast data
        forecast_X_imputed, weather_data, current_hour, remaining_hours_today = self.prepare_forecast_DataFrame(weather_data)
    
        # Predict forecast temperature
        self.predict_forecast_temperature(forecast_X_imputed)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        
    def fetch_weather_forecast(self, latitude, longitude):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.log("Fetching hourly forecast from OpenWeatherMap")
        api_key = "f8da86d4bbb696f7f2f703a23b0eb31f"
        weather_url = f"https://api.openweathermap.org/data/3.0/onecall?lat={latitude}&lon={longitude}&exclude=minutely,daily,alerts&appid={api_key}&units=metric"
        weather_data = self.fetch_data_from_url(weather_url)
        if weather_data is not None:
            formatted_forecast = []
            for hour_data in weather_data.get("hourly", []):  
                timestamp = hour_data.get("dt", "")  # Timestamp              
                temp = hour_data.get("temp", "")  # Temperature
                clouds = hour_data.get("clouds", "")  # Cloudiness
                
                formatted_hour_data = {
                    "dt": timestamp,
                    "temp": temp,
                    "clouds": clouds
                }
                formatted_forecast.append(formatted_hour_data)
            return {"hourly": formatted_forecast}
        else:
            self.log("Failed to fetch weather data")
            return None
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def process_weather_forecast_data(self, weather_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.log("Processing weather forecast data...")
        if 'hourly' not in weather_data:
            self.log("'hourly' key not found in weather data.")
            return None
        timestamps = []
        temperatures = []
        cloudinesses = []
        for hour_data in weather_data['hourly']:
            timestamp = hour_data.get("dt", "")  # Unix timestamp
            temperature = hour_data.get("temp", "")  # Temperature
            humidity = hour_data.get("humidity", "")  # Humidity
            clouds = hour_data.get("clouds", "")  # Cloudiness
            timestamp = datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            timestamps.append(timestamp)
            temperatures.append(temperature)
            cloudinesses.append(clouds)
        return timestamps, temperatures, cloudinesses
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def fetch_data_from_url(self, url):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            return None
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def fetch_and_process_forecast_data(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        current_cloudiness = float(self.get_state('sensor.openweathermap_forecast_cloud_coverage'))
        latitude = float(self.get_state('zone.home', attribute='latitude'))
        longitude = float(self.get_state('zone.home', attribute='longitude'))
        weather_data = self.fetch_weather_forecast(latitude, longitude)
        daily_cloudiness = self.aggregate_daily_cloudiness(weather_data)
        forecast_X = pd.DataFrame(daily_cloudiness, columns=['cloudiness'])
        forecast_X.loc[len(forecast_X)] = [current_cloudiness]
        imputer = SimpleImputer(strategy='mean')
        forecast_X_imputed = imputer.fit_transform(forecast_X)
        predicted_temperature = self.model.predict(forecast_X_imputed)
        self.log(f"Predicted temperature: {predicted_temperature}")  # Log the contents of predicted_temperature
        return forecast_X_imputed, predicted_temperature
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def prepare_forecast_DataFrame(self, weather_data, kwargs=None):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        today = datetime.datetime.now().date()
        current_hour = datetime.datetime.now().hour
        remaining_hours_today = 24 - current_hour
        self.log("Processing weather data...")
        timestamps, temperatures, cloudinesses = self.process_weather_forecast_data(weather_data)
        if timestamps is None or temperatures is None or cloudinesses is None:
            self.log("Failed to process weather data")
            return
        forecast_X_imputed = pd.DataFrame({
            'timestamp': timestamps,
            'ambient_temperature': temperatures,
            'cloudiness': cloudinesses
        })
        forecast_X_imputed['ambient_temperature'].interpolate(method='linear', inplace=True)
        forecast_X_imputed['cloudiness'].interpolate(method='linear', inplace=True)
        self.log("Weather data processed successfully.")
        self.log("Shape of forecast_X_imputed: {}".format(forecast_X_imputed.shape))
        if forecast_X_imputed.shape[1] != 3:
            raise ValueError(f"Expected 3 features (timestamp, ambient_temperature, cloudiness), but got {forecast_X_imputed.shape[1]}")
        bell_curve_adjustment = [self.adjust_temperature_bell_curve(parse(str(timestamp)).hour) for timestamp in forecast_X_imputed['timestamp']]
        bell_curve_adjustment = np.array(bell_curve_adjustment).reshape(-1, 1)
        forecast_X_imputed.loc[:, 'bell_curve_adjustment'] = bell_curve_adjustment.ravel()
        if forecast_X_imputed.shape[1] != 4:
            raise ValueError(f"Expected 4 features (timestamp, ambient_temperature, cloudiness, bell_curve_adjustment), but got {forecast_X_imputed.shape[1]}")
        self.log("Shape of forecast_X_imputed: {}".format(forecast_X_imputed.shape))
        self.log("Sample of forecast_X_imputed:\n{}".format(forecast_X_imputed.head()))
        self.log("Full forecast data sample:\n{}".format(forecast_X_imputed.head().to_string(index=False)))
        return forecast_X_imputed, weather_data, current_hour, remaining_hours_today
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def process_forecast_today(self, weather_data, hourly_forecast_today, current_hour, remaining_hours_today):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        hourly_forecast_today = [hour_data for hour_data in weather_data['hourly'] if parse(hour_data['dt']).hour >= current_hour][:remaining_hours_today]
        self.process_forecast(hourly_forecast_today)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def predict_forecast_temperature(self, forecast_X_imputed):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Convert 'timestamp' to datetime and extract features
            forecast_X_imputed['timestamp'] = pd.to_datetime(forecast_X_imputed['timestamp'])
            forecast_X_imputed['month'] = forecast_X_imputed['timestamp'].dt.month
            forecast_X_imputed['day_of_month'] = forecast_X_imputed['timestamp'].dt.day
            forecast_X_imputed['hour_of_day'] = forecast_X_imputed['timestamp'].dt.hour
        
            # Ensure that the data used for prediction has the same features as the data used for training
            predicted_temperature = np.round(self.model.predict(forecast_X_imputed.drop(columns=['timestamp'])), 2)
        except Exception as e:
            self.log(f"Model prediction failed with error: {e}")
            predicted_temperature = []
        if len(predicted_temperature) > 0:
            # Create a DataFrame that contains the timestamps and the corresponding predicted temperatures
            predicted_df = pd.DataFrame({
                'timestamp': forecast_X_imputed['timestamp'],
                'greenhouse_temperature': predicted_temperature
            })
            # Log each predicted temperature along with its corresponding timestamp
            self.log("Predicted temperatures:\n{}".format(predicted_df.head(24).to_string(index=False)))
            self.schedule_irrigation(predicted_df)
        else:
            self.log("Failed to predict temperature")
            return
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def aggregate_daily_cloudiness(self, weather_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        daily_cloudiness = []
        if 'hourly' in weather_data:
            for hour_data in weather_data['hourly']:
                date = parse(hour_data['dt']).date()
                daily_cloudiness.append({
                    'date': date,
                    'cloudiness': hour_data['clouds']
                })
        else:
            self.log("No 'hourly' key in weather data")
        return daily_cloudiness
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def calculate_hourly_forecast(self, predicted_temperature):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        hourly_forecast = {}
        self.log(f"Hourly forecast before calculation: {hourly_forecast}")
        self.log(f"Predicted temperatures inside calculate_hourly_forecast: {predicted_temperature}")
        for index, row in predicted_temperature.iterrows():
            timestamp = pd.to_datetime(index)
            hour = timestamp.hour  # Extract the hour from the timestamp
            # Format the key as a string containing the date and hour interval
            key = f"{timestamp.strftime('%Y-%m-%d')} {hour:02}:00-{(hour+1)%24:02}:00"
            # Format the value as a string containing the temperature
            value = f"{row['greenhouse_temperature']:.2f}"
            hourly_forecast[key] = value
        self.log(f"Hourly forecast after calculation: {hourly_forecast}")
        return hourly_forecast
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def adjust_temperature_bell_curve(self, hour):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Fetch the next_noon attribute from the sun.sun entity
        next_noon_utc = self.get_state('sun.sun', attribute='next_noon')
        
        # Parse next_noon to a datetime object
        next_noon_utc = parse(next_noon_utc)
        
        # Convert next_noon to local timezone
        next_noon_local = next_noon_utc.astimezone(datetime.datetime.now().tzinfo)
        
        # Extract the hour from the local time
        next_noon_hour = next_noon_local.hour
        
        # Calculate the difference between the current hour and solar noon
        hour_diff = abs(hour - next_noon_hour)
        
        # Adjust the temperature using a bell curve function with peak at 2 and minimum value at 1
        std_dev = 2  # Standard deviation controls the width of the curve
        temperature_at_hour = 1 + np.exp(-0.5 * ((hour_diff) / std_dev) ** 2)   # Bell curve function

        return temperature_at_hour
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

#Irrigation section start
    def schedule_irrigation(self, predicted_temperature):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Check if irrigation is needed
        if self.is_irrigation_needed():
            self.log("Scheduling irrigation")
            hourly_forecast = self.calculate_hourly_forecast(predicted_temperature)
        
            # Get the current day
            today = pd.Timestamp.now().normalize()
        
            # Get the historical data
            start_time = today  # start of the current day
            end_time = today + pd.Timedelta(days=1, seconds=-1)  # end of the current day at 23:59:59 
            self.historical_data = self.get_historical_data(start_time, end_time)
            self.log(f"Historical data: {self.historical_data}")
        
            # Filter out specific columns from the historical data
            self.historical_data = self.historical_data[['timestamp', 'greenhouse_temperature']]
            self.log(f"Filtered historical data: {self.historical_data}")
        
            # Convert the 'timestamp' column to datetime
            predicted_temperature.loc[:, 'timestamp'] = pd.to_datetime(predicted_temperature['timestamp'])
        
            # Filter the data for today
            today = pd.Timestamp.now().normalize()
            predicted_temperature = predicted_temperature[predicted_temperature['timestamp'].dt.date == today.date()]
        
            self.log(f"Predicted temperatures for today: {predicted_temperature}")
        
            # Convert 'timestamp' to datetime format and set as index for historical_data
            self.historical_data.loc[:, 'timestamp'] = pd.to_datetime(self.historical_data['timestamp'])
            self.historical_data.set_index('timestamp', inplace=True)
        
            # Convert 'timestamp' to datetime format and set as index for predicted_temperature
            predicted_temperature.loc[:, 'timestamp'] = pd.to_datetime(predicted_temperature['timestamp'])
            predicted_temperature.set_index('timestamp', inplace=True)
        
            # Combine the DataFrames
            df_combined = self.historical_data.combine_first(predicted_temperature)
            self.log(f"Combined DataFrame: {df_combined}")
        
            # Calculate the mean of the greenhouse temperatures for the current day
            self.greenhouse_temperature = round(df_combined['greenhouse_temperature'].mean(), 2)
            self.log(f"Mean greenhouse temperature for the current day: {self.greenhouse_temperature}")
        
            humidity = float(self.get_state(GREENHOUSE_HUMIDITY_SENSOR))
            cloudiness = float(self.get_state('sensor.openweathermap_forecast_cloud_coverage'))
            hour = datetime.datetime.now().hour
        
            # Determine the number of watering cycles and the amount of water per cycle based on the ambient temperature
            num_cycles, water_per_cycle = self.determine_irrigation_parameters(self.greenhouse_temperature)
        
            # Define self.num_cycles
            self.num_cycles = num_cycles
        
            water_amount = num_cycles * water_per_cycle
            runtime_hours = water_per_cycle / WATER_OUTPUT_RATE
            duration = datetime.timedelta(hours=runtime_hours)
        
            # Call set_sensor_state with predicted_temperature argument
            # Assuming current_cycle starts from 1
            current_cycle = 1  # Adjust as needed based on your logic
            self.set_sensor_state(duration, current_cycle, num_cycles, predicted_temperature)
        
            # Fire event
            self.fire_event("irrigation_started")
        else:
            self.log("Irrigation not needed")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def is_irrigation_needed(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Retrieve the timestamp of the last irrigation from a state or attribute
        last_irrigation_timestamp = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation', attribute='last_irrigation')

        # If the timestamp is None or 'N/A', then irrigation is needed
        if last_irrigation_timestamp is None or last_irrigation_timestamp == 'N/A':
            return True

        # Convert the timestamp to a datetime object
        last_irrigation_date = datetime.datetime.strptime(last_irrigation_timestamp, '%Y-%m-%d %H:%M')

        # Get the current date and time
        current_date = datetime.datetime.now()

        # Check if the last irrigation occurred today
        return last_irrigation_date.date() < current_date.date()
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def determine_irrigation_parameters(self, meantemperature):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        # If the mean temperature is less than 15 degrees, no irrigation is needed
        if meantemperature < 15:
            return 0, 0

        # If the mean temperature is less than or equal to 20 degrees
        # Check if irrigation was done yesterday
        # If irrigation was done yesterday, no cycles are scheduled for today
        # If irrigation was not done yesterday, schedule 1 cycle today
        # Each cycle will use 2 units of water
        elif meantemperature <= 20:
            return 1 if self.did_water_yesterday() else 0, 2
        
        # If the mean temperature is between 20 and 25 degrees (exclusive)
        # Schedule 1 cycle with 2 units of water
        elif 20 < meantemperature <= 25:
            return 1, 2
        
        # If the mean temperature is between 25 and 30 degrees (exclusive)
        # Schedule 1 cycle with 2 units of water
        elif 25 < meantemperature <= 30:
            return 1, 2
        
        # If the mean temperature is between 30 and 35 degrees (exclusive)
        # Schedule 2 cycles with 1.5 units of water each
        elif 30 < meantemperature <= 35:
            return 2, 1.5
        
        # If the mean temperature is greater than 35 degrees
        # Schedule 3 cycles with 1 unit of water each
        else:  # meantemperature > 35
            return 3, 1

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
    
        # Convert time_until_run from seconds to minutes
        time_until_run = min(delays) / 60 if delays else 0
    
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return time_until_run, scheduled_times
    def calculate_seconds_until_morning(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        now = datetime.datetime.now()
        next_morning = datetime.datetime(now.year, now.month, now.day, 6, 0)  # 6 AM
        if now > next_morning:
            next_morning += datetime.timedelta(days=1)
        return next_morning
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def calculate_seconds_until_afternoon(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        now = datetime.datetime.now()
        next_afternoon = datetime.datetime(now.year, now.month, now.day, 14, 0)  # 2 PM
        if now > next_afternoon:
            next_afternoon += datetime.timedelta(days=1)
        return next_afternoon
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def calculate_seconds_until_evening(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        now = datetime.datetime.now()
        next_evening = datetime.datetime(now.year, now.month, now.day, 18, 0)  # 6 PM
        if now > next_evening:
            next_evening += datetime.timedelta(days=1)
        return next_evening
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def start_irrigation(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Turn on the irrigation system
        self.call_service('switch/turn_on', entity_id='switch.sonoff_smartrelay_1')

        # Check if the irrigation system is on
        if self.get_state('switch.sonoff_smartrelay_1') != 'on':
            self.call_service('notify/notify', message='Failed to start irrigation system.')
            return

        # Update the timestamp of the last irrigation
        self.set_state('sensor.sensor_greenhouse_intelligent_irrigation', attribute='last_irrigation', value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        
        # Define the water output rate of your irrigation system (in liters per hour)
        water_output_rate = 4

        # Get the duration of the last irrigation (in hours)
        # If the duration is not already in hours, convert it
        last_irrigation_duration = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation', attribute='last_irrigation_duration') / 3600  # Convert from seconds to hours

        # Calculate the amount of water used in the last irrigation
        last_irrigation_amount = water_output_rate * last_irrigation_duration
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def did_water_yesterday(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Retrieve the timestamp of the last irrigation from a state or attribute
        last_irrigation_timestamp = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation', attribute='last_irrigation')

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

    def handle_irrigation_state_change(self, entity, attribute, old, new, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        if old == "pending" and new == "running":
            self.fire_event("irrigation_started")
        elif old == "running" and new == "none":
            self.fire_event("irrigation_completed")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def log_irrigation_event(self, event_name, data, kwargs):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        water_amount = data.get("water_amount", "N/A")
        duration = data.get("duration", "N/A")
        self.log(f"Irrigation event - Water amount: {water_amount} liters, Duration: {duration}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        
    def get_current_duration(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Check if self.greenhouse_temperature is set
        if not hasattr(self, 'greenhouse_temperature'):
            # If not, raise an exception (or return a default value)
            return "00:00:00"
    
        # Determine the number of watering cycles and the amount of water per cycle based on the ambient temperature
        num_cycles, water_per_cycle = self.determine_irrigation_parameters(self.greenhouse_temperature)
        
        # Define self.num_cycles
        self.num_cycles = num_cycles
    
        # Define the water output rate of your irrigation system (in liters per hour)
        water_output_rate = 4  # Adjust this value based on your irrigation system
    
        # Calculate the duration of the current cycle (in hours)
        current_cycle_duration_hours = water_per_cycle / water_output_rate
    
        # Convert the duration from hours to a time string in the format 'HH:MM:SS'
        current_cycle_duration_seconds = int(current_cycle_duration_hours * 3600)
        current_cycle_duration_str = str(datetime.timedelta(seconds=current_cycle_duration_seconds))
    
        return current_cycle_duration_str
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
#Irrigation section end

    def set_sensor_state(self, duration, current_cycle, num_cycles, predicted_temperature):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        hourly_forecast = self.calculate_hourly_forecast(predicted_temperature)
        total_cycles = num_cycles
    
        # If the irrigation is not scheduled to run today
        if current_cycle > total_cycles or total_cycles == 0:
            next_running_cycle = "Tomorrow"
            cycle_no = "0/0"
            current_cycle_length = "N/A"
            time_left = "N/A"
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
        last_irrigation_duration_str = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation', attribute='current_cycle_length')
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
        last_irrigation = self.get_state('sensor.sensor_greenhouse_intelligent_irrigation', attribute='last_irrigation')
        if last_irrigation is None:
            last_irrigation = "N/A"
        last_updated = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        did_water_yesterday = 'YES' if self.did_water_yesterday() else 'NO'
        time_until_run, scheduled_times = self.schedule_watering_cycles(num_cycles, duration)
        if time_until_run is None:
            time_until_run = "N/A"
        if not scheduled_times:
            scheduled_times = ["N/A"]
        
        self.set_state('sensor.sensor_greenhouse_intelligent_irrigation', state='ON', attributes={
            'planned_irrigation': scheduled_times,
            'next_running_cycle #': f"{next_running_cycle} ({next_running_cycle_time})",
            'cycle_no': f"{self.current_cycle}/{total_cycles}",
            'current_cycle_length': duration_str,
            'hourly_forecast': hourly_forecast,
            'last_updated': last_updated,
            'last_irrigation': last_irrigation,
            'last_irrigation_amount': last_irrigation_amount,
            'did_water_yesterday': did_water_yesterday
        })
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")