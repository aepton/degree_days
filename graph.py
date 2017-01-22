import boto3
import numpy
import pandas as pd
import requests

from csv import DictReader
from datetime import datetime, timedelta
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ggplot import *
from StringIO import StringIO

def generate_image_for_location(location, num_days, email_string):
    url = 'http://data.rcc-acis.org/StnData'

    elems = [
        {
            'name': 'Max Temp',
            'code': 'maxt'
        },
        {
            'name': 'Min Temp',
            'code': 'mint'
        },
        {
            'name': 'Heating Degree Days',
            'code': 'hdd'
        },
        {
            'name': 'Cooling Degree Days',
            'code': 'cdd'
        }
    ]

    period_length = timedelta(days=num_days)
    adjust = timedelta(days=0*365)
    one_day = timedelta(days=1)
    end_date = datetime.today() - one_day
    begin_date = end_date - period_length - adjust
    time_fmt = '%b %d'

    payload = {
        "sid": location,
        "sdate": begin_date.strftime('%Y-%m-%d'),
        "edate": end_date.strftime('%Y-%m-%d'),
        "elems": ','.join([e['code'] for e in elems])
    }

    r = requests.post(url, data=payload)
    result = r.json()

    filtered_begin_date = begin_date + adjust

    days = {}
    for row in result['data']:
        row_date = datetime.strptime(row[0], '%Y-%m-%d')
        key = row_date.strftime(time_fmt)
        if key not in days:
            days[key] = {}
        days[key][row_date.year] = row

    parsed_results = []
    for row in result['data']:
        row.append(datetime.strptime(row[0], '%Y-%m-%d'))
        parsed_results.append(row)

    chart_data = {
        'date': [row[-1] for row in parsed_results],
        'mint': [int(row[2]) if row[2].isdigit() else 0 for row in parsed_results],
        'maxt': [int(row[1]) if row[1].isdigit() else 0 for row in parsed_results],
        'Cooling': [int(row[4]) if row[4].isdigit() else 0 for row in parsed_results],
        'Heating': [int(row[3]) if row[3].isdigit() else 0 for row in parsed_results],
        'dd': [
            int(row[3]) if row[3].isdigit() else 0 +\
            int(row[4]) if row[4].isdigit() else 0 \
            for row in parsed_results
        ]
    }

    df = pd.DataFrame(chart_data)

    filtered_df = df[df['date'] > filtered_begin_date]

    melted = pd.melt(
        filtered_df, id_vars=['date'], value_vars=[
            'Cooling',
            'Heating',
        ], var_name='DD Type'
    )

    image = ggplot(
            melted,
            aes(x='date', y='value', color='DD Type')) +\
        geom_line() + scale_x_date(labels = date_format(time_fmt)) +\
        theme_bw() + xlab("Date") + ylab("Degree Days") +\
        scale_color_manual(values=['blue', 'pink']) +\
        ggtitle("Degree Days for %s, Last %d Days" % (
            result['meta']['name'], num_days))

    image_path = '/Users/abraham.epton/Downloads/%s_%d_dd.png' % (location, num_days)

    image.save(image_path)

    session = boto3.Session(profile_name='abe')
    connection = session.client('ses', 'us-east-1')

    for address in email_string.split(','):
        print 'Emailing %s' % address
        message = MIMEMultipart()
        message['Subject'] = 'Degree Days for %s' % result['meta']['name']
        message['From'] = 'abraham.epton@gmail.com'
        message['To'] = address

        part = MIMEText("Attaching Degree Days for %s, Last %d Days" % (
            result['meta']['name'], num_days))
        message.attach(part)

        part = MIMEImage(open(image_path, 'rb').read())
        part.add_header('Content-Disposition', 'attachment', filename=image_path)
        message.attach(part)

        connection.send_raw_email(
            RawMessage={
                'Data': message.as_string()
            },
            Source=message['From'],
            Destinations=[message['To']])


if __name__ == '__main__':
    key = '19i_H7oA_fkJR5aU4FdeoInlOuI9-hwWqx9E-9TvH6To'
    url = 'https://docs.google.com/spreadsheets/d/%s/pub?gid=0&single=true&output=csv' % key
    locations = requests.get(url)
    for row in DictReader(StringIO(locations.text)):
        print 'Generating %s, %s' % (row['Station'], row['Period'])
        generate_image_for_location(row['Station'], int(row['Period']), row['Emails'])


