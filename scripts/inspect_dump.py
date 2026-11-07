import re

dump_path = 'artifacts/api-server/100times_database_dump.sql'
with open(dump_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if 'INSERT INTO `users`' in line:
            print("Users line found! Length:", len(line))
            # Find emails in this line
            emails = re.findall(r'[\w\.-]+@[\w\.-]+', line)
            print("Emails in users table:", emails[:15])
