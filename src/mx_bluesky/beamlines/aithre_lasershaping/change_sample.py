from dodal.devices.aithre_lasershaping.robot import BartRobot

robot = BartRobot(prefix="LA18L-MO-ROBOT-01:", name="lsrob")

async def change_sample():
    await robot.connect()
