import pandas as pd
import requests

from datetime import datetime, timedelta
from ggplot import *

location = 'PIA'

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

period_length = timedelta(days=30)
one_day = timedelta(days=1)
end_date = datetime.today() - one_day
begin_date = end_date - period_length

payload = {
    "sid": location,
    "sdate": begin_date.strftime('%Y-%m-%d'),
    "edate": end_date.strftime('%Y-%m-%d'),
    "elems": ','.join([e['code'] for e in elems])
}

r = requests.post(url, data=payload)
result = r.json()

"""
for row in result['data']:
    print row[0]
    for idx, elem in enumerate(elems):
        print elem['name'], row[idx + 1]
"""

results = {
    'date': [datetime.strptime(row[0], '%Y-%m-%d') for row in result['data']],
    'mint': [int(row[2]) for row in result['data']],
    'maxt': [int(row[1]) for row in result['data']],
    'Cooling': [int(row[4]) for row in result['data']],
    'Heating': [int(row[3]) for row in result['data']],
    'dd': [int(row[3]) + int(row[4]) for row in result['data']],
}

df = pd.DataFrame(results)

image = ggplot(
        pd.melt(df, id_vars=['date'], value_vars=['Cooling', 'Heating'], var_name='DD Type'),
        aes(x='date', y='value', color='DD Type')) +\
    geom_line() + scale_x_date(labels = date_format("%b %d")) +\
    theme_bw() + xlab("Date") + ylab("Degree Days") +\
    ggtitle("Degree Days for %s, Last 30 Days" % location)

#image
image.save('/Users/abraham.epton/Downloads/%s_dd.png' % location)