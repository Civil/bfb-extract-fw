# Overview

NOTE: That tool was modified with help of Claude Code. Treat it as such.

A Python tool to extract firmware images from bfb and mlxfwmanager binaries.

## Overview

This tool extracts firmware images from:
- mlxfwmanager executable files containing embedded MFA files
- BFB bundles
- OFED packages

## Quick Start

### Extract from mlxfwmanager binary

```bash
./mlx_fwextract.py -f <mlxfwmanager_file> -o <output_directory> [-v]
```

Options:
- `-f, --file`: Path to the mlxfwmanager binary file
- `-o, --output`: Directory to save extracted firmware files
- `-v, --verbose`: Enable verbose output for debugging

### Example

```bash
# Extract firmware from a specific mlxfwmanager file
./mlx_fwextract.py -f samples/25.04-0.6.1.0/mlxfwmanager_sriov_dis_x86_64_4123 -o /tmp/extracted_fw

# Verify extracted firmware with mstflint
mstflint -i /tmp/extracted_fw/firmware_2_0.bin query full
```

## Extract from BFB bundles

1. Download https://github.com/Mellanox/bfscripts/blob/master/mlx-mkbfb and put it in your PATH (e.g. /usr/local/bin)
2. Put `mlx_fwextract.py` in your path
3. Edit extract.sh and point it to correct URL for bf-bundle you want to extract
4. Run extract.sh

Additional scripts:
- `extract_pkg.sh` - Extract from a deb file of fwmanager
- `extract_ofed` - Download OFED and extract firmware from there

## Supported Formats

The tool supports:
- Old MFA format (versions 4.x-5.x) with concatenated XZ streams
- Standard MFA format with proper section structure
- Multiple firmware image types (FS3, FS4, FS5, CX8/ConnectX-8)

## Output

The tool extracts:
- Individual firmware binary files (`firmware_*.bin`)
- Metadata file containing PSID mappings (for old format)
- Each firmware file can be verified using mstflint

## Documentation

See the `docs/` directory for detailed information about:
- [MFA file structure](docs/mfa_structure.md)
- [Technical specification](docs/mfa_technical_spec.md)

## Requirements

- Python 3.6+
- mstflint (for verification only)
- For BFB extraction: mlx-mkbfb tool
