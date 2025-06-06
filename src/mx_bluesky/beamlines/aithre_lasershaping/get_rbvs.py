import asyncio

from aiostream import stream
from bluesky.run_engine import RunEngine
from dodal.beamlines.aithre import goniometer, robot
from ophyd_async.core import observe_value

# laser_oav = oav(connect_immediately=True)

# async def monitor_oav():
#     """Monitor the OAV beam centre and update variables"""
#     RE = RunEngine()
#     laser_oav = oav(connect_immediately=True)
#     rbv_values = {'acqtime': 0.0, 'gain': 0.0}

#     obs_x = stream.map(observe_value(laser_oav.x.user_readback), lambda v, *args: ('x', v))
#     obs_y = stream.map(observe_value(laser_oav.y.user_readback), lambda v, *args: ('y', v))
#     obs_z = stream.map(observe_value(laser_oav.z.user_readback), lambda v, *args: ('z', v))

#     to_monitor = stream.merge(obs_x, obs_y, obs_z)

#     async with to_monitor.stream() as streamer:
#         async for channel, value in streamer:
#             rbv_values[channel] = value
#             print(f"Updated {channel} to {value}")


async def monitor_gonio():
    """Monitor the RBV of the goniometer axis and update variables"""
    RE = RunEngine()
    laser_goniometer = goniometer(connect_immediately=True)
    rbv_values = {
        "omega": 0.0,
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "sampy": 0.0,
        "sampz": 0.0,
    }

    obs_omega = stream.map(
        observe_value(laser_goniometer.omega.user_readback),
        lambda v, *args: ("omega", v),
    )
    obs_x = stream.map(
        observe_value(laser_goniometer.x.user_readback), lambda v, *args: ("x", v)
    )
    obs_y = stream.map(
        observe_value(laser_goniometer.y.user_readback), lambda v, *args: ("y", v)
    )
    obs_z = stream.map(
        observe_value(laser_goniometer.z.user_readback), lambda v, *args: ("z", v)
    )
    obs_sampy = stream.map(
        observe_value(laser_goniometer.sampy.user_readback),
        lambda v, *args: ("sampy", v),
    )
    obs_sampz = stream.map(
        observe_value(laser_goniometer.sampz.user_readback),
        lambda v, *args: ("sampz", v),
    )

    to_monitor = stream.merge(obs_omega, obs_x, obs_y, obs_z, obs_sampy, obs_sampz)

    async with to_monitor.stream() as streamer:
        async for channel, value in streamer:
            rbv_values[channel] = value
            print(f"Updated {channel} to {value}")


async def monitor_robot():
    """Monitor the RBV of the robot and update variables"""
    RE = RunEngine()
    laser_robot = robot(connect_immediately=True)
    rbv_values = {"current_pin": 5.8, "pin_mounted": False}
    obs_current_pin = stream.map(
        observe_value(laser_robot.current_pin), lambda v, *args: ("current_pin", v)
    )
    obs_pin_mounted = stream.map(
        observe_value(laser_robot.gonio_pin_sensor), lambda v, *args: ("pin_mounted", v)
    )

    to_monitor = stream.merge(obs_current_pin, obs_pin_mounted)

    async with to_monitor.stream() as streamer:
        async for channel, value in streamer:
            rbv_values[channel] = value
            print(f"Updated {channel} to {value}")


if __name__ == "__main__":
    print("Starting goniometer and robot RBV monitoring...")
    loop = asyncio.get_event_loop()
    tasks = asyncio.gather(monitor_robot(), monitor_gonio())
    loop.run_until_complete(tasks)
