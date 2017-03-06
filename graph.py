import boto3
import locale
import numpy
import pandas as pd
import requests
import spectra

from csv import DictReader
from datetime import datetime, timedelta
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ggplot import *
from StringIO import StringIO

locale.setlocale(locale.LC_ALL, '')

def generate_image_for_location(location, num_days, email_string):
    # Set up request to RCC-ACIS system
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

    # Pick the time periods we're interested in
    period_length = timedelta(days=num_days)
    num_years_for_avg = 10
    num_years = num_years_for_avg + 1 # Make sure we're getting enough data for X-year averages
    adjust = timedelta(days=num_years*365)
    one_day = timedelta(days=1)
    one_year = timedelta(days=1*365)
    end_date = datetime.today() - one_day
    begin_date = end_date - period_length - adjust

    chart_time_fmt = '%b %d'
    row_time_fmt = '%Y-%m-%d'

    payload = {
        "sid": location,
        "sdate": begin_date.strftime(row_time_fmt),
        "edate": end_date.strftime(row_time_fmt),
        "elems": ','.join([e['code'] for e in elems])
    }

    r = requests.post(url, data=payload)
    result = r.json()

    # Reset the begin_date to the window we actually care about (i.e. offset the adjustment)
    filtered_begin_date = begin_date + adjust

    # Create dict keyed on day-of-year with all years' results for that day in another dict
    days = {}
    for row in result['data']:
        row_date = datetime.strptime(row[0], row_time_fmt)
        key = row_date.strftime(chart_time_fmt)
        if key not in days:
            days[key] = {}
        days[key][row_date.year] = row

    # Add a formatted date entry as the last element in each row
    parsed_results = []
    for row in result['data']:
        row.append(datetime.strptime(row[0], row_time_fmt))
        parsed_results.append(row)

    # Create data we can use directly for charts
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

    # Begin setting up email text
    email_text = {
        'html': '<h2>Degree Days report for %s - %s</h2>' % (location, result['meta']['name']),
        'text': 'Degree Days report for %s - %s\n\n' % (location,result['meta']['name'])
    }

    # Set up the color scales we'll use for increasing/decreasing values in text
    light_green = '#a1d99b'
    dark_green = '#00441b'
    light_red = '#fc9272'
    dark_red = '#67000d'
    green_scale = spectra.scale([light_green, dark_green])
    red_scale = spectra.scale([light_red, dark_red])

    # Create a dataframe based on the chart
    df = pd.DataFrame(chart_data)

    def generate_last_days():
        # Compute, and generate text for, last X days this year
        ty_days = {'Cooling': 0, 'Heating': 0}
        dt = end_date + one_day - timedelta(days=num_days)
        while dt <= end_date:
            data = df[df['date']==dt.strftime(row_time_fmt)]
            for key in ty_days.keys():
                ty_days[key] += data[key].values[0]
            dt += one_day
        email_text['text'] += 'Last 30 days: %s HDD, %s CDD\n' % (
            locale.format('%d', ty_days['Heating'], grouping=True),
            locale.format('%d', ty_days['Cooling'], grouping=True)
        )
        email_text['html'] += '<p>Last 30 days: <strong>%s</strong> HDD, <strong>%s</strong> CDD<br>' % (
            locale.format('%d', ty_days['Heating'], grouping=True),
            locale.format('%d', ty_days['Cooling'], grouping=True))

    def generate_last_year_comparison():
        # Compute, and generate text for, same time period last year
        ly_days = {'Cooling': 0, 'Heating': 0}
        dt = end_date + one_day - one_year - timedelta(days=num_days)
        while dt <= (end_date - one_year):
            data = df[df['date']==dt.strftime(row_time_fmt)]
            for key in ly_days.keys():
                ly_days[key] += data[key].values[0]
            dt += one_day
        hdd_change_sign = '+'
        hdd_change_pct = 0.
        if ly_days['Heating']:
            hdd_change_pct = 100. * (
                (float(ty_days['Heating']) - float(ly_days['Heating']))/ly_days['Heating'])
        try:
            hdd_change_color = green_scale(abs(hdd_change_pct/100.)).hexcode
        except:
            hdd_change_color = dark_green
        cdd_change_sign = '-'
        cdd_change_pct = 0.
        if ly_days['Cooling']:
            cdd_change_pct = 100. * (
                (float(ty_days['Cooling']) - float(ly_days['Cooling']))/ly_days['Cooling'])
        try:
            cdd_change_color = green_scale(abs(cdd_change_pct/100.)).hexcode
        except:
            cdd_change_color = dark_green
        if ty_days['Heating'] < ly_days['Heating']:
            try:
                hdd_change_color = red_scale(abs(hdd_change_pct/100.)).hexcode
            except:
                hdd_change_color = dark_red
            hdd_change_sign = ''
        elif ty_days['Heating'] == ly_days['Heating']:
            hdd_change_color = 'black'
            hdd_change_sign = ''
        if ty_days['Cooling'] < ly_days['Cooling']:
            try:
                cdd_change_color = red_scale(abs(cdd_change_pct/100.)).hexcode
            except:
                cdd_change_color = dark_red
            cdd_change_sign = ''
        elif ty_days['Cooling'] == ly_days['Cooling']:
            cdd_change_color = 'black'
            cdd_change_sign = ''
        email_text['text'] += 'Same time period last year: %s HDD (%s%.2f%%), %s CDD (%s%.2f%%)\n' % (
            locale.format('%d', ly_days['Heating'], grouping=True),
            hdd_change_sign,
            hdd_change_pct,
            locale.format('%d', ly_days['Cooling'], grouping=True),
            cdd_change_sign,
            cdd_change_pct
        )
        email_text['html'] += 'Same time period last year: <strong style="color:%s">%s (%s%.2f%%) HDD</strong>, <strong style="color:%s">%s (%s%.2f%%) CDD</strong><br>' % (
            hdd_change_color,
            locale.format('%d', ly_days['Heating'], grouping=True),
            hdd_change_sign,
            hdd_change_pct,
            cdd_change_color,
            locale.format('%d', ly_days['Cooling'], grouping=True),
            cdd_change_sign,
            cdd_change_pct
        )

    def generate_average_days():
        # Compute, and generate text for, average HDD/CDD days for this time period over last X years
        avg_days = {'Cooling': 0, 'Heating': 0}
        divisor = float(num_years_for_avg)
        while num_years_for_avg:
            begin_date = end_date + one_day - timedelta(days=num_years_for_avg*365) - timedelta(days=num_days)
            dt = end_date + one_day - timedelta(days=num_years_for_avg*365) - timedelta(days=num_days)
            while dt <= (end_date - timedelta(days=num_years_for_avg*365)):
                data = df[df['date']==dt.strftime(row_time_fmt)]
                for key in avg_days.keys():
                    avg_days[key] += data[key].values[0]
                dt += one_day
            num_years_for_avg -= 1

        hdd_change_sign = '+'
        hdd_change_value = float(avg_days['Heating'])/float(divisor)
        hdd_change_pct = 0.
        if hdd_change_value:
            hdd_change_pct = 100. * ((float(ty_days['Heating']) - hdd_change_value)/hdd_change_value)
        try:
            hdd_change_color = green_scale(abs(hdd_change_pct/100.)).hexcode
        except:
            hdd_change_color = dark_green
        cdd_change_sign = '-'
        cdd_change_value = float(avg_days['Cooling'])/float(divisor)
        cdd_change_pct = 0.
        if cdd_change_value:
            cdd_change_pct = 100. * ((float(ty_days['Cooling']) - cdd_change_value)/cdd_change_value)
        try:
            cdd_change_color = green_scale(abs(cdd_change_pct/100.)).hexcode
        except:
            cdd_change_color = dark_green
        if ty_days['Heating'] < hdd_change_value:
            try:
                hdd_change_color = red_scale(abs(hdd_change_pct/100.)).hexcode
            except:
                hdd_change_color = dark_red
            hdd_change_sign = ''
        elif ty_days['Heating'] == hdd_change_value:
            hdd_change_color = 'black'
            hdd_change_sign = ''
        if ty_days['Cooling'] < cdd_change_value:
            try:
                cdd_change_color = red_scale(abs(cdd_change_pct/100.)).hexcode
            except:
                cdd_change_color = dark_red
            cdd_change_sign = ''
        elif ty_days['Cooling'] == cdd_change_value:
            cdd_change_color = 'black'
            cdd_change_sign = ''
        email_text['text'] += 'Same time period last ten years (avg): %s HDD (%s%.2f%%), %s CDD (%s%.2f%%)\n' % (
            locale.format('%.1f', hdd_change_value, grouping=True),
            hdd_change_sign,
            hdd_change_pct,
            locale.format('%.1f', cdd_change_value, grouping=True),
            cdd_change_sign,
            cdd_change_pct
        )
        email_text['text'] += 'Deviation from last ten years (avg): %s HDD, %s CDD\n' % (
            locale.format(
                '%.1f',
                ty_days['Heating'] - hdd_change_value,
                grouping=True),
            locale.format(
                '%.1f',
                ty_days['Cooling'] - cdd_change_value,
                grouping=True)
        )
        email_text['html'] += 'Same time period last ten years (avg): <strong style="color:%s">%s (%s%.2f%%) HDD</strong>, <strong style="color:%s">%s (%s%.2f%%) CDD</strong></p>' % (
            hdd_change_color,
            locale.format('%.1f', hdd_change_value, grouping=True),
            hdd_change_sign,
            hdd_change_pct,
            cdd_change_color,
            locale.format('%.1f', cdd_change_value, grouping=True),
            cdd_change_sign,
            cdd_change_pct
        )
        email_text['html'] += 'Deviation from last ten years (avg): <strong>%s</strong> HDD, <strong>%s</strong> CDD</p>' % (
            locale.format(
                '%.1f',
                ty_days['Heating'] - hdd_change_value,
                grouping=True),
            locale.format(
                '%.1f',
                ty_days['Cooling'] - cdd_change_value,
                grouping=True)
        )

    def get_forecast():
        # Now let's get the forecast from NOAA for the next week
        r = requests.get('http://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/hfstwpws.txt')
        forecast_date_sign = 'LAST DATE OF FORECAST WEEK IS '
        for line in r.text.splitlines():
            if line.strip().startswith('ILLINOIS'):
                results = line.split()
            elif line.strip().startswith(forecast_date_sign):
                email_text['text'] += 'Degree Day forecast (statewide), week ending %s\nCourtesy NOAA Climate Prediction Center: http://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/hfstwpws.txt' % line.replace(
                    forecast_date_sign, '').strip()
                email_text['html'] += '<h4>Degree Day forecast (statewide), week ending %s</h4><p>Courtesy <a href="http://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/hfstwpws.txt">NOAA Climate Prediction Center</a></p>' % (
                    line.replace(forecast_date_sign, '').strip())

        if results and len(results) > 4:
            try:
                forecast = int(results[1].replace(',', ''))
                deviation_normal = int(results[2].replace(',', ''))
                deviation_last_year = int(results[3].replace(',', ''))
                deviation_normal_sign = '+'
                deviation_normal_pct = 0.
                deviation_normal_value = float(forecast + -1 * deviation_normal)
                if deviation_normal_value != 0.:
                    deviation_normal_pct = (
                        100. * (float(forecast) - deviation_normal_value)/deviation_normal_value)
                try:
                    deviation_normal_color = green_scale(abs(deviation_normal_pct/100.)).hexcode
                except:
                    deviation_normal_color = dark_green
                deviation_ly_sign = '+'
                deviation_ly_pct = 0.
                deviation_ly_value = float(forecast + -1 * deviation_last_year)
                if deviation_ly_value != 0.:
                    deviation_ly_pct = (
                        100. * (float(forecast) - deviation_ly_value)/deviation_ly_value)
                try:
                    deviation_ly_color = green_scale(abs(deviation_ly_pct/100.)).hexcode
                except:
                    deviation_ly_color = dark_green
                if deviation_normal < 0:
                    deviation_normal_sign = ''
                    try:
                        deviation_normal_color = red_scale(abs(deviation_normal_pct/100.)).hexcode
                    except:
                        deviation_normal_color = dark_red
                elif deviation_normal == 0:
                    deviation_normal_sign = ''
                    deviation_normal_color = 'black'
                if deviation_last_year < 0:
                    deviation_ly_sign = ''
                    try:
                        deviation_ly_color = red_scale(abs(deviation_ly_pct/100.)).hexcode
                    except:
                        deviation_ly_color = dark_red
                elif deviation_last_year == 0:
                    deviation_ly_sign = ''
                    deviation_ly_color = 'black'
                email_text['text'] += 'Forecast: %s\nDeviation from normal: %s (%s%.2f%%)\nDeviation from last year: %s (%s%.2f%%)\n' % (
                    locale.format('%d', forecast, grouping=True),
                    locale.format('%d', deviation_normal, grouping=True),
                    deviation_normal_sign,
                    deviation_normal_pct,
                    locale.format('%d', deviation_last_year, grouping=True),
                    deviation_ly_sign,
                    deviation_ly_pct
                )
                email_text['html'] += '<p>Forecast: <strong>%s</strong> degree days next week<br>Deviation from normal: <strong style="color:%s">%s (%s%.2f%%)</strong> degree days<br>Deviation from last year: <strong style="color:%s">%s (%s%.2f%%)</strong> degree days</p>' % (
                    locale.format('%d', forecast, grouping=True),
                    deviation_normal_color,
                    locale.format('%d', deviation_normal, grouping=True),
                    deviation_normal_sign,
                    deviation_normal_pct,
                    deviation_ly_color,
                    locale.format('%d', deviation_last_year, grouping=True),
                    deviation_ly_sign,
                    deviation_ly_pct
                )
            except Exception, e:
                print e

    def generate_chart_data():
        # Generate day-by-day last-x-years average values for charts
        filtered_df = df.loc[(df['date'] >= filtered_begin_date) & (df['date'] <= end_date), :]
        averages = {}
        avg_years = {
            'ORD': 10,
            'ILX': 10,
            'LOT': 10,
            'PWK': 10,
            'DPA': 10
        }
        num_years_for_avg = avg_years[location]
        for d in filtered_df['date']:
            formatted_date = d.strftime(chart_time_fmt)
            averages[formatted_date] = {'Cooling': 0., 'Heating': 0.}
            numerator = {'Heating': 0., 'Cooling': 0.}
            for year in sorted(days[formatted_date], reverse=True)[:num_years_for_avg]:
                numerator['Heating'] += float(days[formatted_date][year][3]) if days[formatted_date][year][3].isdigit() else 0
                numerator['Cooling'] += float(days[formatted_date][year][4]) if days[formatted_date][year][4].isdigit() else 0
            averages[formatted_date]['Heating'] = numerator['Heating']/float(num_years_for_avg)
            averages[formatted_date]['Cooling'] = numerator['Cooling']/float(num_years_for_avg)

        filtered_df.loc[:, 'Cooling (%dya)' % avg_years[location]] = [
            averages[k.strftime(chart_time_fmt)]['Cooling'] for k in filtered_df['date']]
        filtered_df.loc[:, 'Heating (%dya)' % avg_years[location]] = [
            averages[k.strftime(chart_time_fmt)]['Heating'] for k in filtered_df['date']]

        # Turn multi-column table into essentially list of key-value pairs for chart creation
        melted = pd.melt(
            filtered_df, id_vars=['date'], value_vars=[
                'Cooling',
                'Heating',
                'Cooling (%sya)' % avg_years[location],
                'Heating (%sya)' % avg_years[location]
            ], var_name='DD Type'
        )

        # Generate the image
        image = ggplot(
                melted,
                aes(x='date', y='value', color='DD Type')) +\
            geom_line() + scale_x_date(labels = date_format(chart_time_fmt)) +\
            theme_bw() + xlab("Date") + ylab("Degree Days") +\
            scale_color_manual(values=['lightblue', 'blue', 'purple', 'pink']) +\
            ggtitle("Degree Days for %s, Last %d Days" % (
                result['meta']['name'], num_days))

        image_path = '/tmp/%s_%d_dd.png' % (location, num_days)

        image.save(image_path)

    def generate_send_email():
        # Create and send the email
        session = boto3.Session(profile_name='abe')
        connection = session.client('ses', 'us-east-1')

        for address in email_string.split(','):
            print 'Emailing %s' % address
            message = MIMEMultipart('alternative')
            message['Subject'] = 'Degree Days for %s - %s' % (location, result['meta']['name'])
            message['From'] = 'abraham.epton@gmail.com'
            message['To'] = address

            part_text = MIMEText(email_text['text'], 'plain')
            message.attach(part_text)

            part_html = MIMEText(email_text['html'], 'html')
            message.attach(part_html)

            part_image = MIMEImage(open(image_path, 'rb').read())
            part_image.add_header('Content-Disposition', 'attachment', filename=image_path)
            message.attach(part_image)

            connection.send_raw_email(
                RawMessage={
                    'Data': message.as_string()
                },
                Source=message['From'],
                Destinations=[message['To']])

    generate_last_days()
    generate_last_year_comparison()
    generate_average_days()
    get_forecast()
    generate_chart_data()
    generate_and_send_email()


if __name__ == '__main__':
    key = '19i_H7oA_fkJR5aU4FdeoInlOuI9-hwWqx9E-9TvH6To'
    url = 'https://docs.google.com/spreadsheets/d/%s/pub?gid=0&single=true&output=csv' % key
    locations = requests.get(url)
    for row in DictReader(StringIO(locations.text)):
        print 'Generating %s, %s' % (row['Station'], row['Period'])
        generate_image_for_location(row['Station'], int(row['Period']), row['Emails'])


