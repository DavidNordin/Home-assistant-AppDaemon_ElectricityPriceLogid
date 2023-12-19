# Author: David Nordin
# Description: This App calculates the two-day mean price for each hour and classifies it into one of five classes.
# The classification is based on the two-day mean price's position in the distribution of all two-day mean prices.
# The classification is then used to set the state of the sensor 'sensor.Electricity_TwoDay_classification'.
# The classification of each hour is also set as an attribute of the sensor.
# The App also prints the two-day mean price and classification for each hour in the AppDaemon log.
# The App is intended to be used with the Nordpool sensor (
# https://www.home-assistant.io/integrations/nordpool/).
      
import hassapi as hass
import csv
from datetime import datetime, timedelta
from dateutil.parser import parse

class ReadPriceData(hass.Hass):

  def initialize(self):
    self.current_data = None
    self.next_data = None
    self.read_price_data(None)  # Run immediately on start
    next_hour = (datetime.now().replace(minute=0, second=0) + timedelta(hours=1))
    self.run_hourly(self.read_price_data, next_hour)

  def read_price_data(self, kwargs):
    file_path = '/homeassistant/price_ranges.csv'
    with open(file_path, 'r') as file:
      reader = csv.reader(file)
      next(reader)  # Skip the header row

      current_hour = datetime.now().hour
      for row in reader:
        timestamp = parse(row[0])
        hour = timestamp.hour
        if hour == current_hour:
          self.current_data = self.parse_row(row)
        elif hour == current_hour + 1:
          self.next_data = self.parse_row(row)
          break

      if self.current_data and self.next_data:
        adjustment = self.interpolate(self.current_data['adjustment'], self.next_data['adjustment'])
        self.set_state("sensor.Heatpump_ThrottleSignal", state=adjustment, attributes={
            "device_class": "measurement",
            "unit_of_measurement": "%",
            "price": self.current_data['price']
        })

  def parse_row(self, row):
    data = row[1].split(',')
    price = float(data[0].split(':')[1].strip())
    adjustment = float(data[2].split(':')[1].strip().replace('%', ''))
    return {'price': price, 'adjustment': adjustment}

  def interpolate(self, start, end):
    current_minute = datetime.now().minute
    current_second = datetime.now().second

    if 52.5 <= current_minute < 60:
      # Last 7.5 minutes of the current hour
      transition_progress = ((current_minute - 52.5) * 60 + current_second) / (7.5 * 60)
      return start + (end - start) * transition_progress
    elif 0 <= current_minute < 7.5:
      # First 7.5 minutes of the next hour
      transition_progress = (current_minute * 60 + current_second) / (7.5 * 60)
      return start + (end - start) * transition_progress
    elif 7.5 <= current_minute < 52.5:
      # Middle of the hour, no transition
      return start