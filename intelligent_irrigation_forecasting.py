import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, timedelta, time
from dateutil.parser import parse
import requests
import math
import numpy as np
import pandas as pd
import inspect
import ephem
from pytz import timezone
from ephem import Observer, Sun
from sklearn.linear_model import LinearRegression
from sklearn.impute import SimpleImputer

HIGH_TEMPERATURE_THRESHOLD = 30
LOW_TEMPERATURE_THRESHOLD = 10
OUTSIDE_TEMPERATURE_SENSOR = 'sensor.santetorp_rumsgivare_utegivare_temperature'
GREENHOUSE_TEMPERATURE_SENSOR = 'sensor.sensor_i_vaxthuset_temperature'
GREENHOUSE_HUMIDITY_SENSOR = 'sensor.sensor_i_vaxthuset_humidity'

class intelligent_irrigation_forecasting(hass.Hass):
    
    def initialize(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.log("Initializing Intelligen Irrigation Forecasting...")
        self.model = LinearRegression()  # Create the model object here
        self.run_forecast()  # Run the forecast function
        self.train_model_and_predict() # Train the model with historical data
        #self.run_forecast() # Run the forecast function
        #self.run_hourly(self.train_model_and_predict, time(0, 0, 0))   # Train the model every hour
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def train_model_and_predict(self, forecast_X_imputed, weather_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        self.log(f"Model state before training: {self.model}")
        
        # Fetch historical data for training the model
        start_time = datetime.now() - timedelta(days=30)  # Fetch data from the last 30 days
        end_time = datetime.now()
        historical_data = self.get_historical_data(start_time, end_time)
        
        # Use historical data for training the model
        if not historical_data.empty:
            # Ensure the index is a datetime index
            historical_data.index = pd.to_datetime(historical_data.index)
        
            # Extract hour, day and month from timestamp using .loc to avoid SettingWithCopyWarning
            historical_data.loc[:, 'year'] = historical_data.index.year
            historical_data.loc[:, 'month'] = historical_data.index.month
            historical_data.loc[:, 'day_of_month'] = historical_data.index.day
            historical_data.loc[:, 'hour_of_day'] = historical_data.index.hour

        
            X_train = historical_data[['year', 'month', 'day_of_month', 'hour_of_day', 'ambient_temperature', 'cloudiness',  'solar_azimuth', 'solar_elevation']]
            y_train = historical_data['greenhouse_temperature']  # Target variable
            
            # Fit the model with historical data
            self.model.fit(X_train, y_train)
            
            # If weather data is provided, make a prediction
            if weather_data is not None:
                try:
                    # Convert the index to a datetime index
                    forecast_X_imputed.index = pd.to_datetime(forecast_X_imputed.index)
                    
                    # Extracting necessary date-time features from the index
                    forecast_X_imputed['year'] = forecast_X_imputed.index.year
                    forecast_X_imputed['month'] = forecast_X_imputed.index.month
                    forecast_X_imputed['day_of_month'] = forecast_X_imputed.index.day  # changed 'day' to 'day_of_month'
                    forecast_X_imputed['hour_of_day'] = forecast_X_imputed.index.hour  # changed 'hour' to 'hour_of_day'
                    
                    predicted_temperature = self.model.predict(forecast_X_imputed)
                    self.log(f"First 24 rows of predicted_temperature: {predicted_temperature[:24]}")
                    predicted_temperature = np.clip(predicted_temperature, a_min=LOW_TEMPERATURE_THRESHOLD, a_max=HIGH_TEMPERATURE_THRESHOLD)  # Ensure that the predicted temperature is within a reasonable range
                    
                    # Create a DataFrame with the predicted temperatures and timestamps
                    predicted_temperature_df = pd.DataFrame(predicted_temperature, index=forecast_X_imputed.index, columns=['predicted_temperature'])
                    self.log(f"First 24 rows of predicted_temperature along with timestamps: \n{predicted_temperature_df.head(24)}")
                    
                    self.log(f"Model state training training: {self.model}")
                    
                    # Check if the DataFrame is empty
                    if predicted_temperature_df.empty:
                        self.log("The predicted temperature DataFrame is empty.")
                        self.log(f"Leaving {inspect.currentframe().f_code.co_name}  with empty DataFrame error")
                        self.log("Exiting method due to empty DataFrame")  # New log statement
                        return None
                    else:
                        # Log the predicted temperature
                        self.log("Returning the predicted temperature DataFrame...")
                        self.log(f"Leaving {inspect.currentframe().f_code.co_name} with success")

                    return predicted_temperature_df
                    
                except Exception as e:
                    self.log(f"Error predicting temperature: {e}")
                    self.log(f"Leaving {inspect.currentframe().f_code.co_name} with exception error")
                    self.log("Exiting method due to exception")  # New log statement
                    return None
        else:
            self.log("Failed to fetch historical data for training the model")
            self.log(f"Leaving {inspect.currentframe().f_code.co_name} with failed fetching error")
            self.log("Exiting method due to failed data fetch")  # New log statement
            return None
    
# Historical section start
    def prepare_historical_DataFrame(self, start_time, end_time):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        # Generate timestamps for each hour between start_time and end_time
        timestamp = pd.date_range(start=start_time, end=end_time, freq='H')
        
        # Initialize an empty DataFrame with the required columns
        historical_data = pd.DataFrame(columns=['year', 'month', 'day_of_month', 'hour_of_day', 'ambient_temperature', 'cloudiness', 'greenhouse_temperature', 'solar_azimuth', 'solar_elevation'])

        # Extract year, month, day_of_month, and hour_of_day from timestamps using .loc to avoid SettingWithCopyWarning
        historical_data.loc[:, 'year'] = timestamp.year.to_list()
        historical_data.loc[:, 'month'] = timestamp.month.to_list()
        historical_data.loc[:, 'day_of_month'] = timestamp.day.to_list()
        historical_data.loc[:, 'hour_of_day'] = timestamp.hour.to_list()


        # Ensure the DataFrame has the correct number of rows
        num_rows = len(timestamp)
        historical_data = historical_data.reindex(range(num_rows))
        
        # Log the last 12 rows of the prepared DataFrame with all features for inspection
        self.log(f"Historical DataFrame tail:\n{historical_data.tail(24).to_string()}")

        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

        return historical_data



    def get_historical_data(self, start_time, end_time):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")

        # Prepare the DataFrame foundation
        historical_data = self.prepare_historical_DataFrame(start_time, end_time)
        
        # Extract the latitude and longitude of the home zone
        latitude = float(self.get_state('zone.home', attribute='latitude'))
        longitude = float(self.get_state('zone.home', attribute='longitude'))
        
        # Round start_time to the nearest hour
        start_time = start_time.replace(minute=0, second=0, microsecond=0)

        # Fetch historical greenhouse temperature data
        self.log("Fetching historical greenhouse temperature data...")
        historical_data = self.get_historical_greenhouse_temperature_data(start_time, end_time, GREENHOUSE_TEMPERATURE_SENSOR, historical_data)
        self.log(f"Greenhouse temperature data:\n{historical_data.tail(24).to_string()}")

        # Fetch historical outside temperature data
        self.log("Fetching historical outside temperature data...")
        historical_data = self.get_historical_outside_temperature_data(start_time, end_time, OUTSIDE_TEMPERATURE_SENSOR, historical_data)
        self.log(f"Outside temperature data:\n{historical_data.tail(24).to_string()}")

        # Fetch historical cloudiness data
        self.log("Fetching historical cloudiness data...")
        historical_data = self.get_historical_cloudiness_data(start_time, end_time, historical_data)
        self.log(f"Cloudiness data:\n{historical_data.tail(24).to_string()}")

        # Fetch historical solar data
        self.log("Fetching historical solar data...")
        historical_data = self.get_historical_solar_data(start_time, end_time, historical_data)
        self.log(f"Solar data:\n{historical_data.tail(24).to_string()}")

        # Combine year, month, day_of_month, and hour_of_day columns into a datetime column
        #historical_data['timestamp'] = pd.to_datetime(historical_data[['year', 'month', 'day_of_month', 'hour_of_day']])
        
        # Merge fetched data with the existing DataFrame based on timestamp
        #historical_data = pd.merge(historical_data, greenhouse_temperature_data, on='timestamp', how='left')
        #historical_data = pd.merge(historical_data, ambient_temperature_data, on='timestamp', how='left')
        #historical_data = pd.merge(historical_data, cloudiness_data, on='timestamp', how='left')
        #historical_data = pd.merge(historical_data, solar_data, on='timestamp', how='left')

        # Log the last 12 rows of the updated DataFrame with all features for inspection
        self.log(f"Historical DataFrame tail:\n{historical_data.tail(24).to_string()}")
        
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

        return historical_data
    
    def get_historical_greenhouse_temperature_data(self, start_time, end_time, sensor_name, historical_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Get the historical data from the sensor
            history = self.get_history(entity_id=GREENHOUSE_TEMPERATURE_SENSOR, start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values and the associated timestamps from the history
                data = []
                for state in history[0]:
                    if state['state'] not in ['unknown', 'unavailable']:
                        try:
                            timestamp = pd.to_datetime(state['last_changed'])
                            greenhouse_temperature = float(state['state'])
                            data.append((timestamp, greenhouse_temperature))
                        except ValueError:
                            self.log(f"Invalid temperature value: {state['state']}")
                    
                # Convert the data to a DataFrame
                data = pd.DataFrame(data, columns=['timestamp', 'greenhouse_temperature'])
                
                # Log the DataFrame created
                self.log(f"DataFrame created: {data}")
                self.log(f"DataFrame (first few rows):\n{data.head().to_string()}")
                
                # Extract 'year', 'month', 'day', and 'hour' from 'timestamp'
                data['year'] = data['timestamp'].dt.year
                data['month'] = data['timestamp'].dt.month
                data['day_of_month'] = data['timestamp'].dt.day
                data['hour_of_day'] = data['timestamp'].dt.hour
                
                # Drop the 'timestamp' column
                data = data.drop(columns=['timestamp'])
                
                # Rearrange the columns
                data = data[['year', 'month', 'day_of_month', 'hour_of_day', 'greenhouse_temperature']]
                
                # Log the DataFrame created
                self.log(f"DataFrame dateformat: {data}")
                self.log(f"DataFrame with dateformat(first few rows):\n{data.tail(24).to_string()}")
                
                # Group by 'year', 'month', 'day_of_month', 'hour_of_day' and take the average temperature for each group
                data = data.groupby(['year', 'month', 'day_of_month', 'hour_of_day']).agg({'greenhouse_temperature': 'mean'}).reset_index()
                
                # Log the DataFrame created
                self.log(f"DataFrame grouped data(first few rows):\n{data.tail(24).to_string()}")
                
                # Merge historical_data with data on ['year', 'month', 'day_of_month', 'hour_of_day']
                historical_data = historical_data.merge(data, on=['year', 'month', 'day_of_month', 'hour_of_day'], how='left', suffixes=('', '_new'))
                
                # Update 'greenhouse_temperature' in historical_data with the corresponding values from 'greenhouse_temperature_new'
                historical_data['greenhouse_temperature'].update(historical_data['greenhouse_temperature_new'])
                
                # Drop the 'greenhouse_temperature_new' column
                historical_data.drop(columns=['greenhouse_temperature_new'], inplace=True)
                
                # Fill NaN values using forward fill followed by backward fill
                historical_data['greenhouse_temperature'] = historical_data['greenhouse_temperature'].ffill().bfill()

                # Interpolate remaining missing data in historical_data using linear method
                self.log("Interpolating remaining missing data in historical_data using linear method")
                historical_data['greenhouse_temperature'] = historical_data['greenhouse_temperature'].interpolate(method='linear')

                # Round the greenhouse_temperature to 2 decimal places
                historical_data['greenhouse_temperature'] = historical_data['greenhouse_temperature'].round(2)
                
                # Log the DataFrame after interpolation
                self.log(f"DataFrame after interpolation:\n{historical_data.tail(24).to_string()}")
                
                # Log all the column names
                self.log(f"DataFrame columns: {historical_data.columns.tolist()}")
                
                # Return the updated historical_data
                return historical_data
            else:
                self.log("No historical data found.")
                return None
        except Exception as e:
            self.log(f"Error getting temperature data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def get_historical_outside_temperature_data(self, start_time, end_time, sensor_name, historical_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Get the historical data from the sensor
            history = self.get_history(entity_id=OUTSIDE_TEMPERATURE_SENSOR, start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values and the associated timestamps from the history
                data = []
                for state in history[0]:
                    if state['state'] not in ['unknown', 'unavailable']:
                        try:
                            timestamp = pd.to_datetime(state['last_changed'])
                            ambient_temperature = float(state['state'])
                            data.append((timestamp, ambient_temperature))
                        except ValueError:
                            self.log(f"Invalid ambient_temperature value: {state['state']}")
                    
                # Convert the data to a DataFrame
                data = pd.DataFrame(data, columns=['timestamp', 'ambient_temperature'])
                
                # Log the DataFrame created
                self.log(f"DataFrame created: {data}")
                self.log(f"DataFrame (first few rows):\n{data.head().to_string()}")
                
                # Extract 'year', 'month', 'day', and 'hour' from 'timestamp'
                data['year'] = data['timestamp'].dt.year
                data['month'] = data['timestamp'].dt.month
                data['day_of_month'] = data['timestamp'].dt.day
                data['hour_of_day'] = data['timestamp'].dt.hour
                
                # Drop the 'timestamp' column
                data = data.drop(columns=['timestamp'])
                
                # Rearrange the columns
                data = data[['year', 'month', 'day_of_month', 'hour_of_day', 'ambient_temperature']]
                
                # Log the DataFrame created
                self.log(f"DataFrame dateformat: {data}")
                self.log(f"DataFrame with dateformat(first few rows):\n{data.tail(24).to_string()}")
                
                # Group by 'year', 'month', 'day_of_month', 'hour_of_day' and take the average ambient_temperature for each group
                data = data.groupby(['year', 'month', 'day_of_month', 'hour_of_day']).agg({'ambient_temperature': 'mean'}).reset_index()
                
                # Log the DataFrame created
                self.log(f"DataFrame grouped data(first few rows):\n{data.tail(24).to_string()}")
                
                # Merge historical_data with data on ['year', 'month', 'day_of_month', 'hour_of_day']
                historical_data = historical_data.merge(data, on=['year', 'month', 'day_of_month', 'hour_of_day'], how='left', suffixes=('', '_new'))
                
                # Update 'ambient_temperature' in historical_data with the corresponding values from 'ambient_temperature'
                historical_data['ambient_temperature'].update(historical_data['ambient_temperature_new'])
                
                # Drop the 'ambient_temperature_new' column
                historical_data.drop(columns=['ambient_temperature_new'], inplace=True)
                
                # Fill NaN values using forward fill followed by backward fill
                historical_data['ambient_temperature'] = historical_data['ambient_temperature'].ffill().bfill()

                # Interpolate remaining missing data in historical_data using linear method
                self.log("Interpolating remaining missing data in historical_data using linear method")
                historical_data['ambient_temperature'] = historical_data['ambient_temperature'].interpolate(method='linear')

                # Round the ambient_temperature to 2 decimal places
                historical_data['ambient_temperature'] = historical_data['ambient_temperature'].round(2)
                
                # Log the DataFrame after interpolation
                self.log(f"DataFrame after interpolation:\n{historical_data.tail(24).to_string()}")
                
                # Log all the column names
                self.log(f"DataFrame columns: {historical_data.columns.tolist()}")
                
                # Return the updated historical_data
                return historical_data
            else:
                self.log("No historical data found.")
                return None
        except Exception as e:
            self.log(f"Error getting ambient_temperature data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def get_historical_cloudiness_data(self, start_time, end_time, historical_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Get historical cloud coverage data from the sensor
            history = self.get_history(entity_id='sensor.openweathermap_cloud_coverage', start_time=start_time, end_time=end_time)
            
            # Check if history is not empty
            if history:
                # Extract the 'state' values and the associated timestamps from the history
                data = []
                for state in history[0]:
                    if state['state'] not in ['unknown', 'unavailable']:
                        try:
                            timestamp = pd.to_datetime(state['last_changed'])
                            cloudiness = float(state['state'])
                            data.append((timestamp, cloudiness))
                        except ValueError:
                            self.log(f"Invalid cloudiness value: {state['state']}")
                    
                # Convert the data to a DataFrame
                data = pd.DataFrame(data, columns=['timestamp', 'cloudiness'])
                
                # Log the DataFrame created
                self.log(f"DataFrame created: {data}")
                self.log(f"DataFrame (first few rows):\n{data.head().to_string()}")
                
                # Extract 'year', 'month', 'day', and 'hour' from 'timestamp'
                data['year'] = data['timestamp'].dt.year
                data['month'] = data['timestamp'].dt.month
                data['day_of_month'] = data['timestamp'].dt.day
                data['hour_of_day'] = data['timestamp'].dt.hour
                
                # Drop the 'timestamp' column
                data = data.drop(columns=['timestamp'])
                
                # Rearrange the columns
                data = data[['year', 'month', 'day_of_month', 'hour_of_day', 'cloudiness']]
                
                # Log the DataFrame created
                self.log(f"DataFrame dateformat: {data}")
                self.log(f"DataFrame with dateformat(first few rows):\n{data.tail(24).to_string()}")
                
                # Group by 'year', 'month', 'day_of_month', 'hour_of_day' and take the average cloudiness for each group
                data = data.groupby(['year', 'month', 'day_of_month', 'hour_of_day']).agg({'cloudiness': 'mean'}).reset_index()
                
                # Log the DataFrame created
                self.log(f"DataFrame grouped data(first few rows):\n{data.tail(24).to_string()}")
                
                # Merge historical_data with data on ['year', 'month', 'day_of_month', 'hour_of_day']
                historical_data = historical_data.merge(data, on=['year', 'month', 'day_of_month', 'hour_of_day'], how='left', suffixes=('', '_new'))
                
                # Update 'cloudiness' in historical_data with the corresponding values from 'cloudiness'
                historical_data['cloudiness'].update(historical_data['cloudiness_new'])
                
                # Drop the 'cloudiness_new' column
                historical_data.drop(columns=['cloudiness_new'], inplace=True)
                
                # Fill NaN values using forward fill followed by backward fill
                historical_data['cloudiness'] = historical_data['cloudiness'].ffill().bfill()

                # Interpolate remaining missing data in historical_data using linear method
                self.log("Interpolating remaining missing data in historical_data using linear method")
                historical_data['cloudiness'] = historical_data['cloudiness'].interpolate(method='linear')

                # Round the ambient_temperature to 2 decimal places
                historical_data['cloudiness'] = historical_data['cloudiness'].round(2)
                
                # Log the DataFrame after interpolation
                self.log(f"DataFrame after interpolation:\n{historical_data.tail(24).to_string()}")
                
                # Log all the column names
                self.log(f"DataFrame columns: {historical_data.columns.tolist()}")
                
                # Return the updated historical_data
                return historical_data
            else:
                self.log("No historical data found.")
                return None
        except Exception as e:
            self.log(f"Error getting cloudiness data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")


    def get_historical_solar_data(self, start_time, end_time, historical_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Get historical solar_data
            # Extract the latitude and longitude of the home zone
            latitude = float(self.get_state('zone.home', attribute='latitude'))
            longitude = float(self.get_state('zone.home', attribute='longitude'))
    
            for i, row in historical_data.iterrows():
                timestamp_string = f"{str(row['year'])}-{str(row['month']).zfill(2)}-{str(row['day_of_month']).zfill(2)} {str(row['hour_of_day']).zfill(2)}:00:00"
                solar_info = self.fetch_solar_data(latitude, longitude, timestamp_string)
    
                if solar_info:
                    try:
                        # Unpack the solar data
                        solar_azimuth, solar_elevation = solar_info
    
                        # Assign the solar data to the current row
                        historical_data.at[i, 'solar_azimuth'] = solar_azimuth
                        historical_data.at[i, 'solar_elevation'] = solar_elevation
                    except ValueError:
                        self.log(f"Invalid solar_data value: {solar_info}")
    
            # Log the DataFrame after updating solar data
            self.log(f"DataFrame after updating solar data:\n{historical_data.tail(24).to_string()}")
    
            # Return the updated historical_data
            return historical_data
        except Exception as e:
            self.log(f"Error getting solar data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")


    def get_forecast_solar_data(self, forecast_X_imputed):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        # Extract the latitude and longitude of the home zone
        latitude = float(self.get_state('zone.home', attribute='latitude'))
        longitude = float(self.get_state('zone.home', attribute='longitude'))
        
        # Predict temperature using the trained model
        solar_azimuth, solar_elevation = zip(*[self.fetch_solar_data(latitude, longitude, f"{year}-{month:02d}-{day_of_month:02d} {hour_of_day:02d}:00:00") for year, month, day_of_month, hour_of_day in zip(forecast_X_imputed['year'], forecast_X_imputed['month'], forecast_X_imputed['day_of_month'], forecast_X_imputed['hour_of_day'])])
        
        forecast_X_imputed['solar_azimuth'] = solar_azimuth
        forecast_X_imputed['solar_elevation'] = solar_elevation

        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return forecast_X_imputed
        

    # Fetch solar data - azimuth and elevation
    # Solar data is used to determine the position of the sun in the sky
    # The position of the sun is used to determine the amount of sunlight that reaches the greenhouse
    # fetch_solar_data is used for both historical and forecast data
    def fetch_solar_data(self, latitude, longitude, timestamp_string):
        # Create an observer object for the specified location
        observer = ephem.Observer()
        observer.lat = str(latitude)
        observer.lon = str(longitude)

        # Create a timezone object for your local timezone
        local_tz = timezone('Europe/Stockholm')

        # Check if timestamp_string is a list
        if isinstance(timestamp_string, list):
            solar_data = []
            for ts in timestamp_string:
                # Convert the timestamp string to a datetime object
                timestamp_utc = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

                # Adjust the timestamp for daylight saving time
                local_dt = local_tz.localize(timestamp_utc)
                if local_dt.dst() != timedelta(0):
                    local_dt = local_dt - timedelta(hours=1)

                # Set the date of the observer to the adjusted timestamp
                observer.date = local_dt.strftime("%Y/%m/%d %H:%M:%S")

                # Calculate solar position
                sun = Sun()
                sun.compute(observer)

                # Extract azimuth and elevation
                solar_azimuth = math.degrees(float(sun.az))  # Azimuth in degrees
                solar_elevation = math.degrees(float(sun.alt))  # Elevation in degrees

                solar_data.append((solar_azimuth, solar_elevation))

            return solar_data
        else:
            # Convert the timestamp string to a datetime object
            timestamp_utc = datetime.strptime(timestamp_string, "%Y-%m-%d %H:%M:%S")

            # Adjust the timestamp for daylight saving time
            local_dt = local_tz.localize(timestamp_utc)
            if local_dt.dst() != timedelta(0):
                local_dt = local_dt - timedelta(hours=1)

            # Set the date of the observer to the adjusted timestamp
            observer.date = local_dt.strftime("%Y/%m/%d %H:%M:%S")

            # Calculate solar position
            sun = Sun()
            sun.compute(observer)

            # Extract azimuth and elevation
            solar_azimuth = math.degrees(float(sun.az))  # Azimuth in degrees
            solar_elevation = math.degrees(float(sun.alt))  # Elevation in degrees

            return solar_azimuth, solar_elevation


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
        
        forecast_X_imputed = self.get_forecast_solar_data(forecast_X_imputed)
        
        # Train the model
        self.train_model_and_predict(forecast_X_imputed, weather_data)

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
            self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
            return None

        
    def fetch_data_from_url(self, url):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
            return None
        
    def create_daily_temperature_dataframe(self, predicted_temperature_df):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        # Get the current day
        today = pd.Timestamp.now().normalize()

        # Get the historical data
        start_time = today  # start of the current day
        end_time = today + pd.Timedelta(days=1, seconds=-1)  # end of the current day at 23:59:59 
        self.historical_data = self.get_historical_data(start_time, end_time)
        #self.log(f"Historical data: {self.historical_data}")

        # Filter out specific columns from the historical data
        self.historical_data = self.historical_data[['year', 'month', 'day_of_month', 'hour_of_day', 'greenhouse_temperature']]
        #self.log(f"Filtered historical data: {self.historical_data}")

        # Convert 'year', 'month', 'day_of_month', 'hour_of_day' to datetime format and set as index for historical_data
        self.historical_data['timestamp'] = pd.to_datetime(self.historical_data[['year', 'month', 'day_of_month', 'hour_of_day']])
        self.historical_data.set_index('timestamp', inplace=True)

        # Convert 'timestamp' to datetime format and set as index for predicted_temperature
        predicted_temperature_df['timestamp'] = pd.to_datetime(predicted_temperature_df[['year', 'month', 'day_of_month', 'hour_of_day']])
        predicted_temperature_df.set_index('timestamp', inplace=True)

        # Combine the DataFrames
        df_combined = self.historical_data.combine_first(predicted_temperature_df)
        # Filter df_combined to only include rows where the timestamp is on the current day
        df_combined = df_combined[df_combined.index.date == today.date()]

        # Calculate the mean of the greenhouse temperatures for the current day
        self.greenhouse_daily_mean_temperature = round(df_combined['greenhouse_temperature'].mean(), 2)
        #self.log(f"Mean greenhouse temperature for the current day: {self.greenhouse_daily_mean_temperature}")        

        # Call set_sensor_state with the required arguments
        self.set_sensor_state(predicted_temperature_df, df_combined)

        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return df_combined

    def process_weather_forecast_data(self, weather_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.log("Processing weather forecast data...")
        if 'hourly' not in weather_data:
            self.log("'hourly' key not found in weather data.")
            return None
        timestamps = []
        temperatures = []
        cloudiness = []
        for hour_data in weather_data['hourly']:
            timestamp = hour_data.get("dt", "")  # Unix timestamp
            temperature = hour_data.get("temp", "")  # Temperature
            humidity = hour_data.get("humidity", "")  # Humidity
            clouds = hour_data.get("clouds", "")  # Cloudiness
            timestamp = pd.to_datetime(timestamp, unit='s')  # Convert Unix timestamp to datetime object
            timestamps.append(timestamp)
            temperatures.append(temperature)
            cloudiness.append(clouds)
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return timestamps, temperatures, cloudiness

    def prepare_forecast_DataFrame(self, weather_data, kwargs=None):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        today = datetime.now().date()
        current_hour = datetime.now().hour
        remaining_hours_today = 24 - current_hour
        self.log("Processing weather data...")
        timestamps, temperatures, cloudiness = self.process_weather_forecast_data(weather_data)
        if timestamps is None or temperatures is None or cloudiness is None:
            self.log("Failed to process weather data")
            return
    
        forecast_X_imputed = pd.DataFrame({
            'year': [timestamp.year for timestamp in timestamps],
            'month': [timestamp.month for timestamp in timestamps],
            'day_of_month': [timestamp.day for timestamp in timestamps],
            'hour_of_day': [timestamp.hour for timestamp in timestamps],
            'ambient_temperature': temperatures,
            'cloudiness': cloudiness
        })
        forecast_X_imputed['ambient_temperature'].interpolate(method='linear', inplace=True)
        forecast_X_imputed['cloudiness'].interpolate(method='linear', inplace=True)
        self.log("Weather data processed successfully.")
        self.log("Shape of forecast_X_imputed: {}".format(forecast_X_imputed.shape))
        if forecast_X_imputed.shape[1] != 6:
            raise ValueError(f"Expected 6 features (year, month, day_of_month, hour_of_day, ambient_temperature, cloudiness), but got {forecast_X_imputed.shape[1]}")
        self.log("Sample of forecast_X_imputed:\n{}".format(forecast_X_imputed.head(12)))
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        return forecast_X_imputed, weather_data, current_hour, remaining_hours_today

    
    def predict_forecast_temperature(self, forecast_X_imputed):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        try:
            # Log before prediction
            self.log("Before prediction: forecast_X_imputed\n{}".format(forecast_X_imputed.head()))

            # Ensure that the data used for prediction has the same features as the data used for training
            predicted_temperature = np.round(self.model.predict(forecast_X_imputed), 2)

            # Log after prediction
            self.log("After prediction: predicted_temperature\n{}".format(predicted_temperature))

            self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        except Exception as e:
            self.log(f"Model prediction failed with error: {e}")
            predicted_temperature = []
        
        if len(predicted_temperature) > 0:
            # Create a DataFrame that contains the timestamps and the corresponding predicted temperatures
            self.predicted_temperature_df = pd.DataFrame({
                'year': forecast_X_imputed['year'],
                'month': forecast_X_imputed['month'],
                'day_of_month': forecast_X_imputed['day_of_month'],
                'hour_of_day': forecast_X_imputed['hour_of_day'],
                'greenhouse_temperature': predicted_temperature
            })
            
            # Log forecast_X_imputed and predicted_temperature
            self.log("forecast_X_imputed:\n{}".format(forecast_X_imputed.head(12)))  # Display the first 10 rows
            self.log("predicted_temperature:\n{}".format(self.predicted_temperature_df.head(12)))

            # Log predicted_temperature_df
            self.log("predicted_temperature_df:\n{}".format(self.predicted_temperature_df.head(12)))
            
            # Update daily temperature data
            # Update daily temperature data by passing predicted_temperature_df
            self.create_daily_temperature_dataframe(self.predicted_temperature_df)
            self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        else:
            self.log("Failed to predict temperature")
            self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
            return

    def set_sensor_state(self, predicted_temperature_df, df_combined):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")

        # Fetch the current values of  predicted_temperature
        predicted_temperature = getattr(self, 'get_predicted_temperature', None)

        # Format df_combined as desired
        df_combined['timestamp'] = df_combined.index.strftime('%Y-%m-%d %H:%M:%S')
        df_combined['greenhouse_temperature'] = df_combined['greenhouse_temperature'].apply(lambda x: f"{x:.2f}°C")

        # Convert Timestamp objects to strings and format them as date and hour interval
        daily_temperature_dict = {
            f"{pd.to_datetime(key).strftime('%Y-%m-%d %H:%M:%S')}-{(pd.to_datetime(key) + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')}": value
            for key, value in df_combined['greenhouse_temperature'].to_dict().items()
        }

        # Set the sensor state
        self.set_state('sensor.sensor_greenhouse_intelligent_irrigation_forecasting', state='ON', attributes={
            'daily_temperatures': daily_temperature_dict,
            'last_updated': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
            'daily_mean_temperature': f"{self.greenhouse_daily_mean_temperature:.2f}°C"
        })
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

