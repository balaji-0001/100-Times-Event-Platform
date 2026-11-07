with open('artifacts/api-server/100times_database_dump.sql', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

def show_table(name):
    print('=== ' + name + ' ===')
    recording = False
    for line in lines:
        if ('CREATE TABLE `' + name + '`') in line:
            recording = True
        if recording:
            print(line, end='')
            if line.strip().endswith(';'):
                break

show_table('communities')
show_table('acquisition_opportunities')
show_table('event_discovery_sources')
