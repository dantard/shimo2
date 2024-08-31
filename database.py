import random
import sqlite3
import subprocess

# Connect to the database (or create it if it doesn't exist)
import sys
import time

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
            remote TEXT NOT NULL,
            album TEXT NOT NULL,
            file TEXT NOT NULL,
            hash TEXT NOT NULL,
            touched INTEGER,
            UNIQUE(album,file)
        )''')

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS sequence (id INTEGER, date float)''')
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS albums (id INTEGER primary key, remote text, title text, active integer, touched integer, UNIQUE(remote, title))''')

        # Commit the changes
        self.connection.commit()

    def update_remote(self, remote, kind):

        result = subprocess.run(['rclone', "lsf", remote + "album", "--max-depth", "1", "--format", "pi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

        self.cursor.execute('''UPDATE albums SET touched = ? where remote = ?''', (0, remote))

        for line in result.stdout.splitlines():
            print(line)
            album, hash = line.split(";")

            self.cursor.execute('''INSERT INTO albums (remote, title, active, touched)
                     VALUES (?, ?, ?, ?)
                     ON CONFLICT(remote, title) DO UPDATE SET touched = 1''', (remote, album.replace("/", ""), 0, 1))

        # select all the untouched albums
        albums = self.cursor.execute('''SELECT remote, title FROM albums WHERE touched = 0 and remote = ?''', (remote,))

        # delete all the images from my_table of remove album
        for remote, title in albums.fetchall():
            self.cursor.execute('''DELETE FROM my_table WHERE remote = ? and album = ?''', (remote, title))

        # Delete the albums that are not in the remote anymore
        self.cursor.execute('''DELETE FROM albums WHERE touched = 0 and remote = ?''', (remote,))


        self.connection.commit()

    def get_albums(self, remote):
        albums = self.cursor.execute('''
        SELECT remote, title, active
        FROM albums WHERE remote = ?
        ''', (remote,))

        return albums.fetchall()

    def get_remotes(self):
        remotes = self.cursor.execute('''SELECT DISTINCT remote FROM albums''')
        return [x[0] for x in remotes.fetchall()]

    # def update_full(self):
    #     result = subprocess.run(['rclone', "lsf", "gphoto:album", "--max-depth", "2", "--format", "pi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    #                             text=True)
    #
    #     self.cursor.execute('''UPDATE my_table SET touched = ?''', (0,))
    #     self.connection.commit()
    #
    #     for line in result.stdout.splitlines():
    #         parts = line.split(";")
    #         path = parts[0]
    #         hash = parts[1]
    #         folder, filename = path.split("/")
    #         if filename:
    #             print(folder, filename, hash)
    #
    #         self.cursor.execute('''INSERT INTO my_table (album, file, hash, touched)
    #                 VALUES (?, ?, ?, ?)
    #                 ON CONFLICT(album,file) DO UPDATE SET touched = 1''', (folder, filename, hash, 1))
    #
    #         self.connection.commit()
    #
    #         self.cursor.execute('''DELETE FROM my_table WHERE touched = 0''')
    #
    #         # Commit the changes
    #         self.connection.commit()

    def insert_recent(self, id):
        self.cursor.execute('''DELETE FROM sequence
            WHERE id NOT IN (
            SELECT id
            FROM sequence
            ORDER BY date DESC
            LIMIT 3
        );''')
        self.cursor.execute('''INSERT INTO sequence (id, date) VALUES (?, ?)''', (id, time.time()))
        self.connection.commit()

    def get_recent_ids(self):
        ids = self.cursor.execute('SELECT id FROM sequence')
        return [x[0] for x in ids.fetchall()]

    def remove_album(self, remote, album):
        # Delete from my_table all the file of the specified album
        self.cursor.execute('''DELETE FROM my_table WHERE remote = ? AND album = ?''', (remote, album))
        self.connection.commit()

    def update_album_active(self, remote, album, active):
        self.cursor.execute('''UPDATE albums SET active = ? where remote = ? and title = ?''', (active, remote, album))
        self.connection.commit()

    def update_album(self, remote, album):

        print("********** updating", album)
        result = subprocess.run(['rclone', "lsf", remote + "album/" + album,
                                 "--max-depth", "2", "--format", "pi"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)

        for line in result.stdout.splitlines():
            parts = line.split(";")
            filename = parts[0]
            hash = parts[1]

            self.cursor.execute('''INSERT INTO my_table (remote, album, file, hash, touched) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(album,file) DO UPDATE SET touched = 1''', (remote, album, filename, hash, 1))

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
        name = cursor.execute('SELECT remote, album, file, hash FROM my_table WHERE id = ?', (index,))
        result = name.fetchone()
        connection.close()
        return result

    def get_album_from_hash(self, hash):
        connection = sqlite3.connect('my_database.db')
        cursor = connection.cursor()
        # get all ids from the database
        name = cursor.execute('SELECT album FROM my_table WHERE hash = ?', (hash,))
        result = name.fetchone()
        connection.close()
        return result
