import stat, os, errno, fuse
from typing import Generator

fuse.fuse_python_api = (0, 2)

FILES = {"/test": b"Hello, world!"}

class TheFS(fuse.Fuse):
    def getattr(self, path: str) -> fuse.Stat | int:
        st = fuse.Stat()
        
        if path == "/":
            st.st_mode = stat.S_IFDIR | 0o755
            st.st_nlink = 2
        elif path in FILES:
            st.st_mode = stat.S_IFREG | 0o444
            st.st_nlink = 1
            st.st_size = len(FILES[path])
        else:
            print(f"getattr {path} -> ENOENT")
            return -errno.ENOENT
        
        print(f"getattr {path} -> {st.__dict__}")
        return st

    def readdir(self, path, offset) -> Generator[fuse.Direntry, None, None]:
        print(f"readdir {path} o{offset}")
        for f in [".", ".."] + [e[1:] for e in FILES]:
            yield fuse.Direntry(f)

    def open(self, path, flags) -> None | int:
        if path not in FILES:
            print(f"open {path} {flags:b} -> ENOENT")
            return -errno.ENOENT

        if flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR) != os.O_RDONLY:
            print(f"open {path} {flags:b} -> EACCES")
            return -errno.EACCES
        
        print(f"open {path} {flags:b} -> OK")

    def read(self, path, size, offset) -> bytes | int:
        if path not in FILES:
            print(f"read {path} s{size} o{offset} -> ENOENT")
            return -errno.ENOENT

        buf = FILES[path][offset:size]
        print(f"read {path} s{size} o{offset} -> bytes[{len(buf)}]")
        return buf

def main() -> None:
    server = TheFS(dash_s_do="setsingle")
    server.parse(errex=1)
    server.main()

if __name__ == "__main__":
    main()
