from dodal.devices.aithre_lasershaping.cameras import OAV


oav = OAV(prefix="LA18L-DI-OAV-01:", name="oav")
async def run():
    await oav.connect()
    await oav.snapshot.filename.get_value()
    await oav.snapshot.directory.set("/tmp/")
    await oav.snapshot.filename.set("test")
