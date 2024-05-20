import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, timedelta, time  # Correctly import the time class
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

TIMEZONE = 'Europe/Stockholm'
HIGH_TEMPERATURE_THRESHOLD = 30
LOW_TEMPERATURE_THRESHOLD = 10
OUTSIDE_TEMPERATURE_SENSOR = 'sensor.santetorp_rumsgivare_utegivare_temperature'
GREENHOUSE_TEMPERATURE_SENSOR = 'sensor.sensor_i_vaxthuset_temperature'
GREENHOUSE_HUMIDITY_SENSOR = 'sensor.sensor_i_vaxthuset_humidity'

class intelligent_irrigation_forecasting(hass.Hass):
    
    def initialize(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.log("Initializing Intelligent Irrigation Forecasting...")
        self.log(f"Current system time: {datetime.now(timezone(TIMEZONE))}")
        
        try:
            self.model = LinearRegression()  # Create the model object here
            self.log("LinearRegression model created")
            
            self.get_forecast_data()  # Run the forecast function initially
            
            # Schedule get_forecast_data to run daily at 04:00
            runtime = time(4, 0, 0)  # Use time from datetime module
            self.log(f"Scheduling get_forecast_data to run daily at {runtime}")
            self.run_daily(self.get_forecast_data, runtime)
            
        except Exception as e:
            self.log(f"Error during initialization: {e}", level="ERROR")
        
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
    def train_model_and_predict(self, forecast_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        self.log(f"Model state before training: {self.model}")
        # Get the current time and round down to the nearest hour
        now = pd.Timestamp.now().floor('H')
        # Fetch historical data for training the model
        start_time = datetime.now() - timedelta(days=30)  # Fetch data from the last 30 days
        # Adjust end_time to be the previous hour
        end_time = now - pd.Timedelta(hours=1)

        # If end_time is earlier than start_time, set it to start_time
        end_time = max(end_time, start_time)
        
        # Prepare the historical data DataFrame
        historical_data = self.prepare_historical_DataFrame(start_time, end_time)
        # Fetch and process historical data
        historical_data = self.get_historical_data(start_time, end_time, historical_data)

        # Use historical data for training the model
        if not historical_data.empty:
            # Create a copy of the DataFrame
            historical_data_copy = historical_data.copy()
        
            # Ensure the index is a datetime index
            historical_data_copy.index = pd.to_datetime(historical_data_copy.index)
        
            # Extract hour, day and month from timestamp using .loc to avoid SettingWithCopyWarning
            historical_data_copy.loc[:, 'year'] = historical_data_copy.index.year
            historical_data_copy.loc[:, 'month'] = historical_data_copy.index.month
            historical_data_copy.loc[:, 'day_of_month'] = historical_data_copy.index.day
            historical_data_copy.loc[:, 'hour_of_day'] = historical_data_copy.index.hour
        
            X_train = historical_data_copy[['year', 'month', 'day_of_month', 'hour_of_day', 'ambient_temperature', 'cloudiness',  'solar_azimuth', 'solar_elevation']]
            y_train = historical_data_copy['greenhouse_temperature']  # Target variable
            
            # Fit the model with historical data
            self.model.fit(X_train, y_train)
            
            # If weather data is provided, make a prediction
            if forecast_data is not None:
                try:
                    # Check if the index is already a DateTimeIndex
                    isinstance(forecast_data.index, pd.DatetimeIndex)
                    
                    # Predict the temperatures
                    predicted_temperature = self.model.predict(forecast_data)
                    #predicted_temperature = np.clip(predicted_temperature, a_min=, a_max=)
                    
                    # Create a DataFrame with the predicted temperatures
                    predicted_temperature_df = pd.DataFrame(predicted_temperature, columns=['predicted_greenhouse_temperature'])
                    
                    # Round the predicted temperatures to two decimal places
                    predicted_temperature_df['predicted_greenhouse_temperature'] = predicted_temperature_df['predicted_greenhouse_temperature'].round(2)
                    
                    # Create a timestamp column in predicted_temperature_df from the year, month, day_of_month, and hour_of_day columns in forecast_data
                    predicted_temperature_df['timestamp'] = pd.to_datetime(forecast_data['year'].astype(str) + '-' + forecast_data['month'].astype(str).str.zfill(2) + '-' + forecast_data['day_of_month'].astype(str).str.zfill(2) + ' ' + forecast_data['hour_of_day'].astype(str).str.zfill(2) + ':00:00')
                    
                    # Rearrange the columns
                    predicted_temperature_df = predicted_temperature_df[['timestamp', 'predicted_greenhouse_temperature']]
                    
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
        
        # Get the current time and round down to the nearest hour
        now = pd.Timestamp.now().floor('H')

        # Adjust end_time to be the previous hour
        end_time = now - pd.Timedelta(hours=1)

        # If end_time is earlier than start_time, set it to start_time
        end_time = max(end_time, start_time)
    
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
        
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    
        return historical_data



    def get_historical_data(self, start_time, end_time, historical_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")

        # Create a temporary copy of historical_data and rename columns
        temp_data = historical_data[['year', 'month', 'day_of_month', 'hour_of_day']].copy()
        temp_data.columns = ['year', 'month', 'day', 'hour']
        
        # Create timestamps directly without storing them
        timestamps = pd.to_datetime(temp_data)
        
        # Set start_time as the earliest timestamp and end_time as the latest timestamp
        start_time = timestamps.min()
        end_time = timestamps.max()
        
        # Log  end_time
        self.log(f" start_time in {inspect.currentframe().f_code.co_name}: {start_time}")
        self.log(f" end_time in {inspect.currentframe().f_code.co_name}: {end_time}")
    
        # Prepare the DataFrame foundation
        #historical_data = self.prepare_historical_DataFrame(start_time, end_time) # Moved to train_model_and_predict
        
        # Extract the latitude and longitude of the home zone
        latitude = float(self.get_state('zone.home', attribute='latitude'))
        longitude = float(self.get_state('zone.home', attribute='longitude'))
        
        # Round start_time to the nearest hour
        start_time = start_time.replace(minute=0, second=0, microsecond=0)
    
        # Fetch historical greenhouse temperature data
        self.log("Fetching historical greenhouse temperature data...")
        historical_data = self.get_historical_greenhouse_temperature_data(historical_data, GREENHOUSE_TEMPERATURE_SENSOR)
        self.log(f"Historical data after historical greenhouse temperature: {historical_data.tail(12).to_string()}")

        # Fetch historical outside temperature data
        self.log("Fetching historical outside temperature data...")
        historical_data = self.get_historical_outside_temperature_data(historical_data, OUTSIDE_TEMPERATURE_SENSOR)
        self.log(f"Historical data after historical outside temperature: {historical_data.tail(12).to_string()}")

        # Fetch historical cloudiness data
        self.log("Fetching historical cloudiness data...")
        historical_data = self.get_historical_cloudiness_data(historical_data)
    
        # Fetch historical solar data
        self.log("Fetching historical solar data...")
        historical_data = self.get_historical_solar_data(historical_data)
        
        # Log the historical data
        self.log(f"Historical data after get_historical_data: {historical_data.tail(12).to_string()}")
        
        # Store historical_data as an instance variable
        self.historical_data = historical_data
        
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
        return historical_data
    
    def get_historical_greenhouse_temperature_data(self, historical_data, sensor_name):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        # Create a temporary copy of historical_data and rename columns
        temp_data = historical_data[['year', 'month', 'day_of_month', 'hour_of_day']].copy()
        temp_data.columns = ['year', 'month', 'day', 'hour']
        
        # Create timestamps directly without storing them
        timestamps = pd.to_datetime(temp_data)
        
        # Set start_time as the earliest timestamp and end_time as the latest timestamp
        start_time = timestamps.min()
        end_time = timestamps.max()
         
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
               
                # Extract 'year', 'month', 'day', and 'hour' from 'timestamp'
                data['year'] = data['timestamp'].dt.year
                data['month'] = data['timestamp'].dt.month
                data['day_of_month'] = data['timestamp'].dt.day
                data['hour_of_day'] = data['timestamp'].dt.hour
                
                # Drop the 'timestamp' column
                data = data.drop(columns=['timestamp'])
                
                # Rearrange the columns
                data = data[['year', 'month', 'day_of_month', 'hour_of_day', 'greenhouse_temperature']]
                
                # Group by 'year', 'month', 'day_of_month', 'hour_of_day' and take the average temperature for each group
                data = data.groupby(['year', 'month', 'day_of_month', 'hour_of_day']).agg({'greenhouse_temperature': 'mean'}).reset_index()
                
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

                
                # Round the greenhouse_temperature to 2 decimal places
                historical_data['greenhouse_temperature'] = historical_data['greenhouse_temperature'].round(2)
                             
                # Return the updated historical_data
                self.log(f"Historical data before return: {historical_data.tail(12).to_string()}")
                return historical_data
            else:
                self.log("No historical data found.")
                return None
        except Exception as e:
            self.log(f"Error getting temperature data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def get_historical_outside_temperature_data(self, historical_data, sensor_name):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        # Create a temporary copy of historical_data and rename columns
        temp_data = historical_data[['year', 'month', 'day_of_month', 'hour_of_day']].copy()
        temp_data.columns = ['year', 'month', 'day', 'hour']
        
        # Create timestamps directly without storing them
        timestamps = pd.to_datetime(temp_data)
        
        # Set start_time as the earliest timestamp and end_time as the latest timestamp
        start_time = timestamps.min()
        end_time = timestamps.max()
        
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
                
                # Extract 'year', 'month', 'day', and 'hour' from 'timestamp'
                data['year'] = data['timestamp'].dt.year
                data['month'] = data['timestamp'].dt.month
                data['day_of_month'] = data['timestamp'].dt.day
                data['hour_of_day'] = data['timestamp'].dt.hour
                
                # Drop the 'timestamp' column
                data = data.drop(columns=['timestamp'])
                
                # Rearrange the columns
                data = data[['year', 'month', 'day_of_month', 'hour_of_day', 'ambient_temperature']]
                
                # Group by 'year', 'month', 'day_of_month', 'hour_of_day' and take the average ambient_temperature for each group
                data = data.groupby(['year', 'month', 'day_of_month', 'hour_of_day']).agg({'ambient_temperature': 'mean'}).reset_index()
                
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
               
                # Return the updated historical_data
                return historical_data
            else:
                self.log("No historical data found.")
                return None
        except Exception as e:
            self.log(f"Error getting ambient_temperature data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

    def get_historical_cloudiness_data(self, historical_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        # Create a temporary copy of historical_data and rename columns
        temp_data = historical_data[['year', 'month', 'day_of_month', 'hour_of_day']].copy()
        temp_data.columns = ['year', 'month', 'day', 'hour']
        
        # Create timestamps directly without storing them
        timestamps = pd.to_datetime(temp_data)
        
        # Set start_time as the earliest timestamp and end_time as the latest timestamp
        start_time = timestamps.min()
        end_time = timestamps.max()
        
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
                
                # Extract 'year', 'month', 'day', and 'hour' from 'timestamp'
                data['year'] = data['timestamp'].dt.year
                data['month'] = data['timestamp'].dt.month
                data['day_of_month'] = data['timestamp'].dt.day
                data['hour_of_day'] = data['timestamp'].dt.hour
                
                # Drop the 'timestamp' column
                data = data.drop(columns=['timestamp'])
                
                # Rearrange the columns
                data = data[['year', 'month', 'day_of_month', 'hour_of_day', 'cloudiness']]
                
                # Group by 'year', 'month', 'day_of_month', 'hour_of_day' and take the average cloudiness for each group
                data = data.groupby(['year', 'month', 'day_of_month', 'hour_of_day']).agg({'cloudiness': 'mean'}).reset_index()
                
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
                 
                # Return the updated historical_data
                return historical_data
            else:
                self.log("No historical data found.")
                return None
        except Exception as e:
            self.log(f"Error getting cloudiness data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")


    def get_historical_solar_data(self, historical_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        
        # Create a temporary copy of historical_data and rename columns
        temp_data = historical_data[['year', 'month', 'day_of_month', 'hour_of_day']].copy()
        temp_data.columns = ['year', 'month', 'day', 'hour']
        
        # Create timestamps directly without storing them
        timestamps = pd.to_datetime(temp_data)
        
        # Set start_time as the earliest timestamp and end_time as the latest timestamp
        start_time = timestamps.min()
        end_time = timestamps.max()
        
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
     
            # Return the updated historical_data
            return historical_data
        except Exception as e:
            self.log(f"Error getting solar data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")


    def get_forecast_solar_data(self, forecast_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        try:
            # Get forecast solar_data
            # Extract the latitude and longitude of the home zone
            latitude = float(self.get_state('zone.home', attribute='latitude'))
            longitude = float(self.get_state('zone.home', attribute='longitude'))
    
            for i, row in forecast_data.iterrows():
                timestamp_string = f"{str(row['year'])}-{str(row['month']).zfill(2)}-{str(row['day_of_month']).zfill(2)} {str(row['hour_of_day']).zfill(2)}:00:00"
                solar_info = self.fetch_solar_data(latitude, longitude, timestamp_string)
    
                if solar_info:
                    try:
                        # Unpack the solar data
                        solar_azimuth, solar_elevation = solar_info
    
                        # Assign the solar data to the current row
                        forecast_data.at[i, 'solar_azimuth'] = solar_azimuth
                        forecast_data.at[i, 'solar_elevation'] = solar_elevation
                    except ValueError:
                        self.log(f"Invalid solar_data value: {solar_info}")
     
            # Return the updated forecast_data
            return forecast_data
        except Exception as e:
            self.log(f"Error getting solar data: {e}")
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
        

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
    def get_weather_forecast_data(self, latitude, longitude):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
        self.log("Fetching hourly forecast from OpenWeatherMap")
        api_key = "f8da86d4bbb696f7f2f703a23b0eb31f"
        weather_url = f"https://api.openweathermap.org/data/3.0/onecall?lat={latitude}&lon={longitude}&exclude=minutely,daily,alerts&appid={api_key}&units=metric"
        weather_data = self.fetch_data_from_url(weather_url)
        if weather_data is not None:
            self.log("Weather data fetched successfully.")
            return weather_data
        else:
            self.log("Failed to fetch weather data")
            self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
            return None
        
    def fetch_data_from_url(self, url):
        import requests
        response = requests.get(url)
        return response.json()
    
    def prepare_forecast_DataFrame(self, weather_data):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
    
        # Extract start_time and end_time from the weather data
        start_time = pd.to_datetime(weather_data['hourly'][0].get("dt", ""), unit='s')
        end_time = pd.to_datetime(weather_data['hourly'][-1].get("dt", ""), unit='s')
    
        # Process weather forecast data
        timestamps, temperatures, cloudiness = self.process_weather_forecast_data(weather_data)

        # Generate timestamps for each hour between start_time and end_time
        timestamp = pd.date_range(start=start_time, end=end_time, freq='H')

        # Initialize an empty DataFrame with the required columns
        forecast_data = pd.DataFrame(columns=['year', 'month', 'day_of_month', 'hour_of_day', 'ambient_temperature', 'cloudiness', 'solar_azimuth', 'solar_elevation'])

        # Extract year, month, day_of_month, and hour_of_day from timestamps using .loc to avoid SettingWithCopyWarning
        forecast_data.loc[:, 'year'] = timestamp.year.tolist()
        forecast_data.loc[:, 'month'] = timestamp.month.tolist()
        forecast_data.loc[:, 'day_of_month'] = timestamp.day.tolist()
        forecast_data.loc[:, 'hour_of_day'] = timestamp.hour.tolist()

        # Fill in the 'ambient_temperature' and 'cloudiness' columns with the processed weather data
        forecast_data.loc[:, 'ambient_temperature'] = temperatures
        forecast_data.loc[:, 'cloudiness'] = cloudiness
    
        # Ensure the DataFrame has the correct number of rows
        num_rows = len(timestamp)
        forecast_data = forecast_data.reindex(range(num_rows))
     
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")
    
        return forecast_data
    
    def get_forecast_data(self):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")

        # Fetch the latitude and longitude of the home zone
        latitude = float(self.get_state('zone.home', attribute='latitude'))
        longitude = float(self.get_state('zone.home', attribute='longitude'))

        # Fetch forecast weather data
        weather_data = self.get_weather_forecast_data(latitude, longitude)

        # Prepare the DataFrame foundation
        forecast_data = self.prepare_forecast_DataFrame(weather_data)
        
        # Define start_time and end_time
        start_time = forecast_data.index[0]
        end_time = forecast_data.index[-1]

        # Fetch forecast solar data
        forecast_data = self.get_forecast_solar_data(forecast_data)

        # Train the model and capture the return value
        predicted_temperature_df = self.train_model_and_predict(forecast_data)
        
        # Call create_daily_temperature_dataframe with predicted_temperature_df as argument
        self.create_daily_temperature_dataframe(predicted_temperature_df)

        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")

        return forecast_data

    def process_weather_forecast_data(self, weather_data):
        timestamps = [pd.to_datetime(item['dt'], unit='s') for item in weather_data['hourly']]
        temperatures = [item['temp'] for item in weather_data['hourly']]
        cloudiness = [item['clouds'] for item in weather_data['hourly']]
        
        return timestamps, temperatures, cloudiness
    
    
    def create_daily_temperature_dataframe(self, predicted_temperature_df):
        # Get the current day
        today = pd.Timestamp.now().normalize()
    
        # Get the current hour
        current_hour = pd.Timestamp.now().hour

        self.log(f"self.historical_data : {(self.historical_data).tail(12).to_string()}")
        
        # Filter out specific columns from the historical data
        historical_data_filtered = self.historical_data[['year', 'month', 'day_of_month', 'hour_of_day', 'greenhouse_temperature']].copy()
        self.log(f"historical_data_filtered : {(historical_data_filtered).tail(12).to_string()}")
        
        # Convert 'year', 'month', 'day_of_month', 'hour_of_day' to datetime and set as index
        historical_data_filtered.rename(columns={'day_of_month': 'day', 'hour_of_day': 'hour'}, inplace=True)
        historical_data_filtered.loc[:, 'timestamp'] = pd.to_datetime(historical_data_filtered[['year', 'month', 'day', 'hour']])
        historical_data_filtered.set_index('timestamp', inplace=True)
        self.log(f"historical_data_filtered : {(historical_data_filtered).tail(12).to_string()}")
        
        # Filter out data that is not from today or is in the future
        historical_data_today = historical_data_filtered.loc[today:today + pd.DateOffset(days=1, hours=-1)]
        self.log(f"historical_data_today : {(historical_data_today).tail(12).to_string()}")
        
        # Prepare predicted_temperature_df
        self.log(f"Predicted data: {(predicted_temperature_df).tail(12).to_string()}")
        predicted_temperature_df_copy = predicted_temperature_df.copy()
        predicted_temperature_df_copy.rename(columns={'predicted_greenhouse_temperature': 'greenhouse_temperature'}, inplace=True)
    
        # Convert 'timestamp' to datetime if it's not already
        predicted_temperature_df_copy['timestamp'] = pd.to_datetime(predicted_temperature_df_copy['timestamp'])
    
        # Extract 'year', 'month', 'day', 'hour' from 'timestamp'
        predicted_temperature_df_copy['year'] = predicted_temperature_df_copy['timestamp'].dt.year
        predicted_temperature_df_copy['month'] = predicted_temperature_df_copy['timestamp'].dt.month
        predicted_temperature_df_copy['day'] = predicted_temperature_df_copy['timestamp'].dt.day
        predicted_temperature_df_copy['hour'] = predicted_temperature_df_copy['timestamp'].dt.hour
    
        predicted_temperature_df_copy.set_index('timestamp', inplace=True)
    
        # Filter out data that is not from today or is in the past
        predicted_temperature_df_today = predicted_temperature_df_copy.loc[today + pd.DateOffset(hours=current_hour):today + pd.DateOffset(days=1, hours=-1)]
    
        # Combine the DataFrames
        df_combined = pd.concat([historical_data_today, predicted_temperature_df_today])
    
        # Calculate the mean of the greenhouse temperatures for the current day
        self.greenhouse_daily_mean_temperature = round(df_combined['greenhouse_temperature'].mean(), 2)
    
        # Call set_sensor_state with the required arguments
        self.set_sensor_state(predicted_temperature_df_copy, df_combined)
    
        return df_combined

    def set_sensor_state(self, predicted_temperature_df, df_combined):
        self.log(f"Entered {inspect.currentframe().f_code.co_name}")
    
        # Ensure that the index is a datetime index
        df_combined.index = pd.to_datetime(df_combined.index)
    
        # Format df_combined as desired
        df_combined['timestamp'] = df_combined.index.strftime('%Y-%m-%d %H:%M')
        df_combined['greenhouse_temperature'] = df_combined['greenhouse_temperature'].apply(lambda x: f"{x:.2f}°C")
    
        # Convert Timestamp objects to strings and format them as date and hour interval
        daily_temperature_dict = {
            f"{key.strftime('%Y-%m-%d %H:%M')}-{(key + pd.Timedelta(hours=1)).strftime('%H:%M')}": value
            for key, value in df_combined['greenhouse_temperature'].to_dict().items()
        }
    
        # Set the sensor state
        self.set_state('sensor.sensor_greenhouse_intelligent_irrigation_forecasting', state='ON', attributes={
            'daily_temperatures': daily_temperature_dict,
            'last_updated': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
            'daily_mean_temperature': f"{self.greenhouse_daily_mean_temperature:.2f}°C"
        })
    
        self.log(f"Leaving {inspect.currentframe().f_code.co_name}")