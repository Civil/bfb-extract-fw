# Mellanox Firmware Archive (MFA) File Structure

## Overview

Mellanox Firmware Archives (MFA) are container formats used to package multiple firmware images for different Mellanox/NVIDIA network adapters. These archives are embedded within mlxfwmanager executable files, which are self-extracting archives containing ZIP files with MFA files inside.

## File Structure Hierarchy

### 1. mlxfwmanager Executable Structure
```
mlxfwmanager_sriov_dis_x86_64_XXXX (ELF executable)
├── Program code and data
└── Embedded ZIP archive(s) at various offsets
    └── srcs.mfa (the actual MFA file)
```

### 2. MFA File Format

The MFA file has two main versions:
- **MFA (version 1)** - Uses "MFAR" magic signature
- **MFA2** - Uses "MLNX.MFA2.XZ.00!" fingerprint

#### MFA Version 1 Structure

```
┌─────────────────────────┐
│    Header (16 bytes)    │
├─────────────────────────┤
│    MAP Section          │
├─────────────────────────┤
│    TOC Section          │
├─────────────────────────┤
│    DATA Section         │
├─────────────────────────┤
│    CRC32 (4 bytes)     │
└─────────────────────────┘
```

##### Header Format (16 bytes)
- **Offset 0x00-0x03**: Magic signature "MFAR" (0x4D464152)
- **Offset 0x04-0x07**: Version (0x00000001 = major: 0, minor: 1)
- **Offset 0x08-0x0F**: Reserved (zeros)

##### Section Structure
Each section starts with a section header:
```c
struct section_hdr {
    u_int8_t type;      // Section type (1=MAP, 2=TOC, 3=DATA)
    u_int8_t reserved[2];
    u_int8_t flags;     // Flags (1=XZ compressed)
    u_int32_t size;     // Section size
};
```

### 3. Section Details

#### MAP Section
Contains board type mappings and metadata. Each entry includes:
```c
struct map_entry_hdr {
    char board_type_id[32];  // PSID (e.g., "MT_0000000117")
    u_int8_t nimages;        // Number of images
    u_int8_t reserved;
    u_int16_t metadata_size; // Metadata size
};
```

Followed by:
```c
struct map_image_entry {
    u_int32_t toc_offset;    // Offset in TOC section
    u_int16_t image_type;    // Image type (1=FW)
    u_int8_t reserved;
    u_int8_t group_id;       // Group ID
    char select_tag[32];     // Selection tag
};
```

#### TOC Section (Table of Contents)
Lists all firmware images with offsets and metadata:
```c
struct toc_entry {
    u_int32_t data_offset;   // Offset in DATA section
    u_int32_t data_size;     // Size of data
    u_int16_t subimage_type; // Type (1=FW, 0x110=PXE, 0x111=UEFI)
    u_int8_t reserved0;
    u_int8_t num_ver_fields;
    u_int16_t version[4];    // Version numbers
    u_int16_t data_offset_msb; // MSB of offset for >4GB files
    u_int16_t metadata_size;
};
```

#### DATA Section
Contains the actual firmware binaries, which may be XZ compressed.

### 4. Firmware Image Magic Numbers

Firmware images within the DATA section have their own magic signatures:
- **FS3**: `4D 54 46 57 8C DF D0 00 DE AD 92 70 41 54 BE EF 14 18 54 11 D6` (older cards)
- **FS4**: `4D 54 46 57 AB CD EF 00 FA DE 12 34 56 78 DE AD 01 00 01 00 FF FF FF FF` (ConnectX-4/5/6)
- **FS5**: `4D 54 46 57 AB CD EF 00 FA DE 12 34 56 78 DE AD 01 01 01 00 FF FF FF FF` (ConnectX-6 Dx and newer)
- **CX8**: `4D 54 46 57 AB CD EF 00 FA DE 12 34 56 78 DE AD 02 00 01 00 FF FF FF FF` (ConnectX-8)

All start with "MTFW" (0x4D544657). The version bytes at offset 0x10 indicate the firmware generation.

### 5. Compression

MFA files use XZ compression (LZMA2) for sections. XZ streams are identified by:
- Magic: `FD 37 7A 58 5A` (ÝˆÞ7zXZ)

Multiple XZ streams may be concatenated within the srcs.mfa file.

### 6. Extraction Process

1. **Find ZIP archives** in the mlxfwmanager executable by searching for ZIP signatures (PK\x03\x04)
2. **Extract srcs.mfa** from the ZIP archive
3. **Parse MFA header** and verify magic/version
4. **Decompress sections** if XZ compressed
5. **Parse MAP section** to find board types (PSIDs)
6. **Parse TOC section** to get firmware offsets
7. **Extract firmware images** from DATA section
8. **Split concatenated firmwares** using firmware magic signatures

### 7. Special Cases

#### Old MFA Format (versions 4.9-5.x)
Some older MFA files have a different structure where:
1. The first XZ stream contains metadata (PSID mappings and descriptions)
2. Subsequent XZ streams contain the actual firmware images
3. The metadata section doesn't use standard firmware magic numbers

#### MFA2 Format
MFA2 uses a more complex structure with:
- 16-byte fingerprint: "MLNX.MFA2.XZ.00!"
- Component-based architecture
- SHA256 checksums
- Enhanced metadata support

### 8. Known Issues with Current Extractor

The current `mlx_fwextract.py` script has limitations:
1. Doesn't properly parse the MAP/TOC sections of MFA files
2. Relies on searching for firmware magic numbers instead of using the MFA structure
3. Saves raw MFA data when it can't find firmware magic numbers (old formats)
4. Doesn't handle the metadata section in old MFA files

### 9. Recommended Improvements

To properly extract all firmware types:
1. Implement proper MFA header parsing
2. Parse MAP section to get PSID mappings
3. Parse TOC section to get exact offsets and sizes
4. Use the MFA structure instead of searching for magic numbers
5. Handle both MFA v1 and MFA2 formats
6. Extract metadata along with firmware images

