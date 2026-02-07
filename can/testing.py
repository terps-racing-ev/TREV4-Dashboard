import cantools


db_file = cantools.database.load_file('CONTROLS.dbc')

for message in db_file.messages:
    print(f"message: {message.name}")
    for signal in message.signals:
        print(f"signal: {signal.name} unit: {signal.unit}")
