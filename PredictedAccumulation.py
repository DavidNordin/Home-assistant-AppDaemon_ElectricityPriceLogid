import csv

def read_price_data(file_path):
    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header row

        for row in reader:
            timestamp = row[0]
            price = float(row[1].split(':')[1].strip())
            price_range = row[2].split(':')[1].strip()
            adjustment = int(row[3].split(':')[1].strip('%'))

            yield timestamp, price, price_range, adjustment

# Usage example
file_path = '/homeassistant/price_range.csv'
for timestamp, price, price_range, adjustment in read_price_data(file_path):
    # Use the extracted data to control the heat pump
    # You can implement your logic here
    print(f'Timestamp: {timestamp}, Price: {price}, Range: {price_range}, Adjustment: {adjustment}%')



# This idea is tabled for now. I'm not sure if it's worth the effort.
    #2023-12-17