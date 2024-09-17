# Old code

## Where and how

- The deployment used live both times lives in: `/dls_sw/i24/software/bluesky/jungfrau`
- .venv in `./jungfrau_commissioning`
- executable `jungfrau_commissioning` loads an iPython terminal
- don't install stuff pls - this environment has dependencies which no longer exist like `python-artemis`
- changing the code is fine
- if you mess up the environment the dependencies can be found in current_deps.txt

## Talk to JF

`jf = i24.jungfrau()`

## Collect darks

`RE(do_darks(jf))` 

## Warnings

- Directory hardcoded in many places in code - "/dls/i24/data/2024/cm37275-4/jungfrau_commissioning/" - should be fine 
- expects a file `run_number.txt` with a 5-digit integer for keeping track of the run number

## Rotation scans

- Parameter files in /dls_sw/i24/software/bluesky/jungfrau/jungfrau_commissioning/param_files
- just modify the JSON (should be relatively obvious)
- fine for exp time and acq time to be the same (detector will adjust for readout time)
- 

### load the params:

- `params = RotationScanParameters.from_file("param_files/insulin_2khz.json")`
- this can be modified on the fly
- a copy will be saved alongside the data

### run a scan:

`RE(get_rotation_scan_plan(params))`

### run rotation scans at various transmissions

`RE(rotations_at_transmissions(params, [0.04,0.08,0.16,0.32,0.64]))`

## Burst mode ???!!!

- will need to provide compatible scan parameters (see the manual?)
- 

# Talking to the detector directly; the IOC

- it lives on `bl24i-sc-jcu01`
- run `sudo -l` to see what you can do there
- hopefully it includes `systemctl stop/start/restart epics-soft-iocs`
- one IOC for jungfrau and one for frame receiver
- to look at IOC logs live, `console BL24I-EA-SLSRC-01`, ctrl+x to restart
- IOC and scripts which talk to detector live  `/dls_sw/work/jungfrau`
- SLSDetector binaries live in `/dls_sw/prod/tools/RHEL7-x86_64/slsDetectorPackage/8.0.1dls1/prefix/bin`
-  `sls_detector_get list`
- detector binaries or IOC write files to /dev/shm which only one person can own at a time
- IOC runs as i24detector
- Gary has some scripts for setting up the detector in `/dls_sw/work/jungfrau/`
- run `/dls_sw/work/jungfrau/jungfrau_acquisition.py --initial-config -config=/dls_sw/work/jungfrau/slsDetector/etc/makeIocs/jungfrau_i24.config`
- this config has networking config that tell the detector where to push stuff
- needs to correspond to the frame receiver and IOC in `start_<thing>.sh`
- the recommended power-off procedure is the following:
  - `sls_detector_put stop` -  ensures that the detector is not running
  - `sls_detector_put highvoltage 0`
  - `sls_detector_put powerchip 0`
