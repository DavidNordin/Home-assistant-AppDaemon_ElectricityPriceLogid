import hassapi as hass
import csv
from datetime import datetime, time
from dateutil.parser import parse

class ReadPriceData(hass.Hass):

  def initialize(self):
    self.run_daily(self.read_price_data, time(0, 0))

  def read_price_data(self, kwargs):
    file_path = '/homeassistant/price_range.csv'
    with open(file_path, 'r') as file:
      reader = csv.reader(file)
      next(reader)  # Skip the header row

      current_hour = datetime.now().hour
      for row in reader:
        timestamp = parse(row[0])
        hour = timestamp.hour
        if hour == current_hour:
          data = row[1].split(',')
          price = data[0].split(':')[1].strip()
          adjustment = data[2].split(':')[1].strip()
          print(f'price: {price}, adjustment: {adjustment}')
          break