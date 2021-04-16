import os
import urllib, urllib3, http.cookiejar
import datetime
import csv
import ephem
from astropy import constants as const
import json
from flask import Flask, request, send_file

app = Flask(__name__)
app.returnFile = True

def loadConfig(file='forseeing.json'):
    '''
    Get config data from json file mentioned in command line
    '''
    if request.json is not None:
         app.returnFile = False
         return request.json
    else:
        try:
            with open(file) as myfile:
                result = json.load(myfile)
        except Exception as e:
            raise e
    return result


class Sat_info(object):
    '''
    Sets objects from json file for satellite config
    '''

    def __init__(self, obj):
        self.satid = str(obj['satid'])
        self.sat_name = str(obj['sat_name'])
        self.in_des = str(obj['in_des'])
        self.sat_freq = int(obj['sat_freq'])  # [Hz]


class Station_conf(object):
    '''
    Sets objects from json file for ground station config
    '''

    def __init__(self, obj):
        self.station_name = str(obj['station_name'])
        self.station_position = list(obj['station_position'])
        self.horizon = str(obj['horizon'])
        self.date_pred = datetime.datetime.utcnow()
        self.station_freq = int(obj['station_freq'])  # [Hz]
        self.data_rate = int(obj['data_rate'])
        self.polarization = str(obj['polarization'])
        self.num_passes = int(obj['num_passes'])
        self.timestep = int(obj['timestep'])
        self.channelstep = int(obj['channelstep'])
        self.channel_step = obj['channel_step']


class Credentials(object):
    '''
    Sets objects from json file for credentials for TLE source website
    '''

    def __init__(self, obj):
        self.baseURL = str(obj['baseURL'])
        self.username = str(obj['username'])
        self.password = str(obj['password'])


class csv_sheet(object):
    '''
    Sets objects from json file for csv file properties
    '''

    def __init__(self, obj):
        self.header = list(obj['header'])
        self.file_name = str(obj['file_name'])


def datetime_from_time(tr):
    '''
    Translate pyemphem time to the format="%YYYY-%MM-%DD %hh:%mm:%ss".
    '''
    year, month, day, hour, minute, second = tr.tuple()
    dt = datetime.datetime(year, month, day, hour, minute, int(second))
    return dt


def angle_format(angle):
    '''
    Convert angle in format 30:00:00.0 to 30.00000
    '''
    angle_format = str(angle).replace('.', ':', 1)
    angle_format = angle_format.replace(':', '.', 1)
    angle_format = angle_format.replace(':', '')
    return angle_format


def Get_TLE(satid, username, password, baseURL):
    '''
    Getting the latest TLE data with the satellite ID as input from the website https://www.space-track.org/
    '''
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    parameters = urllib.parse.urlencode({'identity': username, 'password': password}).encode("utf-8")
    opener.open(baseURL + '/ajaxauth/login', parameters)
    queryString = "https://www.space-track.org/basicspacedata/query/class/tle_latest/ORDINAL/1/NORAD_CAT_ID/" + satid + "/orderby/TLE_LINE1%20ASC/format/tle"
    resp = opener.open(queryString)
    TLE = resp.read()
    TLE_utf = str(TLE, "utf-8")
    opener.close()
    TLE_line = TLE_utf.split('\n')
    return TLE_line


def predict_pass(station_position, horizon, date_pred, TLE_line):
    '''
    The prediction of the passes are made by using the pyephem libraries,
    The mathematical steps for realising this are usually following:

    1. Translate the TLE data to the orbital elements of the Satellite.
    2. Expressing the satellites position inside the orbital plane.
    3. Translating the coordinates to the inertial coordinates.
    4. Translating the interial coordinates to the topocentric coordinates.
    5. Calculation od the elevation, azimuth and slant range.

    Pyephem allows to define the ground station with its different properties.
    The Satellite object is defined with the TLE data as input.
    '''
    station = ephem.Observer()
    station.lat = station_position[0]
    station.lon = station_position[1]
    station.elevation = station_position[2]
    station.horizon = horizon
    station.date = date_pred
    sate = ephem.readtle("SAT", TLE_line[0], TLE_line[1])
    tr, azr, tt, altt, ts, azs = station.next_pass(sate)
    rise_time = datetime_from_time(tr)
    set_time = datetime_from_time(ts)
    high_time = datetime_from_time(tt)
    return rise_time, set_time, high_time, station, sate


def get_passes(station, date_pred, num_passes, timestep, station_position, horizon, TLE_line):
    '''
    From the ground station data and using the predict_pass() computing the all the timestamps when the stellite is visbile for N amount passes.
    '''
    i = 0
    j = 0
    timestamps = []
    rise_times = []
    set_times = []
    high_times = []
    predict_time = date_pred
    while i < num_passes:
        rise_time, set_time, high_time, station, sate = predict_pass(station_position, horizon, predict_time, TLE_line)
        add_stamp = datetime.datetime.timestamp(rise_time + datetime.timedelta(seconds=1))
        end_stamp = datetime.datetime.timestamp(set_time)
        rise_times.append(rise_time)
        set_times.append(set_time)
        high_times.append(high_time)
        while add_stamp < end_stamp:
            timestamps.append(add_stamp)
            j += 1
            add_stamp = add_stamp + timestep
        predict_time = set_time + datetime.timedelta(seconds=1)
        i += 1
    return timestamps, rise_times, set_times, high_times


def get_az_el(timestamps, station, sate):
    '''
    With pyephem computing azimuths angles and elevation for each timestamp.
    '''
    azimuths = []
    elevations = []
    satlat = []
    satlong = []
    n = len(timestamps)
    i = 0
    while i < n:
        thetimestamp = timestamps[i]
        station.date = datetime.datetime.fromtimestamp(thetimestamp)
        sate.compute(station)
        azimuths.insert(i, angle_format(sate.az))
        elevations.insert(i, angle_format(sate.alt))
        satlat.insert(i, sate.sublat)
        satlong.insert(i, sate.sublong)
        i += 1
    return azimuths, elevations, timestamps, station, sate


def calcDopler(timestamps, set_times, high_times, station, sate, sat_freq, channel_step, channelstep):
    '''
    Computing the doppler effect of the satellite communication and the correction frequency of the ground station.
    '''
    dopplerfreq = []
    RX = []
    TX = []
    n = len(timestamps)
    i = 0
    while i < n:
        thetimestamp = timestamps[i]
        station.date = datetime.datetime.fromtimestamp(thetimestamp)
        sate.compute(station)
        v_r = sate.range_velocity
        '''
        To calculate the doppler effect of the passing satellite:

        Doppler_frequency = V_r * freq / c

        c is the speed of light [m/s]
        freq is the frequency of the link [Hz]
        V_r relative velocity of the satellite with respect to the ground station [m/s]
        also called range velocity directly given by pyephem: range_velocity [m/s]

        The range velocity is determined by: V_r = [d(t+delta_t)-d(t)]/delta_t the derivative of the slant range d.
        d is the range distance from observer to satellite given by pyephem: range [m]

                S
                |\
               h| \d
               _|_ \
             _R |  _\
             _ O|--_ U
               _ _

        The range distance betweem the point S (satellite) and U (ground station) is calculated as such:

        d = srqt(B*cos(elev)^2 + r - B^2) - B*cos(elev)

        B is the distance from the Geocenter to the ground station, the distance OU
        h distance between the surface and the satellite given by pyephem: elevation [m]
        R radius of the earth to the surface facing the Satellite
        r = R + h distance from Geocenter to satellite
        elev the elevation angle given by pyephem: alt [°]
        '''
        doppler_freq = v_r * sat_freq / const.c.value
        dopplerfreq.insert(i, doppler_freq)
        i += 1
    i = 0
    j = 0
    if channel_step == False:
        while i < n:

            if timestamps[i] > datetime.datetime.timestamp(set_times[j]):
                j += 1
                RX.insert(i, sat_freq + abs(dopplerfreq[i]))
                TX.insert(i, sat_freq - abs(dopplerfreq[i]))
            if timestamps[i] < datetime.datetime.timestamp(high_times[j]):
                RX.insert(i, sat_freq + abs(dopplerfreq[i]))
                TX.insert(i, sat_freq - abs(dopplerfreq[i]))
            if timestamps[i] == datetime.datetime.timestamp(high_times[j]):
                RX.insert(i, sat_freq)
                TX.insert(i, sat_freq)
            if timestamps[i] > datetime.datetime.timestamp(high_times[j]):
                RX.insert(i, sat_freq - abs(dopplerfreq[i]))
                TX.insert(i, sat_freq + abs(dopplerfreq[i]))

            else:
                None
            i += 1
    else:
        while i < n:

            if dopplerfreq[i] > 3 * channelstep / 2:
                TX.insert(i, sat_freq - 2 * channelstep)
                RX.insert(i, sat_freq + 2 * channelstep)
            if dopplerfreq[i] > channelstep / 2:
                TX.insert(i, sat_freq - channelstep)
                RX.insert(i, sat_freq + channelstep)
            if dopplerfreq[i] > - channelstep / 2:
                TX.insert(i, sat_freq)
                RX.insert(i, sat_freq)
            if dopplerfreq[i] > - 3 * channelstep / 2:
                TX.insert(i, sat_freq + channelstep)
                RX.insert(i, sat_freq - channelstep)
            else:
                TX.insert(i, sat_freq + 2 * channelstep)
                RX.insert(i, sat_freq - 2 * channelstep)
            i += 1

        '''
        To correct the frequency of the ground station:

             __________________________________________________________________
             | Satellite approaching | Max elevation point | Satellite fading  |
        _____|_______________________|_____________________|___________________|
        |TX  | satfreq-|doppler|     |      satfreq        | satfreq-|doppler| |
        |____|_______________________|_____________________|___________________|
        |RX  | satfreq-|doppler|     |      satfreq        | satfreq-|doppler| |
        |____|_______________________|_____________________|___________________|

        '''

    return dopplerfreq, RX, TX


def save_data(list_of_lists, header, file_name, timestamps):
    '''
    Exporting data in CSV.
    '''
    #Reset file to avoid file max size overflow
    if (os.path.isfile(file_name)):
        os.unlink(file_name)
    data_csv = [list(i) for i in zip(*list_of_lists)]
    i = 0
    n = len(timestamps)
    # with open(file_name, 'w', newline='') as file:
    # write = csv.writer(file)
    # write.writerow(header)
    while i < n:
        with open(file_name, 'a+', newline='') as file:
            write = csv.writer(file)
            # print(data_csv)
            write.writerow(data_csv[i])
        i += 1

def respond_with_file(filename):
    return send_file(filename, mimetype='text/csv')

def respond_from_file(filename):
    glue = ''
    return glue.join(open(filename, 'r').readlines())

@app.route("/", methods=['POST'])
def run():
    '''
    From satellite info and ground station data get the csv containing the timestamps of each time the satellite is in reach as well as
    the azimuth angle, elevation, correction frequency from the doppler effect for uplink and downlink, the data rate and the polarization.
    '''
    obj = loadConfig()
    Sat = Sat_info(obj)
    Gs = Station_conf(obj)
    Cr = Credentials(obj)
    exp = csv_sheet(obj)
    TLE_line = Get_TLE(Sat.satid, Cr.username, Cr.password, Cr.baseURL)
    rise_time, set_time, high_time, station, sate = predict_pass(Gs.station_position, Gs.horizon, Gs.date_pred,
                                                                 TLE_line)
    timestamps, rise_times, set_times, high_times = get_passes(station, Gs.date_pred, Gs.num_passes, Gs.timestep,
                                                               Gs.station_position, Gs.horizon, TLE_line)
    azimuths, elevations, timestamps, station, sate = get_az_el(timestamps, station, sate)
    dopplerfreq, RX, TX = calcDopler(timestamps, set_times, high_times, station, sate, Sat.sat_freq, Gs.channel_step,
                                     Gs.channelstep)
    rate = [Gs.data_rate] * len(timestamps)
    polar = [Gs.polarization] * len(timestamps)
    list_of_lists = [timestamps, azimuths, elevations, TX, RX, rate, polar]
    save_data(list_of_lists, exp.header, exp.file_name, timestamps)
    if(app.returnFile):
        return respond_with_file(obj["file_name"])
    else:
        return respond_from_file(obj["file_name"])
    # return rise_time, set_time


# rise_time, set_time = run()
# print(rise_time, set_time)
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=True)
    # run()

# https://space.stackexchange.com/questions/4339/calculating-which-satellite-passes-are-visible
# https://rhodesmill.org/pyephem/
# https://ntlrepository.blob.core.windows.net/lib/59000/59300/59358/DOT-VNTSC-FAA-16-12.pdf

