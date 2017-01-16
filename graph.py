import numpy
import pandas as pd
import requests

from csv import DictReader
from datetime import datetime, timedelta
from ggplot import *
from StringIO import StringIO

def generate_image_for_location(location, num_days):
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
    adjust = timedelta(days=15*365)
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
        'mint': [int(row[2]) for row in parsed_results],
        'maxt': [int(row[1]) for row in parsed_results],
        'Cooling': [int(row[4]) for row in parsed_results],
        'Heating': [int(row[3]) for row in parsed_results],
        'Cooling (LY)': [
            int(
                days.get(
                    row[-1].strftime(time_fmt),
                    '00000'
                ).get(
                    row[-1].year - 1,
                    '00000'
                )[4]
            ) for row in parsed_results
        ],
        'Heating (LY)': [
            int(
                days.get(
                    row[-1].strftime(time_fmt),
                    '00000'
                ).get(
                    row[-1].year - 1,
                    '00000'
                )[3]
            ) for row in parsed_results
        ],
        'Cooling (5YA)': [
            numpy.mean(
                [
                    int(
                        days.get(
                            row[-1].strftime(time_fmt),
                            '00000'
                        ).get(year, '00000')[4]
                    ) for year in range(row[-1].year - 6, row[-1].year - 1)
                ]
            ) for row in parsed_results
        ],
        'Heating (5YA)': [
            numpy.mean(
                [
                    int(
                        days.get(
                            row[-1].strftime(time_fmt),
                            '00000'
                        ).get(year, '00000')[3]
                    ) for year in range(row[-1].year - 6, row[-1].year - 1)
                ]
            ) for row in parsed_results
        ],
        'Cooling (10YA)': [
            numpy.mean(
                [
                    int(
                        days.get(
                            row[-1].strftime(time_fmt),
                            '00000'
                        ).get(year, '00000')[4]
                    ) for year in range(row[-1].year - 11, row[-1].year - 1)
                ]
            ) for row in parsed_results
        ],
        'Heating (10YA)': [
            numpy.mean(
                [
                    int(
                        days.get(
                            row[-1].strftime(time_fmt),
                            '00000'
                        ).get(year, '00000')[3]
                    ) for year in range(row[-1].year - 11, row[-1].year - 1)
                ]
            ) for row in parsed_results
        ],
        'dd': [int(row[3]) + int(row[4]) for row in parsed_results],
    }

    df = pd.DataFrame(chart_data)

    filtered_df = df[df['date'] > filtered_begin_date]

    image = ggplot(
            pd.melt(
                filtered_df, id_vars=['date'], value_vars=[
                    'Cooling',
                    'Cooling (LY)',
                    'Cooling (10YA)',
                    'Heating',
                    'Heating (LY)',
                    'Heating (10YA)'
                ], var_name='DD Type'
            ),
            aes(x='date', y='value', color='DD Type')) +\
        geom_line() + scale_x_date(labels = date_format(time_fmt)) +\
        theme_bw() + xlab("Date") + ylab("Degree Days") +\
        scale_color_manual(values=['darkblue', 'lightblue', 'blue', 'darkred', 'pink', 'red']) +\
        ggtitle("Degree Days for %s, Last %d Days vs Historic" % (
            result['meta']['name'], num_days))

    image.save('/Users/abraham.epton/Downloads/%s_%d_dd.png' % (location, num_days))


if __name__ == '__main__':
    key = '19i_H7oA_fkJR5aU4FdeoInlOuI9-hwWqx9E-9TvH6To'
    url = 'https://docs.google.com/spreadsheets/d/%s/pub?gid=0&single=true&output=csv' % key
    locations = requests.get(url)
    for row in DictReader(StringIO(locations.text)):
        print 'Generating %s, %s' % (row['Station'], row['Period'])
        generate_image_for_location(row['Station'], int(row['Period']))


