from pyrepak import PakBuilder, RepakStream, Compression, Version


with open(".path/to/file.pak", "wb") as f:
    stream = RepakStream(f)
    
    # Create a builder with compression
    builder = PakBuilder()
    builder.key(b"YOUR_KEY")
    builder.compression([Compression.ZLIB])
    
    # Create a writer
    writer = builder.writer(stream, Version.V10)
    
    # Add some files
    writer.write_file("example.txt", b"Hello, world!")
    writer.write_file("data/config.ini", b'...data')
    
    # Finalize the pak
    writer.write_index()