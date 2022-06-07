#!/usr/bin/env python3
import stat, os, errno, fuse, requests
from time import sleep
from typing import Generator

fuse.fuse_python_api = (0, 2)

FILES = {"/test": b"Hello, world!\n"}
USERAGENT = "f621/1.0 (github.com/chfour)"

class E6Post:
    def __init__(self, post_id: int, api="https://e621.net") -> None:
        self.post_id = post_id
        self.info_request = requests.get(f"{api}/posts/{post_id}.json", headers={"user-agent": USERAGENT})
        if not self.info_request.ok:
            raise RuntimeError(f"got {self.info_request.status_code} for #{post_id}, data={self.info_request.text!r}, path={self.info_request.url}")
        self.data = self.info_request.json()

class TheFS(fuse.Fuse):
    postsdir = "/posts/"
    cache = {}

    def get_post(self, post_id: int) -> E6Post:
        if post_id in self.cache:
            return self.cache[post_id]
        
        self.cache[post_id] = E6Post(post_id)
        return self.cache[post_id]

    def getattr(self, path: str) -> fuse.Stat | int:
        st = fuse.Stat()
        
        if path == "/":
            st.st_mode = stat.S_IFDIR | 0o777
            st.st_nlink = 2
            print(f"getattr {path} -> {st.__dict__}")
        elif path == self.postsdir[:-1]:
            st.st_mode = stat.S_IFDIR | 0o444
            st.st_nlink = 2
            print(f"getattr {path} -> {st.__dict__}")
        elif path in FILES:
            st.st_mode = stat.S_IFREG | 0o444
            st.st_nlink = 1
            st.st_size = len(FILES[path])
            print(f"getattr {path} -> {st.__dict__}")
        elif path.startswith(self.postsdir):
            try:
                post_id = int(path[len(self.postsdir):])
            except ValueError:
                print(f"getattr {path} (not int) -> ENOENT")
                return -errno.ENOENT
            
            try:
                post = self.get_post(post_id)
            except RuntimeError as e:
                print(f"getattr {path} (error fetching post: {e}) -> ENOENT")
                return -errno.ENOENT
            
            st.st_mode = stat.S_IFREG | 0o444
            st.st_nlink = 1
            st.st_size = len(post.info_request.content)
        else:
            print(f"getattr {path} -> ENOENT")
            return -errno.ENOENT
        
        print(f"getattr {path} -> {st.__dict__}")
        return st

    def readdir(self, path, offset) -> Generator[fuse.Direntry, None, None] | int:
        dir_listing = [".", ".."]
        if path == "/":
            dir_listing += [self.postsdir[1:-1]] + [e[1:] for e in FILES]
        elif path == self.postsdir[:-1]:
            pass
        else:
            print(f"readdir {path} o{offset} -> ENOENT")
            return -errno.ENOENT
        
        print(f"readdir {path} o{offset}")
        for f in dir_listing:
            yield fuse.Direntry(f)

    def open(self, path, flags) -> int:
        if path in FILES:
            print(f"open {path} {flags:b} -> 0 (OK)")
            return 0
        elif path.startswith(self.postsdir):
            try:
                post_id = int(path[len(self.postsdir):])
            except ValueError:
                print(f"open {path} (not int) -> ENOENT")
                return -errno.ENOENT

            if flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR) != os.O_RDONLY:
                print(f"open {path} {flags:b} (not readonly) -> EACCES")
                return -errno.EACCES
            
            try:
                self.get_post(post_id)
            except RuntimeError as e:
                print(f"open {path} (error fetching post: {e}) -> ENOENT")
                return -errno.ENOENT
            
            print(f"open {path} #{post_id} {flags:b} -> 0 (OK)")
            return 0
        else:
            print(f"open {path} -> ENOENT")
            return -errno.ENOENT

    def read(self, path, size, offset) -> bytes | int:
        if path in FILES:
            buf = FILES[path][offset:offset+size]
            print(f"read {path} s{size} o{offset} -> bytes[{len(buf)}]")
            return buf
        elif path.startswith(self.postsdir):
            try:
                post_id = int(path[len(self.postsdir):])
            except ValueError:
                print(f"getattr {path} (not int) -> ENOENT")
                return -errno.ENOENT
            
            try:
                post = self.get_post(post_id)
            except RuntimeError as e:
                print(f"getattr {path} (error fetching post: {e}) -> ENOENT")
                return -errno.ENOENT

            buf = post.info_request.content[offset:offset+size]
            print(f"read {path} s{size} o{offset} -> bytes[{len(buf)}]")
            return buf
        else:
            print(f"getattr {path} -> ENOENT")
            return -errno.ENOENT

    def truncate(self, path, size) -> int:
        if path not in FILES:
            print(f"truncate {path} {size} -> EACCES")
            return -errno.EACCES
        print(f"truncate {path} {size} -> 0 (OK)")
        FILES[path] = FILES[path][:size]
        return 0

    def write(self, path, buf, offset) -> int:
        if path not in FILES:
            print(f"write {path} {buf} o{offset} -> EACCES")
            return -errno.EACCES
        FILES[path] = FILES[path][:offset] + buf + FILES[path][offset+len(buf):]
        print(f"write {path} {buf} o{offset} -> {buf}")
        return len(buf)

def main() -> None:
    server = TheFS(dash_s_do="setsingle")
    server.parse(errex=1)
    server.main()

if __name__ == "__main__":
    main()
