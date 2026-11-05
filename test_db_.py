from database import get_connection

conn = get_connection()

if conn.is_connected():
    print("MySQL Connected Successfully!")

conn.close()