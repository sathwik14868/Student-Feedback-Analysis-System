from database import get_connection

try:
    conn = get_connection()
    print("MySQL connected successfully!")
    conn.close()
except Exception as e:
    print("Connection failed:", e)