import random
import sqlite3
import subprocess

# Connect to the database (or create it if it doesn't exist)
import sys
import time
from threading import Lock

from downloader import Downloader


class Cursor:
    def __init__(self):
        self.connection = sqlite3.connect('my_database.db')
        self.cursor = self.connection.cursor()

    def execute(self, *args, commit=False, close=False):
        ret = self.cursor.execute(*args)
        if commit:
            self.connection.commit()
        if close:
            self.connection.close()
        return ret

    def fetch_all(self, *args, close=False):
        self.cursor.execute(*args)
        result = self.cursor.fetchall()
        if close:
            self.connection.close()
        return result

    def fetch_one(self, *args, close=False):
        self.cursor.execute(*args)
        result = self.cursor.fetchone()
        if close:
            self.connection.close()
        return result

    def commit(self):
        self.connection.commit()

    def close(self, commit=False):
        #self.cursor.close()
        if commit:
            self.connection.commit()
        self.connection.close()


class Database:

    def __init__(self):
        self.directory = "shared-album"
        self.connection = sqlite3.connect('my_database.db')
        # Create a cursor object to execute SQL commands
        self.cursor = self.connection.cursor()
        self.lock = Lock()
        # Example: Create a table if you want
        # set wal mode
        #self.cursor.execute("PRAGMA journal_mode=WAL")
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
        self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS remotes (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
        )''')


        self.cursor.execute('''CREATE TABLE IF NOT EXISTS sequence (id INTEGER, date float)''')
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS albums (id INTEGER primary key, remote text, title text, active integer, touched integer, UNIQUE(remote, title))''')

        # Commit the changes
        self.connection.commit()

    def update_remote(self, remote):

        result = subprocess.run(['rclone', "lsf", remote + self.directory, "--max-depth", "1", "--format", "pi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

        cursor = Cursor()
        cursor.execute('''UPDATE albums SET touched = ? where remote = ?''', (0, remote))
        folders = []
        for line in result.stdout.splitlines():
            print(line)
            album, hash = line.split(";")
            folders.append((album, hash))
        print("1",folders)
        folders.sort(key=lambda x: x[0], reverse=True)
        print("2", folders)
        for album, hash in folders:
            cursor.execute('''INSERT INTO albums (remote, title, active, touched)
                     VALUES (?, ?, ?, ?)
                     ON CONFLICT(remote, title) DO UPDATE SET touched = 1''', (remote, album.replace("/", ""), 1, 1))

        # select all the untouched albums
        albums = cursor.fetch_all('SELECT remote, title FROM albums WHERE touched = 0 and remote = ?', (remote,))

        # delete all the images from my_table of removed album
        for remote, title in albums:
            cursor.execute('DELETE FROM my_table WHERE remote = ? and album = ?', (remote, title))

        # Delete the albums that are not in the remote anymore
        cursor.execute('DELETE FROM albums WHERE touched = 0 and remote = ?', (remote,))

        cursor.close(commit=True)

    def get_albums(self, remote):
        self.lock.acquire()
        albums =  Cursor().fetch_all('SELECT remote, title, active FROM albums WHERE remote = ? order by title desc', (remote,), close=True)
        self.lock.release()
        return albums

    def get_remotes(self):
        self.lock.acquire()
        remotes = Cursor().fetch_all('SELECT name FROM remotes', close=True)
        self.lock.release()
        return [x[0] for x in remotes]

    def insert_recent(self, id):
        cursor = Cursor()
        cursor.execute('''DELETE FROM sequence
            WHERE id NOT IN (
            SELECT id
            FROM sequence
            ORDER BY date DESC
            LIMIT 10
        );''')
        cursor.execute('INSERT INTO sequence (id, date) VALUES (?, ?)', (id, time.time()), commit=True, close=True)


    def get_recent_ids(self):
        ids = Cursor().fetch_all('SELECT id FROM sequence', close=True)
        return [x[0] for x in ids]

    def remove_album(self, remote, album):
        # Delete from my_table all the file of the specified album
        Cursor().execute('DELETE FROM my_table WHERE remote = ? AND album = ?', (remote, album), commit=True, close=True)

    def update_album_active(self, remote, album, active):
        Cursor().execute('UPDATE albums SET active = ? where remote = ? and title = ?', (active, remote, album), commit=True, close=True)

    def update_album(self, remote, album):

        self.lock.acquire()
        result = subprocess.run(['rclone', "lsf", remote + self.directory + "/" + album,
                                 "--max-depth", "2", "--format", "pi"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)
        cursor = Cursor()
        print("album", album, "len", len(result.stdout.splitlines()))
        cursor.execute('''UPDATE my_table SET touched = 0 WHERE remote = ? and album = ?''', (remote, album))

        for line in result.stdout.splitlines():
            filename, hash = line.split(";")
            cursor.execute('''INSERT INTO my_table (remote, album, file, hash, touched) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(album,file) DO UPDATE SET touched = 1''', (remote, album, filename, hash, 1))

        cursor.execute('DELETE FROM my_table WHERE touched = 0')

        cursor.close(True)
        self.lock.release()

    def add_remote(self, remote):
        Cursor().execute('INSERT INTO remotes (name) VALUES (?)', (remote,), commit=True, close=True)

    def remove_remote(self, remote):
        Cursor().execute('DELETE FROM remotes WHERE name = ?', (remote,), commit=True, close=True)
        Cursor().execute('DELETE FROM albums WHERE remote = ?', (remote,), commit=True, close=True)
        Cursor().execute('DELETE FROM my_table WHERE remote = ?', (remote,), commit=True, close=True)

    def get_ids(self):
        self.lock.acquire()
        ids = Cursor().fetch_all('SELECT DISTINCT id FROM my_table', close=True)
        self.lock.release()
        return [x[0] for x in ids]

    def get_info_from_id(self, index):
        self.lock.acquire()
        result = Cursor().fetch_one('SELECT remote, album, file, hash FROM my_table WHERE id = ?', (index,), close=True)
        self.lock.release()
        return result

    def get_album_from_hash(self, hash):
        self.lock.acquire()
        result = Cursor().fetch_all('SELECT album FROM my_table WHERE hash = ?', (hash,), close=True)
        self.lock.release()
        return result
