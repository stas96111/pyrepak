from aaaa import PakBuilder, RepakStream


with open(r"C:\Users\Stas\AppData\Roaming\Thunderstore Mod Manager\DataFolder\VotV\cache\Gatohost-PetFloppa\1.0.1\pak\PetFloppaMod.pak", "rb") as f:
    stream = RepakStream(f)
    
    # Create a builder and reader
    builder = PakBuilder()
    reader = builder.reader(stream)
    
    # Get pak info
    print(f"Pak version: {reader.version}")
    print(f"Mount point: {reader.mount_point}")
    
    # List files
    files = reader.files()
    print(f"Files in pak ({len(files)}):")
    for file_path in files:
        print(f"  - {file_path}")
    
    # Read a file
    content = reader.get("folder/example.uasset", stream)
    if content:
        print(f"Content of folder/example.uasset: {content}")