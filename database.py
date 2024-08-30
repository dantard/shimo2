import random
import sqlite3
import subprocess

# Connect to the database (or create it if it doesn't exist)
import sys

from downloader import Downloader


class Database:

    def __init__(self):
        self.connection = sqlite3.connect('my_database.db')

        # Create a cursor object to execute SQL commands
        self.cursor = self.connection.cursor()

        # Example: Create a table if you want
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS my_table (
            id INTEGER PRIMARY KEY,
            album TEXT NOT NULL,
            file TEXT NOT NULL,
            hash TEXT NOT NULL,
            touched INTEGER,
            UNIQUE(album,file)
        )
        ''')

        # Commit the changes
        self.connection.commit()

    def update_full(self):
        result = subprocess.run(['rclone', "lsf", "gphoto:album", "--max-depth", "2", "--format", "pi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

        self.cursor.execute('''UPDATE my_table SET touched = ?''', (0,))
        self.connection.commit()

        for line in result.stdout.splitlines():
            parts = line.split(";")
            path = parts[0]
            hash = parts[1]
            folder, filename = path.split("/")
            if filename:
                print(folder, filename, hash)

            self.cursor.execute('''INSERT INTO my_table (album, file, hash, touched)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(album,file) DO UPDATE SET touched = 1''', (folder, filename, hash, 1))

            self.connection.commit()

            self.cursor.execute('''DELETE FROM my_table WHERE touched = 0''')

            # Commit the changes
            self.connection.commit()

    def update_by_album(self):
        # get all the albums from the database
        albums = self.cursor.execute('''
        SELECT DISTINCT album
        FROM my_table
        ''')

        albums = albums.fetchall()
        print("********** updating", len(albums), "albums")

        for xx in albums:
            folder = xx[0]
            print("********** updating", folder)
            result = subprocess.run(['rclone', "lsf", "gphoto:album/" + folder,
                                     "--max-depth", "2", "--format", "pi"],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)

            for line in result.stdout.splitlines():
                parts = line.split(";")
                filename = parts[0]
                hash = parts[1]

                self.cursor.execute('''INSERT INTO my_table (album, file, hash, touched) VALUES (?, ?, ?, ?)
                    ON CONFLICT(album,file) DO UPDATE SET touched = 1''', (folder, filename, hash, 1))

                self.connection.commit()

                self.cursor.execute('''DELETE FROM my_table WHERE touched = 0''')

                # Commit the changes
                self.connection.commit()

    def get_ids(self):
        # get all ids from the database
        ids = self.cursor.execute('SELECT DISTINCT id FROM my_table')
        return [x[0] for x in ids.fetchall()]

    def get_name_from_id(self, index):
        connection = sqlite3.connect('my_database.db')
        cursor = connection.cursor()
        # get all ids from the database
        name = cursor.execute('SELECT album, file FROM my_table WHERE id = ?', (index,))
        result = name.fetchone()
        print("result", result)
        connection.close()
        return result
