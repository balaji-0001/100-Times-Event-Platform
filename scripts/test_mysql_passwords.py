import pymysql

passwords = [
    "Balaji@01",
    "Balaji@123",
    "Balaji@0001",
    "root",
    "admin",
    "password",
    "123456",
    "1234",
    "12345678",
    "MySQL80",
    "mysql",
    "",
]

success = None
for p in passwords:
    try:
        conn = pymysql.connect(
            host="127.0.0.1",
            user="root",
            password=p,
            port=3306,
            connect_timeout=2
        )
        print(f"SUCCESS! Password is: '{p}'")
        conn.close()
        success = p
        break
    except pymysql.err.OperationalError as e:
        code, msg = e.args
        # print(f"Failed with '{p}': {code} {msg}")
    except Exception as e:
        print(f"Other error with '{p}': {e}")

if not success:
    print("None of the common passwords matched.")
