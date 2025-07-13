# MFA Technical Specification

## Binary Structure Details

### 1. mlxfwmanager Binary Layout

The mlxfwmanager files are ELF executables with embedded ZIP archives. The structure is:

```
[ELF Header]
[Program Headers]
[Code/Data Sections]
...
[ZIP Archive 1] @ offset varies
[ZIP Archive 2] @ offset varies (optional)
...
[ELF Section Headers]
```

ZIP archives are identified by the signature `50 4B 03 04` (PK\x03\x04).

### 2. ZIP Archive Contents

Each ZIP typically contains:
- `srcs.mfa` - The main MFA file with firmware images
- Other support files (varies by version)

### 3. MFA File Detailed Structure

#### 3.1 MFA Header (16 bytes)
```
Offset  Size  Description
0x00    4     Magic: "MFAR" (0x4D, 0x46, 0x41, 0x52)
0x04    4     Version: 0x00000001 (big-endian)
0x08    8     Reserved (zeros)
```

#### 3.2 Section Headers (8 bytes each)
```
Offset  Size  Description
0x00    1     Type (1=MAP, 2=TOC, 3=DATA)
0x01    2     Reserved
0x03    1     Flags (bit 0: XZ compressed)
0x04    4     Section size (bytes)
```

### 4. XZ Compression Details

XZ streams in MFA files use:
- Stream header: `FD 37 7A 58 5A 00` (6 bytes)
- Check type: CRC64 or SHA256
- LZMA2 filter with default settings

Multiple XZ streams can be concatenated in srcs.mfa:
1. First stream: Often contains metadata/mappings
2. Subsequent streams: Contain firmware images

### 5. Firmware Image Formats

#### 5.1 Image Headers by Generation

**FS3 Format** (older cards):
```
Offset  Size  Description
0x00    21    Magic signature (see main doc)
0x15    ...   Firmware data
```

**FS4 Format** (ConnectX-4 and newer):
```
Offset  Size  Description
0x00    24    Magic signature
0x18    ...   Firmware data
```

**FS5 Format** (latest):
```
Offset  Size  Description
0x00    24    Magic signature (similar to FS4 with version differences)
0x18    ...   Firmware data
```

### 6. Parsing Algorithm

```python
def parse_mfa(data):
    # 1. Verify header
    if data[0:4] != b'MFAR':
        raise ValueError("Not an MFA file")
    
    version = struct.unpack('>I', data[4:8])[0]
    if version != 0x00000001:
        raise ValueError(f"Unsupported version: {version}")
    
    # 2. Parse sections
    offset = 16  # After header
    sections = {}
    
    while offset < len(data) - 4:  # Leave room for CRC32
        section_type = data[offset]
        flags = data[offset + 3]
        size = struct.unpack('<I', data[offset + 4:offset + 8])[0]
        
        section_data = data[offset + 8:offset + 8 + size]
        
        if flags & 1:  # XZ compressed
            section_data = lzma.decompress(section_data)
        
        sections[section_type] = section_data
        offset += 8 + size
    
    # 3. Verify CRC32
    crc32_stored = struct.unpack('<I', data[-4:])[0]
    crc32_calc = zlib.crc32(data[:-4])
    
    if crc32_stored != crc32_calc:
        raise ValueError("CRC32 mismatch")
    
    return sections
```

### 7. Special Cases and Edge Cases

#### 7.1 Old Format (v4.9-5.x)
These files have a different internal structure:
- First XZ block contains PSID metadata (not firmware)
- Firmware images are in subsequent XZ blocks
- No standard section headers

#### 7.2 Large Files (>4GB)
TOC entries use `data_offset_msb` field for addressing:
```python
actual_offset = (toc_entry.data_offset_msb << 32) | toc_entry.data_offset
```

#### 7.3 Multi-part Firmware
Some firmware images are split across multiple TOC entries with the same `group_id`.

### 8. Error Handling

Common issues:
1. **Truncated files**: Check section sizes don't exceed file bounds
2. **Corrupted XZ streams**: Use try/except around decompression
3. **Unknown firmware formats**: Log and save raw data
4. **Missing sections**: Some MFA files may not have all sections

### 9. Implementation Notes

1. **Endianness**: MFA uses big-endian for version, little-endian for sizes
2. **Alignment**: Sections are typically aligned to 4-byte boundaries
3. **Padding**: May contain padding between sections
4. **Checksums**: Always verify CRC32 at end of file

### 10. Testing Strategy

1. Test with all sample versions (4.9 through 25.x)
2. Verify extracted firmware with `mstflint -i <firmware> query full`
3. Compare extraction results with official tools
4. Handle edge cases (corrupted files, truncated archives)

