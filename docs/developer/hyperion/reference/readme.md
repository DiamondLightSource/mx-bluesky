# hyperion

Repository for the Hyperion project to implement Unattended Data Collections on the Diamond MX beamlines using the [BlueSky](https://nsls-ii.github.io/bluesky/) / Ophyd framework from BNL.

Currently the software is able to:

- Centre a sample, first using an optical camera, then using an xray grid scan. This centring is done at two orthogonal angles so that the sample is centred in 3D.
- Perform a rotation scan to take diffraction data of the sample

Left to do is:

- Mount/unmount samples
- Set up the beamline to be in a standard state for collection
- Change energy of the beamline

# Development Installation

This project supports only the most recent Python version for which our dependencies are available - currently Python 3.11.

Run `./utility_scripts/dls_dev_env.sh` (This assumes you're on a DLS machine. If you are not, you should be able to just run a subset of this script)

Note that because Hyperion makes heavy use of [Dodal](https://github.com/DiamondLightSource/dodal) this will also pull a local editable version of dodal to the parent folder of this repo.

# Controlling the Gridscan Externally (e.g. from GDA)

## Starting the bluesky runner

The bluesky runner is (re)started in production by GDA when it invokes `run_hyperion.sh`. 

If you wish to attempt to run from a developer machine, then (if you are able to connect all devices) 
you may `run_hyperion.sh --dev --beamline=<beamline>`, which will give you a running instance albeit with
read-only devices. The `--dev` flag ensures that logging will not be sent to the production Graylog/output folders.

This script will determine which beamline you are on based on the `BEAMLINE` environment variable. If on a 
beamline Hyperion will run with `INFO` level logging, sending its logs to both production graylog and to the beamline/log/bluesky/hyperion.log on the shared file system.

If in a dev environment Hyperion will log to a local graylog instance instead and into a file at `./tmp/dev/hyperion.log`. A local instance of graylog will need to be running for this to work correctly. To set this up and run up the containers on your local machine run the `setup_graylog.sh` script.

This uses the generic defaults for a local graylog instance. It can be accessed on `localhost:9000` where the username and password for the graylog portal are both admin.

The hyperion python module can also be run directly without the startup script. It takes the same command line options, including:

`INFO` level logging of the Bluesky event documents can be enabled with the flag

```
python -m hyperion --dev --verbose-event-logging
```

## Testing

Unit tests can be run with `pytest --random-order`. To see log output from tests you can turn on logging with the `--logging` command line option and then use the `-s` command line option to print logs into the console. So to run the unit tests such that all logs are at printed to the terminal, you can use `python -m pytest --random-order --logging -s`. Note that this will likely overrun your terminal buffer, so you can narrow the selection of tests with the `-k "<test name pattern>"` option.

To fake interaction and processing with Zocalo, you can run `fake_zocalo/dls_start_fake_zocalo.sh`, and make sure to run `module load dials/latest` before starting hyperion (in the same terminal).

## Tracing

Tracing information (the time taken to complete different steps of experiments) is collected by an [OpenTelemetry](https://opentelemetry.io/) tracer, and currently we export this information to a local Jaeger monitor (if available). To see the tracing output, run the [Jaeger all-in-one container](https://www.jaegertracing.io/docs/1.6/getting-started/), and go to the web interface at http://localhost:16686.

## Starting a scan

To start a scan you can do the following:

```
curl -X PUT http://127.0.0.1:5005/flyscan_xray_centre/start --data-binary "@tests/test_data/parameter_json_files/test_parameters.json" -H "Content-Type: application/json"
```

## Getting the Runner Status

To get the status of the runner:

```
curl http://127.0.0.1:5005/status
```

## Stopping the Scan

To stop a scan that is currently running:

```
curl -X PUT http://127.0.0.1:5005/stop

```

## Writing out `DEBUG` logs

To make the app write the `DEBUG` level logs stored in the `CircularMemoryHandler`:

```
curl -X PUT http://127.0.0.1:5005/flush_debug_log

```
