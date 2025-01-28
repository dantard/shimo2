import os
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
        self.connection = sqlite3.connect('my_database2.db')
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
        # self.cursor.close()
        if commit:
            self.connection.commit()
        self.connection.close()


class Database:

    def __init__(self):
        self.directory = "shared-album"
        self.directory = "album"
        self.connection = sqlite3.connect('my_database2.db')
        # Create a cursor object to execute SQL commands
        self.cursor = self.connection.cursor()
        self.lock = Lock()
        # Example: Create a table if you want
        # set wal mode
        # self.cursor.execute("PRAGMA journal_mode=WAL")
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS my_table (
            id INTEGER PRIMARY KEY,
            remote TEXT NOT NULL,
            album TEXT NOT NULL,
            file TEXT NOT NULL,
            hash TEXT NOT NULL,
            touched INTEGER,
            seen INTEGER DEFAULT 0,
            UNIQUE(album,file)
        )''')
        self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS remotes (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
        )''')

        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS saved (id INTEGER primary key, filename text, album text, type integer)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS sequence (id INTEGER, date float)''')
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS albums (id INTEGER primary key, remote text, title text, active integer, touched integer, UNIQUE(remote, title))''')

        # Commit the changes
        self.connection.commit()

    def add_folder(self, folder):
        self.lock.acquire()
        Cursor().execute('INSERT INTO remotes (name) VALUES (?)', ("file:"+folder,), commit=True, close=True)
        self.lock.release()

    def update_folder(self, remote):
        sub_dirs = [(d, d) for d in os.listdir(remote) if os.path.isdir(os.path.join(remote, d))]
        self.update_albums("file:"+ remote, sub_dirs)

    def add_remote(self, remote):
        self.lock.acquire()
        Cursor().execute('INSERT INTO remotes (name) VALUES (?)', (remote,), commit=True, close=True)
        self.lock.release()

    def update_remote(self, remote):

        result = subprocess.run(['rclone', "lsf", remote, "--max-depth", "1", "--format", "pi"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)
        folders = []
        for line in result.stdout.splitlines():
            album, hash = line.split(";")
            folders.append((album, hash))
        folders.sort(key=lambda x: x[0], reverse=True)

        self.update_albums(remote, folders)

    def update_albums(self, remote, folders):
        self.lock.acquire()
        cursor = Cursor()
        cursor.execute('''UPDATE albums SET touched = ? where remote = ?''', (0, remote))

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
        self.lock.release()

    def get_albums(self, remote):
        self.lock.acquire()
        albums = Cursor().fetch_all('SELECT remote, title, active FROM albums WHERE remote = ? order by title desc',
                                    (remote,), close=True)
        self.lock.release()
        return albums

    def set_saved(self, filename, album, type):
        self.lock.acquire()
        cursor = Cursor()
        cursor.execute('INSERT INTO saved (filename, album, type) VALUES (?, ?, ?)', (filename, album, type),
                       commit=True, close=True)
        self.lock.release()

    def get_remotes(self):
        self.lock.acquire()
        remotes = Cursor().fetch_all('SELECT name FROM remotes', close=True)
        self.lock.release()
        return [x[0] for x in remotes]

    # def insert_recent(self, id):
    #     cursor = Cursor()
    #     cursor.execute('''DELETE FROM sequence
    #         WHERE id NOT IN (
    #         SELECT id
    #         FROM sequence
    #         ORDER BY date DESC
    #         LIMIT 10
    #     );''')
    #     cursor.execute('INSERT INTO sequence (id, date) VALUES (?, ?)', (id, time.time()), commit=True, close=True)
    #
    # def get_recent_ids(self):
    #     ids = Cursor().fetch_all('SELECT id FROM sequence', close=True)
    #     return [x[0] for x in ids]

    def remove_album(self, remote, album):
        # Delete from my_table all the file of the specified album
        self.lock.acquire()
        Cursor().execute('DELETE FROM my_table WHERE remote = ? AND album = ?', (remote, album), commit=True,
                         close=True)
        self.lock.release()

    def update_album_active(self, remote, album, active):
        self.lock.acquire()
        Cursor().execute('UPDATE albums SET active = ? where remote = ? and title = ?', (active, remote, album),
                         commit=True, close=True)
        self.lock.release()

    def update_folder_album(self, remote, album):
        path = remote.replace("file:", "") + "/" + album
        files = [(x, x) for x in os.listdir(path) if os.path.isfile(os.path.join(path, x)) and x.lower().endswith(('.jpg'))]
        self.update_files("file:" + remote, album, files)

    def update_remote_album(self, remote, album):

        result = subprocess.run(['rclone', "lsf", remote + "/" + album,
                                 "--max-depth", "2", "--format", "pi"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)
        lines = result.stdout.splitlines()
        files = []
        for line in lines:
            filename, hash = line.split(";")
            files.append((filename, hash))
        self.update_files(remote, album, files)

    def update_files(self, remote, album, files):

        self.lock.acquire()
        cursor = Cursor()
        cursor.execute('''UPDATE my_table SET touched = 0 WHERE remote = ? and album = ?''', (remote, album))

        # new entry have touched = 2
        min_seen = cursor.execute('SELECT MIN(seen) FROM my_table').fetchone()[0]

        if min_seen is None:
            min_seen = 0

        for filename, hash in files:

            cursor.execute('''INSERT INTO my_table (remote, album, file, hash, touched, seen) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(album,file) DO UPDATE SET touched = 1''', (remote, album, filename, hash, 2, 0))

        # update the seen of the touched == 2 to the min_seen
        cursor.execute('UPDATE my_table SET seen = ? WHERE touched = 2', (min_seen,), commit=True)

        cursor.execute('DELETE FROM my_table WHERE touched = 0')
        cursor.close(True)
        self.lock.release()


    def remove_remote(self, remote):
        self.lock.acquire()
        Cursor().execute('DELETE FROM remotes WHERE name = ?', (remote,), commit=True, close=True)
        Cursor().execute('DELETE FROM albums WHERE remote = ?', (remote,), commit=True, close=True)
        Cursor().execute('DELETE FROM my_table WHERE remote = ?', (remote,), commit=True, close=True)
        self.lock.release()

    def get_ids_by_album(self, remote, album):
        self.lock.acquire()
        ids = Cursor().fetch_all('SELECT id FROM my_table WHERE remote = ? and album = ?', (remote, album), close=True)
        self.lock.release()
        return [x[0] for x in ids]

    def get_ids(self):
        self.lock.acquire()
        ids = Cursor().fetch_all('SELECT DISTINCT id FROM my_table', close=True)
        self.lock.release()
        return [x[0] for x in ids]

    def get_ids_by_seen(self):
        self.lock.acquire()

        # get the ids of the images that have been seen the least
        # first get the minimum number of times an image has been seen
        min_seen = Cursor().fetch_one('SELECT MIN(seen) FROM my_table', close=True)[0]

        # get the ids of the images that have been seen the least but unique on hash
        ids = Cursor().fetch_all('SELECT id FROM my_table WHERE seen = ? GROUP BY hash', (min_seen,), close=True)
        # ids = Cursor().fetch_all('SELECT id FROM my_table WHERE seen = ?', (min_seen,), close=True)
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

    def count(self, remote, album):
        self.lock.acquire()
        result = Cursor().fetch_one('SELECT count(*) FROM my_table WHERE remote = ? and album = ?', (remote, album),
                                    close=True)
        self.lock.release()
        return result[0]

    def increment_seen(self, index):
        self.lock.acquire()
        Cursor().execute('UPDATE my_table SET seen = seen + 1 WHERE id = ?', (index,), commit=True, close=True)
        self.lock.release()

    def get_less_seen_count(self):
        self.lock.acquire()
        result = Cursor().fetch_one('SELECT MIN(seen) FROM my_table', close=True)
        self.lock.release()
        return result[0]
