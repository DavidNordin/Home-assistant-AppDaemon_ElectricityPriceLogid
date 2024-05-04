import appdaemon.plugins.hass.hassapi as hass
import datetime
from dateutil.parser import parse
import requests
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.impute import SimpleImputer

HIGH_TEMPERATURE_THRESHOLD = 30
LOW_TEMPERATURE_THRESHOLD = 10
OUTSIDE_TEMPERATURE_SENSOR = 'sensor.santetorp_rumsgivare_utegivare_temperature'
GREENHOUSE_TEMPERATURE_SENSOR = 'sensor.sensor_i_vaxthuset_temperature'
GREENHOUSE_HUMIDITY_SENSOR = 'sensor.sensor_i_vaxthuset_humidity'

model = LinearRegression()

class GreenhouseController(hass.Hass):
    
    def initialize(self):
        self.log("Initializing Greenhouse Controller")
        self.train_model()
        self.fetch_and_process_forecast()
        self.run_hourly(self.fetch_and_process_forecast, datetime.time(0, 0, 0))

    def train_model(self):
        # Fetch historical data for training the model
        start_time = datetime.datetime.now() - datetime.timedelta(days=30)  # Fetch data from the last 30 days
        end_time = datetime.datetime.now()
        historical_data = self.get_historical_data(start_time, end_time)
        
        # Use historical data for training the model
        if not historical_data.empty:
            X_train = np.array(historical_data[['ambient_temperature', 'cloudiness', 'bell_curve_adjustment', 'greenhouse_temperature']])
            print("Training Feature Dimensions:", X_train.shape)
            print("Training Feature Types:", X_train.dtype)
            y_train = np.array(historical_data['greenhouse_temperature'])  # Target variable
            model.fit(X_train, y_train)  # Fit the model with historical data
        else:
            self.log("Failed to fetch historical data for training the model")

    def get_historical_data(self, start_time, end_time):
        # Fetch historical cloudiness data
        cloudiness_data = self.get_cloudiness_data(start_time, end_time)
        
        # Fetch historical outside temperature data
        ambient_temperature_data = self.get_historical_outside_temperature_data(start_time, end_time, OUTSIDE_TEMPERATURE_SENSOR)
        
        # Fetch historical greenhouse temperature data
        greenhouse_temperature_data = self.get_historical_greenhouse_temperature_data(start_time, end_time, GREENHOUSE_TEMPERATURE_SENSOR)
        
        # Impute missing values in greenhouse_temperature with the mean
        greenhouse_temperature_data = pd.Series(greenhouse_temperature_data)
        greenhouse_temperature_data.fillna(greenhouse_temperature_data.mean(), inplace=True)
        greenhouse_temperature_data = greenhouse_temperature_data.tolist()
        
        # Ensure all lists are of the same length
        min_length = min(len(ambient_temperature_data), len(cloudiness_data), len(greenhouse_temperature_data))
        ambient_temperature_data = ambient_temperature_data[:min_length]
        cloudiness_data = cloudiness_data[:min_length]
        hourly_forecast = []  # Define the variable "hourly_forecast"
                
        greenhouse_temperature_data = greenhouse_temperature_data[:min_length]

        # Apply bell curve adjustment to each hour in the cloudiness data
        bell_curve_adjustment = [self.adjust_temperature_bell_curve(hour, hourly_forecast) for hour in cloudiness_data[:min_length]]

        # Combine data into a DataFrame
        historical_data = pd.DataFrame({
            'ambient_temperature': ambient_temperature_data,
            'cloudiness': cloudiness_data,
            'bell_curve_adjustment': bell_curve_adjustment,
            'greenhouse_temperature': greenhouse_temperature_data
        })

        # Log the generated features
        self.log("Generated features for historical data: {}".format(historical_data.columns.tolist()))
        self.log("Historical data size: {}".format(historical_data.shape))
        self.log("Historical data sample:\n{}".format(historical_data.head().to_string(index=False)))
    
        
        # Drop rows with missing values
        historical_data.dropna(inplace=True)
        
        return historical_data
        
    def process_forecast(self, hourly_forecast_today):
        for hour_data in hourly_forecast_today:
            self.log(f"Processing forecast data for {hour_data['dt']}")

    def fetch_and_process_forecast(self, kwargs=None):
        self.log("Fetching and processing forecast")
        latitude = float(self.get_state('zone.home', attribute='latitude'))
        longitude = float(self.get_state('zone.home', attribute='longitude'))
        
        # Get today's date
        today = datetime.datetime.now().date()
        
        # Get the current hour
        current_hour = datetime.datetime.now().hour
        
        # Calculate the remaining hours of the current day
        remaining_hours_today = 24 - current_hour
        
        # Fetch forecast data from OpenWeatherMap API
        weather_data = self.fetch_weather_forecast(latitude, longitude)
        if weather_data is None:
            self.log("Failed to fetch weather forecast data")
            return
        
        # Filter out hourly forecast data for the remaining hours of today based on 'dt' field
        hourly_forecast_today = [hour_data for hour_data in weather_data['hourly'] if parse(hour_data['dt']).date() == today and parse(hour_data['dt']).hour >= current_hour][:remaining_hours_today]

        # Check if any forecast data is available for the current day
        if hourly_forecast_today:
            # Process the forecast for today
            self.process_forecast(hourly_forecast_today)
            
            # Further processing as needed
        else:
            self.log("No forecast data available for the current day")


        # Get greenhouse temperature
        greenhouse_temperature_state = self.get_state(GREENHOUSE_TEMPERATURE_SENSOR)
        if greenhouse_temperature_state is not None:
            greenhouse_temperature = float(greenhouse_temperature_state)
        else:
            self.log("Failed to fetch current greenhouse temperature data")
            return

        # Ensure greenhouse_temperature has the same number of rows as forecast_X_imputed[:remaining_hours_today]
        greenhouse_temperature = np.full((forecast_X_imputed.shape[0], 1), greenhouse_temperature)

        # Generate bell_curve_adjustment for the remaining hours of the current day
        forecast_hours = np.array(range(current_hour, 24))
        bell_curve_adjustment = [self.adjust_temperature_bell_curve(hour) for hour in forecast_hours]
        
        # Convert bell_curve_adjustment to a numpy array and reshape it
        bell_curve_adjustment = np.array(bell_curve_adjustment).reshape(-1, 1)
        
        # Log the generated features
        self.log(f"Generated features for forecast data: {['ambient_temperature', 'cloudiness', 'bell_curve_adjustment', 'greenhouse_temperature']}")
        self.log(f"Forecast data size: {forecast_X_imputed.shape}")
        self.log(f"Forecast data sample: {forecast_X_imputed[:5]}")

        # Add print statements to check the shapes of the arrays
        print("Shape of forecast_X_imputed:", forecast_X_imputed.shape)
        print("Shape of bell_curve_adjustment:", bell_curve_adjustment.shape)

        # Concatenate the arrays
        forecast_X_imputed = np.hstack((forecast_X_imputed, bell_curve_adjustment))

        self.log(f"Shape of forecast_X_imputed: {forecast_X_imputed.shape}")
     

        # Log the generated features
        self.log(f"Generated features for forecast data: {['ambient_temperature', 'cloudiness', 'bell_curve_adjustment', 'greenhouse_temperature']}")
        self.log(f"Forecast data size: {forecast_X_imputed.shape}")
        self.log(f"Forecast data sample: {forecast_X_imputed[:5]}")
        
        self.log(f"Shape of forecast_X_imputed: {forecast_X_imputed.shape}")

        # Check the shape of forecast_X_imputed
        if forecast_X_imputed.shape[1] != 4:
            raise ValueError(f"Expected 4 features, but got {forecast_X_imputed.shape[1]}")
        
        # If the shape is correct, proceed with prediction
        predicted_temperature = model.predict(forecast_X_imputed)

        
        # Ensure forecast_X_imputed has the correct shape
        if forecast_X_imputed.shape[1] != 4:
            self.log("forecast_X_imputed does not have the correct number of features")
            # Add missing features here
            missing_features = 4 - forecast_X_imputed.shape[1]
            for _ in range(missing_features):
                forecast_X_imputed = np.hstack((forecast_X_imputed, np.zeros((forecast_X_imputed.shape[0], 1))))
        else:
            # Log the forecast_X_imputed data
            self.log(f"forecast_X_imputed: {forecast_X_imputed}")
            
            # Predict temperature using the trained model
            print("Shape of forecast_X_imputed before prediction:", forecast_X_imputed.shape)
            print("Data types of forecast_X_imputed before prediction:", forecast_X_imputed.dtype)
            predicted_temperature = model.predict(forecast_X_imputed)

        # Filter out hourly forecast data for the remaining hours of today based on 'dt' field
        hourly_forecast_today = [hour_data for hour_data in weather_data['hourly'] if parse(hour_data['dt']).hour >= current_hour][:remaining_hours_today]

        # Process the forecast for today
        self.process_forecast(hourly_forecast_today)

        # Aggregate daily cloudiness data from forecast
        daily_cloudiness = self.aggregate_daily_cloudiness(weather_data)

        # Get real-time cloud coverage data
        current_cloudiness = float(self.get_state('sensor.openweathermap_forecast_cloud_coverage'))
        
        # Fetch forecast data and process it
        forecast_X = pd.DataFrame(daily_cloudiness, columns=['cloudiness'])
        forecast_X.loc[len(forecast_X)] = [current_cloudiness]  # Add real-time cloudiness
        
        # Impute missing values in forecast_X
        imputer = SimpleImputer(strategy='mean')
        forecast_X_imputed = imputer.fit_transform(forecast_X)
    
        # Predict temperature using the trained model
        predicted_temperature = model.predict(forecast_X_imputed)
        
        # Use the real-time cloud coverage and forecast data for prediction
        forecast_X = pd.DataFrame(daily_cloudiness, columns=['cloudiness'])
        forecast_X['temperature'] = np.nan  # Initialize temperature column

        # Fetch historical temperature data
        start_time = datetime.datetime.now() - datetime.timedelta(days=30)  # Fetch data from the last 30 days
        end_time = datetime.datetime.now()
        historical_temperature_data = self.get_temperature_data(start_time, end_time)
        
        # Fetch historical cloudiness data
        start_time = datetime.datetime.now() - datetime.timedelta(days=30)  # Fetch data from the last 30 days
        end_time = datetime.datetime.now()
        historical_cloudiness_data = self.get_cloudiness_data(start_time, end_time)

        
        # Use historical temperature data for training the model
        if historical_temperature_data:
            X_train = np.array(historical_temperature_data).reshape(-1, 1)
            y_train = np.array(historical_temperature_data)  # Use historical temperature data as target variable for training
            model.fit(X_train, y_train)  # Fit the model with historical data
        
            # Predict temperature using the trained model
            predicted_temperature = model.predict(forecast_X)
            predicted_temperature = np.clip(predicted_temperature, a_min=LOW_TEMPERATURE_THRESHOLD, a_max=HIGH_TEMPERATURE_THRESHOLD)  # Ensure that the predicted temperature is within a reasonable range
            self.log(f"Predicted temperature: {predicted_temperature}")

            # Calculate forecast quota multiplier
            greenhouse_temperature = np.mean(predicted_temperature)
            humidity = float(self.get_state(GREENHOUSE_HUMIDITY_SENSOR))
            cloudiness = float(self.get_state('sensor.openweathermap_forecast_cloud_coverage'))
            hour = datetime.datetime.now().hour
            forecast_quota_multiplier = self.calculate_quota_multiplier(greenhouse_temperature, humidity, cloudiness, hour)

            # Handle NoneType for current greenhouse temperature
            current_temperature_state = self.get_state(GREENHOUSE_TEMPERATURE_SENSOR)
            if current_temperature_state is not None:
                current_temperature = float(current_temperature_state)
            else:
                self.log("Failed to fetch current greenhouse temperature data")
                return
        
            current_humidity = float(self.get_state(GREENHOUSE_HUMIDITY_SENSOR))
            current_hour = datetime.datetime.now().hour
            current_cloudiness = float(self.get_state('sensor.openweathermap_forecast_cloud_coverage'))
            current_quota_multiplier = self.calculate_quota_multiplier(current_temperature, current_humidity, current_cloudiness, current_hour)

            # Use predicted temperature, forecast quota multiplier, and current quota multiplier to schedule irrigation
            self.schedule_irrigation(predicted_temperature, forecast_quota_multiplier, current_quota_multiplier)

    def fetch_weather_forecast(self, latitude, longitude):
        api_key = "f8da86d4bbb696f7f2f703a23b0eb31f"
        weather_url = f"https://api.openweathermap.org/data/3.0/onecall?lat={latitude}&lon={longitude}&exclude=minutely,daily,alerts&appid={api_key}&units=metric"
        weather_data = self.fetch_data_from_url(weather_url)
        if weather_data is not None:
            formatted_forecast = []
            for hour_data in weather_data.get("hourly", []):
                # Convert 'dt' field to integer
                hour_data['dt'] = int(hour_data.get("dt", ""))
                # Convert Unix timestamp to datetime object
                timestamp = hour_data.get("dt", "")
                dt_object = datetime.datetime.utcfromtimestamp(timestamp)
                
                # Format datetime object as YYYY-MM-DD HH:MM
                formatted_timestamp = dt_object.strftime('%Y-%m-%d %H:%M')
                
                # Replace the Unix timestamp with the formatted timestamp
                hour_data['dt'] = formatted_timestamp
                formatted_forecast.append(hour_data)
                
                temp = hour_data.get("temp", "")  # Temperature
                humidity = hour_data.get("humidity", "")  # Humidity
                clouds = hour_data.get("clouds", "")  # Cloudiness
                # Access other weather parameters as needed
            return {"hourly": formatted_forecast}
        else:
            self.log("Failed to fetch weather data")
            return None

    def process_weather_data(self, weather_data):
        # Initialize lists to store temperature and cloudiness data
        temperature_data = []
        cloudiness_data = []
    
        # Iterate over hourly data in the weather data
        for hour_data in weather_data['hourly']:
            # Extract temperature and cloudiness data
            temperature = hour_data['temp']
            cloudiness = hour_data['clouds']
    
            # Append data to the respective lists
            temperature_data.append(temperature)
            cloudiness_data.append(cloudiness)
    
        # Convert lists to numpy arrays
        temperature_data = np.array(temperature_data)
        cloudiness_data = np.array(cloudiness_data)
    
        # Reshape data to 2D arrays
        temperature_data = temperature_data.reshape(-1, 1)
        cloudiness_data = cloudiness_data.reshape(-1, 1)
    
        # Combine temperature and cloudiness data into a single array
        forecast_X = np.concatenate((temperature_data, cloudiness_data), axis=1)
    
        # Use SimpleImputer to fill any missing values
        imputer = SimpleImputer(strategy='mean')
        forecast_X_imputed = imputer.fit_transform(forecast_X)
    
        return forecast_X, forecast_X_imputed
    
    def fetch_data_from_url(self, url):
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            return None

    def aggregate_daily_cloudiness(self, weather_data):
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

    def get_historical_greenhouse_temperature_data(self, start_time, end_time, sensor_name):
        try:
            # Get the historical data from the sensor
            history = self.get_history(entity_id=GREENHOUSE_TEMPERATURE_SENSOR, start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values from the history
                data = [float(state['state']) for state in history[0] if state['state'] not in ['unknown', 'unavailable']]
                #self.log(f"Historical greenhouse temperature data: {data}")  # Add this line to log the data
            else:
                data = []
        except Exception as e:
            self.log(f"Error getting temperature data: {e}")
            data = []
            
        return data
    
    def get_historical_outside_temperature_data(self, start_time, end_time, sensor_name):
        try:
            # Get the historical data from the sensor
            history = self.get_history(entity_id=OUTSIDE_TEMPERATURE_SENSOR, start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values from the history
                data = [float(state['state']) for state in history[0] if state['state'] not in ['unknown', 'unavailable']]
                #self.log(f"Historical outside temperature data: {data}")  # Add this line to log the data
            else:
                data = []
        except Exception as e:
            self.log(f"Error getting temperature data: {e}")
            data = []
            
        return data


    def get_cloudiness_data(self, start_time, end_time):
        try:
            # Get historical cloud coverage data from the sensor
            history = self.get_history(entity_id='sensor.openweathermap_cloud_coverage', start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values from the history
                data = [float(state['state']) for state in history[0] if state['state'] not in ['unknown', 'unavailable']]
            else:
                data = []
        except Exception as e:
            self.log(f"Error getting cloudiness data: {e}")
            data = []
                
        return data

    def adjust_temperature_bell_curve(self, hour):
        # Parameters for the bell curve
        mean = 12  # Solar noon
        std_dev = 2  # Standard deviation controls the width of the curve
    
        # Calculate the adjusted temperature based on the bell curve
        temperature_at_hour = np.exp(-0.5 * ((hour - mean) / std_dev) ** 2)
        
        self.log("Setting state for sensor.sensor_greenhouse_intelligent_irrigation")
        self.set_state('sensor.sensor_greenhouse_intelligent_irrigation', state='ON', attributes=hourly_forecast)
        self.log("State set for sensor.sensor_greenhouse_intelligent_irrigation")


    def calculate_hourly_forecast(self, predicted_temperature):
        hourly_forecast = {}
        for i, temp in enumerate(predicted_temperature):
            hour = i % 24  # Hour range from 0 to 23
            hourly_forecast[f"{hour:02}:00-{(hour+1)%24:02}:00"] = temp
        return hourly_forecast

