from IGBot.core.phone_manager import PhoneManager

devices = PhoneManager.get_connected_devices()

print("Connected devices:", devices)

if devices:
    print("First device online:", PhoneManager.is_connected(devices[0]))
else:
    print("No Android devices detected.")
