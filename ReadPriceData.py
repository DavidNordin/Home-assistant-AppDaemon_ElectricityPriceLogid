# ReadPriceData.py
import hassapi as hass
import csv
from datetime import datetime
from dateutil.parser import parse

def read_price_data(file_path):
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
        print(f'Price: {price}, Adjustment: {adjustment}')
        break

# Usage example
file_path = '/homeassistant/price_range.csv'
read_price_data(file_path)