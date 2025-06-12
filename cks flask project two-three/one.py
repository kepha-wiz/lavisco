import sqlite3

# Connect to the database
conn = sqlite3.connect('election.db')
c = conn.cursor()

# Insert a sample agent (replace these with your preferred credentials)
c.execute("INSERT INTO agents (username, password) VALUES (?, ?)", ("admin", "admin123"))

conn.commit()
conn.close()
