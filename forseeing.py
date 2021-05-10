import os
import sys
import urllib, urllib3, http.cookiejar
import datetime
import csv
import ephem
from astropy import constants as const
import json
import sys
from flask import Flask, request, send_file
from flask import jsonify
from flask_caching import Cache

config = {
    "DEBUG": True,  # some Flask specific configs
    "CACHE_TYPE": "SimpleCache",  # Flask-Caching related configs
    "CACHE_DEFAULT_TIMEOUT": 3600
}

app = Flask(__name__)

# tell Flask to use the above defined config
app.config.from_mapping(config)
cache = Cache(app)


def loadConfig(file='forseeing.json'):
    '''
    Get config data. If POST request contains any data => return, otherwise load a file
    '''
    if request.json is not None:
        return request.json
    else:
        try:
            with open(file) as myfile:
                result = json.load(myfile)
        except Exception as e:
            raise e
    return result


class Pass(object):

    def __init__(self, rise_t, high_t, set_t):
        self.rise_time = rise_t
        self.high_time = high_t
        self.set_time = set_t

    @property
    def length(self):
        return ((self.set_time - self.rise_time).seconds) / 60


class Satinfo(object):
    '''
    Sets objects from json file for satellite config
    '''

    def __init__(self, obj):
        self.satid = str(obj['satid'])
        self.sat_name = str(obj['sat_name'])
        self.sat_tx_freq = int(obj['sat_tx_freq'])  # [Hz]

    def __repr__(self):
        return f"{self.__class__.__name__},{self.satid},{self.sat_name},{self.sat_tx_freq}"


class Stationconf(object):
    '''
    Sets objects from json file for ground station config
    '''

    def __init__(self, obj):
        self.station_name = str(obj['station_name'])
        self.station_position = list(obj['station_position'])
        print(f"Station position is: {self.station_position[0]}, {self.station_position[1]}", file=sys.stderr)
        self.horizon = str(obj['horizon'])
        self.date_pred = datetime.datetime.utcnow()
        self.station_tx_freq = int(obj['station_tx_freq'])  # [Hz]
        self.num_passes = int(obj['num_passes'])
        self.timestep = int(obj['timestep'])
        self.channel_step = int(obj['channel_step'])
        self.use_channel_step = obj['use_channel_step']

    def __repr__(self):
        # WARNING: self.date_pred removed from Class so repr string can be used for CACHING but it could be a potential ISSUE if CACHING on calc will be for longer period, i.e more than 60 secs
        return f"{self.__class__.__name__},{self.station_name},{self.timestep},{self.station_position},{self.horizon},{self.station_tx_freq},{self.num_passes},{self.channel_step}, {self.use_channel_step}"


class Credentials(object):
    '''
    Sets objects from json file for credentials for TLE source website
    '''

    def __init__(self, obj):
        self.baseurl = str(obj['baseURL'])
        self.username = str(obj['username'])
        self.password = str(obj['password'])

    def __repr__(self):
        return f"{self.__class__.__name__},{self.baseurl},{self.username},{self.password}"


class csv_sheet(object):
    '''
    Sets objects from json file for csv file properties
    '''

    def __init__(self, obj):
        self.header = list(obj['header'])
        self.file_name = str(obj['file_name'])

    def __repr__(self):
        return f"{self.__class__.__name__},{self.header},{self.file_name}"


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


@cache.memoize(timeout=3600)
def get_tle(satid, username, password, baseURL):
    '''
    Getting the latest TLE data with the satellite ID as input from the website https://www.space-track.org/
    '''
    ctime = datetime.datetime.now()
    vtime = datetime.datetime.now() + datetime.timedelta(hours=1)
    print(
        f"TLE downloading for {satid} triggered at {ctime.strftime('%Y-%m-%d %H:%M:%S')} GMT and cached until {vtime.strftime('%Y-%m-%d %H:%M:%S')} GMT",
        file=sys.stderr)
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


def get_station_observer(station_position, horizon):
    station = ephem.Observer()
    station.lat = station_position[0]
    station.lon = station_position[1]
    station.elevation = station_position[2]
    station.horizon = horizon
    print(f"Station observer instantiated", file=sys.stderr)
    return station


def get_satellite_body(tle):
    satellite_body = ephem.readtle("SAT", tle[0], tle[1])
    print(f"Satellite body instantiated", file=sys.stderr)
    return satellite_body


def predict_pass(station_observer, satellite_body, date_pred):
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

    print(
        f"PREDICTING: for GS Station position @: {station_observer.lat}, {station_observer.lon}, and PASS AFTER: {date_pred.strftime('%Y-%m-%d %H:%M:%S')}",
        file=sys.stderr)
    station_observer.date = date_pred
    tr, azr, tt, altt, ts, azs = station_observer.next_pass(satellite_body)
    rise_time = datetime_from_time(tr)
    set_time = datetime_from_time(ts)
    high_time = datetime_from_time(tt)
    return rise_time, set_time, high_time,
    # return rise_time, set_time, high_time, satelite_body, station


def get_passes(date_pred, num_passes, timestep, station_observer, satellite_body):
    '''
    From the ground station data and using the predict_pass() computing the all the timestamps when the stellite is visbile for N amount passes.
    '''
    i = 0
    j = 0
    timestamps = []
    rise_times = []
    set_times = []
    high_times = []
    tmstmp_per_predict = []
    predict_time = date_pred
    while i < num_passes:
        rise_time, set_time, high_time = predict_pass(station_observer, satellite_body, predict_time)
        add_stamp = datetime.datetime.timestamp(rise_time + datetime.timedelta(seconds=1))
        end_stamp = datetime.datetime.timestamp(set_time)
        rise_times.append(rise_time)
        set_times.append(set_time)
        high_times.append(high_time)
        while add_stamp < end_stamp:
            timestamps.append(add_stamp)
            j += 1
            add_stamp = add_stamp + timestep
        # set time for next prediction
        predict_time = set_time + datetime.timedelta(seconds=1)
        i += 1
        tmstmp_per_predict.append(j)
    return timestamps, rise_times, set_times, high_times, tmstmp_per_predict


def get_az_el(timestamps, observer_station, sat_body):
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
        observer_station.date = datetime.datetime.fromtimestamp(thetimestamp)
        sat_body.compute(observer_station)
        azimuths.insert(i, angle_format(sat_body.az))
        elevations.insert(i, angle_format(sat_body.alt))
        satlat.insert(i, sat_body.sublat)
        satlong.insert(i, sat_body.sublong)
        i += 1
    return azimuths, elevations


def calc_doppler(timestamps, set_times, high_times, station, sate, sat_freq, use_channel_step, channel_step):
    '''
    Computing the doppler effect of the satellite communication and the correction frequency of the ground station.
    '''
    dopplerfreq = []
    dopplerfreq100mhz = []
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
        doppler_freq100mhz = v_r * 100_000_000 / const.c.value
        dopplerfreq.insert(i, doppler_freq)
        dopplerfreq100mhz.append(doppler_freq100mhz)
        i += 1
    i = 0
    j = 0

    # TODO: can be extracted do a dedicated method -> REFACTOR
    if use_channel_step == False:
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

            if dopplerfreq[i] > 3 * channel_step / 2:
                TX.insert(i, sat_freq - 2 * channel_step)
                RX.insert(i, sat_freq + 2 * channel_step)
            if dopplerfreq[i] > channel_step / 2:
                TX.insert(i, sat_freq - channel_step)
                RX.insert(i, sat_freq + channel_step)
            if dopplerfreq[i] > - channel_step / 2:
                TX.insert(i, sat_freq)
                RX.insert(i, sat_freq)
            if dopplerfreq[i] > - 3 * channel_step / 2:
                TX.insert(i, sat_freq + channel_step)
                RX.insert(i, sat_freq - channel_step)
            else:
                TX.insert(i, sat_freq + 2 * channel_step)
                RX.insert(i, sat_freq - 2 * channel_step)
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

    return dopplerfreq, RX, TX, dopplerfreq100mhz


def save_data(list_of_lists, header, file_name):
    '''
    Exporting data in CSV.
    '''
    # Reset file to avoid file max size overflow
    if (os.path.isfile(file_name)):
        os.unlink(file_name)
    data_csv = [list(i) for i in zip(*list_of_lists)]

    with open(file_name, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(header)
        for item in data_csv:
            writer.writerow(item)


def respond_with_file(filename):
    return send_file(filename, mimetype='text/csv')


def respond_from_file(filename):
    glue = ''
    return glue.join(open(filename, 'r').readlines())


def build_track_obj(timestamps, azimuths, elevations, doppfreq100mhz, npasses, it_per_pass):
    id_start = 0
    track_all = []
    for pass_no in range(npasses):
        id_end = it_per_pass[pass_no]
        elems = [{'ts': timestamps[id_start + i], 'az': azimuths[id_start + i], 'el': elevations[id_start + i],
                  'dp': doppfreq100mhz[id_start + i]} for i, _ in enumerate(timestamps[id_start:id_end])]
        id_start = id_end
        track = {'track': elems}
        track_all.append(track)
    return track_all


@cache.memoize(timeout=30)
def calc_data(Sat, Gs, Cr, File_output):
    print(
        f"Calc data for {Sat.satid} and station {Gs.station_name} triggered at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}GMT",
        file=sys.stderr)

    # Init bodies
    tle_line = get_tle(Sat.satid, Cr.username, Cr.password, Cr.baseurl)
    gs_observer = get_station_observer(Gs.station_position, Gs.horizon)
    sat_body = get_satellite_body(tle_line)

    # Calculate passes
    timestamps, rise_times, set_times, high_times, tmstmp_per_predict = get_passes(Gs.date_pred, Gs.num_passes,
                                                                                   Gs.timestep,
                                                                                   gs_observer, sat_body)
    print(f"Passes calculated, n-points: {len(timestamps)}", file=sys.stderr)

    # Get azimuths and elevations for given passes
    azimuths, elevations = get_az_el(timestamps, gs_observer, sat_body)
    print(f"AZIMUTH, ELEV calculated: n-points: {len(azimuths)}, {len(elevations)}", file=sys.stderr)

    # Calculate doppler frequency
    dopplerfreq, RX, TX, doppfreq100mhz = calc_doppler(timestamps, set_times, high_times, gs_observer, sat_body,
                                                       Sat.sat_tx_freq, Gs.use_channel_step,
                                                       Gs.channel_step)
    print(f"DOPPLER calculated", file=sys.stderr)

    # Adaption of format on output to conform to API
    track_data = build_track_obj(timestamps, azimuths, elevations, doppfreq100mhz, Gs.num_passes, tmstmp_per_predict)
    print(f"API compliant object built", file=sys.stderr)

    # EXPORT to file
    list_of_lists = [timestamps, azimuths, elevations, TX, RX]
    save_data(list_of_lists, File_output.header, File_output.file_name)
    print(f"STORED into : {File_output.file_name}", file=sys.stderr)

    return track_data


def load_setup():
    obj = loadConfig()
    Sat = Satinfo(obj)
    Gs = Stationconf(obj)
    Cr = Credentials(obj)
    csv_file = csv_sheet(obj)
    return {'sat': Sat, 'gs': Gs, 'cred': Cr, 'f_out': csv_file}


def get_pass_info(num_passes, station_observer, satellite_body, first_predict_time):
    predict_time = first_predict_time
    passes = []
    for i in range(num_passes):
        rise_time, set_time, high_time = predict_pass(station_observer, satellite_body, predict_time)
        pass_info = Pass(rise_time, high_time, set_time)
        predict_time = set_time + datetime.timedelta(seconds=1)
        passes.append(pass_info)
        print(f"DONE: pass N={i} ")
    return passes


@app.route("/", methods=['POST'])
def run():
    '''
    From satellite info and ground station data get the csv containing the timestamps of each time the satellite is in reach as well as
    the azimuth angle, elevation, correction frequency from the doppler effect for uplink and downlink, the data rate and the polarization.
    '''
    setup = load_setup()
    track_data = calc_data(setup["sat"], setup["gs"], setup["cred"], setup["f_out"])

    return jsonify(track_data)
    # return respond_from_file(exp.file_name)
    # return rise_time, set_time


@app.route("/bounds", methods=['POST'])
def get_bounds():
    setup = load_setup()

    # Init bodies
    Sat = setup["sat"]
    Gs = setup["gs"]
    Cr = setup["cred"]
    tle_line = get_tle(Sat.satid, Cr.username, Cr.password, Cr.baseurl)
    gs_observer = get_station_observer(Gs.station_position, Gs.horizon)
    sat_body = get_satellite_body(tle_line)

    passes = get_pass_info(Gs.num_passes, gs_observer, sat_body, Gs.date_pred)

    boundaries = []
    for item in passes:
        pass_boundary = {}
        pass_boundary["satid"] = Sat.satid
        pass_boundary["rise_time"] = datetime.datetime.timestamp(item.rise_time)
        pass_boundary["set_time"] = datetime.datetime.timestamp(item.set_time)
        pass_boundary["duration"] = item.length

        boundaries.append(pass_boundary)

    return jsonify(boundaries)


# rise_time, set_time = run()
# print(rise_time, set_time)
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8383, debug=True)
    # run()

# https://space.stackexchange.com/questions/4339/calculating-which-satellite-passes-are-visible
# https://rhodesmill.org/pyephem/
# https://ntlrepository.blob.core.windows.net/lib/59000/59300/59358/DOT-VNTSC-FAA-16-12.pdf
