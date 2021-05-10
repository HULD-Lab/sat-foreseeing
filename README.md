# sat-foreseeing
Satellite pass foreseeing for ground station 
> by [HULD](https://huld.io)

This is a tool to get the next passes, azimuth angle and elevation angle from a certain satellite by having as input its satellite ID and the position of the ground station of the user. To find the ID of the satellite www.celestrak.com/NORAD/elements can be used. The website categorizes the satellites and give their respective TLE. The latest TLE is loaded from the website: https://www.space-track.org/. Moreover this tool outputs a CSV file that contains also the doppler shift correction needed for communication with the satellite. This CSV can be used to control a ground station.

Example of TLE: 
```
ATLAS CENTAUR 2         
1 00694U 63047A   20090.82980658  .00000230  00000-0  13759-4 0  9990
2 00694  30.3601 323.7151 0585979 224.1186 131.1207 14.02586114825678
```
Its ID is then 00694.

Its prediction time of the passes is calculated from the TLE using the pyephem python libraries. 
## OUTPUT
* format : csv

# Setting the environment
## Requirements
* python libraries of ephem, urllib, urllib3, http.cookiejar, astropy
* Docker installed
* Docker compose
## Space-track account
* Create an account for the [space-track](https://www.space-track.org/), credentials put in the forseeing.json file.
## Update forseeing.json
* Set the data of your satellite of interest
* Update this file with space-track.org credentials.
* Set the data of the ground station

## Run following commands
```
docker-compose build
docker-compose up
```

## Connection to the API
```
<docker IP>:8383/get/<NORAD_ID>
```
**On Linux**
```
e.g http://127.0.0.1:8383/get/42790
```
**On Windows** version XP,7,8 (i.e. without shell sub-system)
```
e.g 192.168.99.100:8383/get/42790  #correct IP will be displayed during booting up docker machine
``` 

Will output(header has been commented out in the forseeing.py file):
```
Timestamp,Azimuth,Elevation,Uplink frequency,Downlink frequency,Data Rate,Polarization
```
The data for the ground station:
```

1602854300.0,190.05117,0.02312,437230399.16315645,437249600.83684355,115000,Linear
1602854301.0,190.09171,0.05227,437230403.906763,437249596.093237,115000,Linear
1602854302.0,190.13239,0.08154,437230408.6995077,437249591.3004923,115000,Linear
1602854303.0,190.17319,0.11092,437230413.5413905,437249586.4586095,115000,Linear
1602854304.0,190.21413,0.14042,437230418.4324114,437249581.5675886,115000,Linear
1602854305.0,190.25520,0.17002,437230423.37399465,437249576.62600535,115000,Linear
1602854306.0,190.30040,0.19573,437230428.36542815,437249571.63457185,115000,Linear
1602854307.0,190.34174,0.22556,437230433.4081362,437249566.5918638,115000,Linear
1602854308.0,190.38322,0.25549,437230438.5028309,437249561.4971691,115000,Linear
...
```
