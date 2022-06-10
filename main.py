#!/usr/bin/env python3
import stat, os, errno, fuse, requests
from time import sleep
from typing import Generator

fuse.fuse_python_api = (0, 2)

USERAGENT = "f621/1.0 (github.com/chfour)"

def _size_to_readable(n: int) -> str:
    i = 1
    while n / (1024**i) > 1:
        n = n / (1024**i)
        i += 1
    return f"{round(n)} " + [None, "KiB", "MiB", "GiB"][i-1]

class E6Post:
    def __repr__(self) -> str:
        return f"E6Post#{self.data['id']}"

    @classmethod
    def from_json(cls, data: dict, api="https://e621.net") -> "E6Post":
        new_object = cls(None)
        new_object.data = data
        new_object.api = api
        new_object.post_id = new_object.data["id"]
        new_object.info_request = None
        new_object.images = {}
        return new_object
    
    def __init__(self, post_id: int | None, api="https://e621.net") -> None:
        if post_id is None: return
        self.images = {}

        self.api = api
        
        self.post_id = post_id
        self.info_request = requests.get(f"{api}/posts/{post_id}.json", headers={"user-agent": USERAGENT})
        if not self.info_request.ok:
            raise RuntimeError(f"got {self.info_request.status_code} for #{post_id}, data={self.info_request.text!r}, path={self.info_request.url}")
        self.data = self.info_request.json()["post"]

    def update_data(self, data: dict) -> None:
        self.data = data
        self.post_id = self.data["id"]
        self.info_request = None
    
    def get_image(self, fmt="file") -> bytes:
        if fmt not in self.images:
            image = requests.get(self.data[fmt]["url"], headers={"user-agent": USERAGENT})
            if not image.ok:
                raise RuntimeError(f"got {self.info_request.status_code} for image:{fmt}#{post_id}, data={image.text!r}, path={image.url}")
            self.images[fmt] = image
        return self.images[fmt].content

    def get_image_size(self, fmt="file") -> int:
        if fmt == "file":
            return self.data["file"]["size"]
        else:
            return len(self.get_image(fmt=fmt))

    def generate_info(self) -> str:
        output = f"ID: {self.post_id}\nURL: {self.api}/posts/{self.post_id}\n"

        if len(self.data["description"]) > 0:
            output += "Description:\n " + "\n ".join(self.data["description"].replace("\r", "").split("\n")) + "\n"
        else:
            output += "Description: (none)\n"

        output += "\n"
        
        for field in ["artist", "copyright", "character", "species", "lore", "general", "meta", "invalid"]:
            if len(self.data["tags"][field]):
                output += {"artist": "Artists", "copyright": "Copyrights", "character": "Characters"}.get(field, field.title()) + ":\n "
                output += "\n ".join(self.data["tags"][field]) + "\n"
        
        output += "\nSource[s]:\n " + "\n ".join(self.data["sources"]) + "\n" + \
            f"Rating: " + {"s": "Safe", "e": "Explicit", "q": "Questionable"}[self.data["rating"]] + "\n" + \
            f"Score: {self.data['score']['total']} ({self.data['score']['up']} up/{self.data['score']['down']} down)\n" + \
            f"Posted: {self.data['created_at']} (updated {self.data['updated_at']})\n" + \
            f"Size: {self.data['file']['width']}x{self.data['file']['height']} ({_size_to_readable(self.data['file']['size'])})\n" + \
            f"Favorites: {self.data['fav_count']}\nMD5: {self.data['file']['md5']}\n"
        
        if self.data["relationships"]["parent_id"] is not None:
            output += f"Parent post: {self.data['relationships']['parent_id']}\n"
        
        if self.data["relationships"]["has_children"]:
            output += f"Children: " + " ".join([str(c) for c in self.data["relationships"]["children"]]) + "\n"
        
        if len(self.data["pools"]) > 0:
            output += f"Pools: " + " ".join(self.data["pools"]) + "\n"
        
        return output


class TheFS(fuse.Fuse):
    api = "https://e621.net"
    postsdir = "/posts/"
    files = {"/tags": b"rating:safe ralsei\n", "/size": b"sample\n", "/page": b"1\n"}
    cache = {}
    

    def load_page(self, page_no: int | str, tags="", limit=10) -> list:
        r = requests.get(f"{self.api}/posts.json", params={"limit": limit, "page": str(page_no), "tags": tags}, headers={"user-agent": USERAGENT})
        if not r.ok:
            raise RuntimeError(f"got {r.status_code} for /posts, tags={tags!r} page={page_no} limit={limit}, data={r.text!r}, path={r.url}")

        data = r.json()
        print(f"caching {len(data['posts'])} posts")
        
        page_listing = []
        for post in data["posts"]:
            if post["id"] in self.cache:
                self.cache[post["id"]].update_data(post)
                post = self.cache[post["id"]]
            else:
                post = E6Post.from_json(post)
                post.api = self.api
                self.cache[post.data["id"]] = post
            page_listing.append(post)
        
        return page_listing

    def get_post(self, post_id: int) -> E6Post:
        if post_id in self.cache:
            return self.cache[post_id]
        
        self.cache[post_id] = E6Post(post_id, api=self.api)
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
        elif path in self.files:
            st.st_mode = stat.S_IFREG | 0o444
            st.st_nlink = 1
            st.st_size = len(self.files[path])
            print(f"getattr {path} -> {st.__dict__}")
        elif path.startswith(self.postsdir):
            st.st_mode = stat.S_IFREG | 0o444
            st.st_nlink = 1
            try:
                if "_" in path:
                    post_id = int(path[len(self.postsdir):path.index("_")])
                else:
                    post_id = int(path[len(self.postsdir):])
            except ValueError:
                print(f"getattr {path} (not int) -> ENOENT")
                return -errno.ENOENT
            
            try:
                post = self.get_post(post_id)
            except RuntimeError as e:
                print(f"getattr {path} (error fetching post: {e}) -> ENOENT")
                return -errno.ENOENT

            if path.endswith("_info"):
                st.st_size = len(post.generate_info().encode("utf-8"))
            else:
                image_size = self.files["/size"].decode("utf-8").strip()
                if image_size not in ["file", "sample", "preview"]:
                    image_size = "sample"
                self.files["/size"] = (image_size + "\n").encode("utf-8")
                st.st_size = post.get_image_size(fmt=image_size)
        else:
            print(f"getattr {path} -> ENOENT")
            return -errno.ENOENT
        
        print(f"getattr {path} -> {st.__dict__}")
        return st

    def readdir(self, path, offset) -> Generator[fuse.Direntry, None, None] | int:
        dir_listing = [".", ".."]
        if path == "/":
            dir_listing += [self.postsdir[1:-1]] + [e[1:] for e in self.files]
        elif path == self.postsdir[:-1]:
            tags = self.files["/tags"].decode("utf-8").strip()
            self.files["/tags"] = (tags + "\n").encode("utf-8")

            page = int(self.files["/page"].decode("utf-8").strip())
            self.files["/page"] = (str(page) + "\n").encode("utf-8")
            
            try:
                page = self.load_page(page, tags=tags)
                print(page)
            except RuntimeError as e:
                print(f"{path} (error fetching post: {e}) -> ENOENT")
                return -errno.EIO
            dir_listing += [str(p.post_id) for p in page]
            dir_listing += [f"{p.post_id}_info" for p in page]
        else:
            print(f"readdir {path} o{offset} -> ENOENT")
            return -errno.ENOENT
        
        print(f"readdir {path} o{offset} -> {dir_listing}")
        for f in dir_listing:
            yield fuse.Direntry(f)

    def open(self, path, flags) -> int:
        if path in self.files:
            print(f"open {path} {flags:b} -> 0 (OK)")
            return 0
        elif path.startswith(self.postsdir):
            try:
                if "_" in path:
                    post_id = int(path[len(self.postsdir):path.index("_")])
                else:
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
        if path in self.files:
            buf = self.files[path][offset:offset+size]
            print(f"read {path} s{size} o{offset} -> bytes[{len(buf)}]")
            return buf
        elif path.startswith(self.postsdir):
            try:
                if "_" in path:
                    post_id = int(path[len(self.postsdir):path.index("_")])
                else:
                    post_id = int(path[len(self.postsdir):])
            except ValueError:
                print(f"getattr {path} (not int) -> ENOENT")
                return -errno.ENOENT
            
            try:
                post = self.get_post(post_id)
            except RuntimeError as e:
                print(f"getattr {path} (error fetching post: {e}) -> ENOENT")
                return -errno.EIO

            if path.endswith("_info"):
                buf = post.generate_info().encode("utf-8")[offset:offset+size]
            else:
                image_size = self.files["/size"].decode("utf-8").strip()
                if image_size not in ["file", "sample", "preview"]:
                    image_size = "sample"
                self.files["/size"] = (image_size + "\n").encode("utf-8")

                try:
                    image_data = post.get_image(fmt=image_size)
                except RuntimeError as e:
                    print(f"getattr {path} (error fetching post image: {e}) -> ENOENT")
                    return -errno.EIO

                buf = image_data[offset:offset+size]
            
            print(f"read {path} s{size} o{offset} -> bytes[{len(buf)}]")
            return buf
        else:
            print(f"getattr {path} -> ENOENT")
            return -errno.ENOENT

    def truncate(self, path, size) -> int:
        if path not in self.files:
            print(f"truncate {path} {size} -> EACCES")
            return -errno.EACCES
        print(f"truncate {path} {size} -> 0 (OK)")
        self.files[path] = self.files[path][:size]
        return 0

    def write(self, path, buf, offset) -> int:
        if path not in self.files:
            print(f"write {path} {buf} o{offset} -> EACCES")
            return -errno.EACCES
        self.files[path] = self.files[path][:offset] + buf + self.files[path][offset+len(buf):]
        print(f"write {path} {buf} o{offset} -> {buf}")
        return len(buf)

def main() -> None:
    server = TheFS(dash_s_do="setsingle")
    server.parse(errex=1)
    server.main()

if __name__ == "__main__":
    main()
