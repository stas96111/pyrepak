import os
import sys
import ctypes
from cffi import FFI

ffi = FFI()

# Define the C interface that matches your Rust FFI definitions
ffi.cdef("""
    // Enum definitions (you may need to adjust these based on the actual definitions)
    typedef enum {
        NONE = 0,
        ZLIB = 1,
        ZSTD = 2,
        OODLE = 3,
    } Compression;

    typedef enum {
        V1 = 1,
        V2 = 2,
        V3 = 3,
        V4 = 4,
        V5 = 5,
        V6 = 6,
        V7 = 7,
        V8A = 8,
        V8B = 9,
        V9 = 10,
        V10 = 11,
        V11 = 12,
    } Version;

    // Callback structure
    struct StreamCallbacks {
        void* context;
        intptr_t (*read)(void* context, unsigned char* buffer, size_t length);
        intptr_t (*write)(void* context, const unsigned char* buffer, size_t length);
        int64_t (*seek)(void* context, int64_t offset, int whence);
        int (*flush)(void* context);
    };

    // Function declarations
    void* pak_builder_new();
    void pak_builder_drop(void* builder);
    void pak_reader_drop(void* reader);
    void pak_writer_drop(void* writer);
    void pak_buffer_drop(unsigned char* buf, size_t len);
    void pak_cstring_drop(char* cstring);
    void* pak_builder_key(void* builder, const unsigned char (*key)[32]);
    void* pak_builder_compression(void* builder, const Compression* compressions, size_t length);
    void* pak_builder_reader(void* builder, struct StreamCallbacks ctx);
    void* pak_builder_writer(void* builder, struct StreamCallbacks ctx, Version version, const char* mount_point, uint64_t path_hash_seed);
    Version pak_reader_version(void* reader);
    const char* pak_reader_mount_point(void* reader);
    int pak_reader_get(void* reader, const char* path, struct StreamCallbacks ctx, unsigned char** buffer, size_t* length);
    char** pak_reader_files(void* reader, size_t* len);
    void pak_drop_files(char** buf, size_t len);
    int pak_writer_write_file(void* writer, const char* path, const unsigned char* data, size_t data_len);
    int pak_writer_write_index(void* writer);
""")

script_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(script_dir, 'repak_bind.dll')
lib = ffi.dlopen(lib_path)

# Define Python wrapper classes
class RepakStream:
    def __init__(self, fileobj=None):
        """
        Create a stream from a file-like object or use in-memory buffer if fileobj is None
        """
        self.fileobj = fileobj
        self.buffer = bytearray() if fileobj is None else None
        self.position = 0
        
        @ffi.callback("intptr_t(void*, unsigned char*, size_t)")
        def read_callback(ctx, buffer, length):
            try:
                if self.fileobj:
                    data = self.fileobj.read(length)
                    if not data:
                        return 0
                    ffi.memmove(buffer, data, len(data))
                    return len(data)
                else:
                    # In-memory read
                    remaining = len(self.buffer) - self.position
                    to_read = min(remaining, length)
                    if to_read <= 0:
                        return 0
                    ffi.memmove(buffer, self.buffer[self.position:self.position+to_read], to_read)
                    self.position += to_read
                    return to_read
            except Exception as e:
                print(f"Read error: {e}")
                return -1
                
        @ffi.callback("intptr_t(void*, const unsigned char*, size_t)")
        def write_callback(ctx, buffer, length):
            try:
                data = bytes(ffi.buffer(buffer, length))
                if self.fileobj:
                    bytes_written = self.fileobj.write(data)
                    return bytes_written
                else:
                    # In-memory write
                    if self.position == len(self.buffer):
                        # Append to the end
                        self.buffer.extend(data)
                    else:
                        # Overwrite existing bytes and potentially extend
                        self.buffer[self.position:self.position+len(data)] = data
                        if self.position + len(data) > len(self.buffer):
                            self.buffer.extend(data[-(self.position + len(data) - len(self.buffer)):])
                    self.position += len(data)
                    return len(data)
            except Exception as e:
                print(f"Write error: {e}")
                return -1
                
        @ffi.callback("int64_t(void*, int64_t, int)")
        def seek_callback(ctx, offset, whence):
            try:
                if self.fileobj:
                    if whence == 0:  # SEEK_SET
                        self.fileobj.seek(offset)
                    elif whence == 1:  # SEEK_CUR
                        self.fileobj.seek(offset, 1)
                    elif whence == 2:  # SEEK_END
                        self.fileobj.seek(offset, 2)
                    return self.fileobj.tell()
                else:
                    # In-memory seek
                    if whence == 0:  # SEEK_SET
                        new_pos = offset
                    elif whence == 1:  # SEEK_CUR
                        new_pos = self.position + offset
                    elif whence == 2:  # SEEK_END
                        new_pos = len(self.buffer) + offset
                    else:
                        return -1
                    
                    if new_pos < 0:
                        return -1
                    
                    # If seeking beyond the end, extend the buffer
                    if new_pos > len(self.buffer):
                        self.buffer.extend(b'\0' * (new_pos - len(self.buffer)))
                    
                    self.position = new_pos
                    return self.position
            except Exception as e:
                print(f"Seek error: {e}")
                return -1
                
        @ffi.callback("int(void*)")
        def flush_callback(ctx):
            try:
                if self.fileobj and hasattr(self.fileobj, 'flush'):
                    self.fileobj.flush()
                return 0
            except Exception as e:
                print(f"Flush error: {e}")
                return -1
                
        # Keep references to callbacks to prevent garbage collection
        self._read_cb = read_callback
        self._write_cb = write_callback
        self._seek_cb = seek_callback
        self._flush_cb = flush_callback
        
        # Create the C structure
        self.callbacks = ffi.new("struct StreamCallbacks *", {
            "context": ffi.NULL,
            "read": self._read_cb,
            "write": self._write_cb,
            "seek": self._seek_cb,
            "flush": self._flush_cb
        })

    def get_callbacks(self):
        return self.callbacks[0]
        
    def get_buffer(self):
        """Return the current buffer if using in-memory mode"""
        if self.buffer is not None:
            return bytes(self.buffer)
        return None


class PakBuilder:
    def __init__(self):
        self.builder = lib.pak_builder_new()
        if self.builder == ffi.NULL:
            raise RuntimeError("Failed to create PakBuilder")
    
    def __del__(self):
        if hasattr(self, 'builder') and self.builder != ffi.NULL:
            lib.pak_builder_drop(self.builder)
            self.builder = ffi.NULL
    
    def key(self, key_bytes):
        """Set encryption key"""
        if len(key_bytes) != 32:
            raise ValueError("Key must be exactly 32 bytes")
        key_array = ffi.new("unsigned char[32]")
        for i, b in enumerate(key_bytes):
            key_array[i] = b
        
        new_builder = lib.pak_builder_key(self.builder, ffi.cast("const unsigned char (*)[32]", key_array))
        if new_builder == ffi.NULL:
            raise RuntimeError("Failed to set key")
        
        # Update our builder pointer and prevent old one from being freed
        self.builder = new_builder
        return self
    
    def compression(self, compression_list):
        """Set compression methods"""
        compressions = ffi.new("Compression[]", compression_list)
        new_builder = lib.pak_builder_compression(self.builder, compressions, len(compression_list))
        if new_builder == ffi.NULL:
            raise RuntimeError("Failed to set compression")
        
        # Update our builder pointer and prevent old one from being freed
        self.builder = new_builder
        return self
    
    def reader(self, stream):
        """Create a PakReader from a stream"""
        reader_ptr = lib.pak_builder_reader(self.builder, stream.get_callbacks())
        if reader_ptr == ffi.NULL:
            raise RuntimeError("Failed to create reader")
        
        # Create a PakReader and transfer ownership
        reader = PakReader(reader_ptr)
        self.builder = ffi.NULL  # Builder is consumed
        return reader
    
    def writer(self, stream, version=12, mount_point="../../../", path_hash_seed=0):
        """Create a PakWriter from a stream"""
        c_mount_point = ffi.new("char[]", mount_point.encode('utf-8'))
        writer_ptr = lib.pak_builder_writer(
            self.builder, 
            stream.get_callbacks(), 
            version,
            c_mount_point, 
            path_hash_seed
        )
        if writer_ptr == ffi.NULL:
            raise RuntimeError("Failed to create writer")
        
        # Create a PakWriter and transfer ownership
        writer = PakWriter(writer_ptr)
        self.builder = ffi.NULL  # Builder is consumed
        return writer


class PakReader:
    def __init__(self, reader_ptr=None):
        self.reader = reader_ptr
    
    def __del__(self):
        if hasattr(self, 'reader') and self.reader != ffi.NULL:
            lib.pak_reader_drop(self.reader)
            self.reader = ffi.NULL
    
    @property
    def version(self):
        """Get pak file version"""
        return lib.pak_reader_version(self.reader)
    
    @property
    def mount_point(self) -> str:
        """Get pak file mount point"""
        c_str = lib.pak_reader_mount_point(self.reader)
        result = ffi.string(c_str).decode('utf-8')
        lib.pak_cstring_drop(c_str)
        return result
    
    def get(self, path, stream=None):
        """Get file content by path"""
        if stream is None:
            stream = RepakStream()
        
        # If the path doesn't start with the mount point, add it first
        
        c_path = ffi.new("char[]", path.encode('utf-8'))
        buffer_ptr = ffi.new("unsigned char**")
        length_ptr = ffi.new("size_t*")
 
        
        # Add debug output
        print(f"Requesting file: {path}")
        
        result = lib.pak_reader_get(self.reader, c_path, stream.get_callbacks(), buffer_ptr, length_ptr)
        if result != 0:
            print(f"Failed to get file")
            return None
        
        # Check if the buffer is NULL
        if buffer_ptr[0] == ffi.NULL:
            print("pak_reader_get returned NULL buffer")
            return None
        
        # Copy the data and free the original buffer
        data = bytes(ffi.buffer(buffer_ptr[0], length_ptr[0]))
        lib.pak_buffer_drop(buffer_ptr[0], length_ptr[0])
        return data

    # Change 2: Enhance debugging for files() method
    def files(self):
        """Get list of files in the pak"""
        length_ptr = ffi.new("size_t*")
        files_ptr = lib.pak_reader_files(self.reader, length_ptr)
        
        if files_ptr == ffi.NULL:
            print("pak_reader_files returned NULL")
            return []
        
        files = []
        for i in range(length_ptr[0]):
            c_str = files_ptr[i]
            if c_str == ffi.NULL:
                print(f"Warning: NULL string at index {i}")
                continue
            file_path = ffi.string(c_str).decode('utf-8')
            files.append(file_path)
        
        # Free the file list
        lib.pak_drop_files(files_ptr, length_ptr[0])
        return files

class PakWriter:
    def __init__(self, writer_ptr):
        self.writer = writer_ptr
    
    def __del__(self):
        if hasattr(self, 'writer') and self.writer != ffi.NULL:
            lib.pak_writer_drop(self.writer)
            self.writer = ffi.NULL
    
    def write_file(self, path, data):
        """Write a file to the pak"""
        c_path = ffi.new("char[]", path.encode('utf-8'))
        buffer = ffi.new("unsigned char[]", data)
        
        result = lib.pak_writer_write_file(self.writer, c_path, buffer, len(data))
        if result != 0:
            raise RuntimeError(f"Failed to write file: {path}")
        return True
    
    def write_index(self):
        """Write the pak index"""
        result = lib.pak_writer_write_index(self.writer)
        if result != 0:
            raise RuntimeError("Failed to write index")
        self.writer = ffi.NULL  # Writer is consumed after write_index
        return True

# Constants
class Compression:
    NONE = 0
    ZLIB = 1
    ZSTD = 2
    OODLE = 3

class Version:
    V1 = 1
    V2 = 2
    V3 = 3
    V4 = 4
    V5 = 5
    V6 = 6
    V7 = 7
    V8A = 8
    V8B = 9
    V9 = 10
    V10 = 11
    V11 = 12