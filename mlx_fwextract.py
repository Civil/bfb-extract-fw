#!/usr/bin/env python3

import os
import zipfile
import argparse
import re

import lzma

parser = argparse.ArgumentParser(
    prog="fwextract",
    description="Extract data from FW Manager's binary files",
)

parser.add_argument(
    "-f",
    "--file",
    type=str,
    required=True,
    help="Path to the binary file to extract data from",
)
parser.add_argument(
    "-o",
    "--output",
    type=str,
    required=True,
    help="Directory to save the extracted files",
)

args = parser.parse_args()

def extract_xz(srcs_mfa: str, output_dir: str) -> bool:
    found = False
    fw_hdr = b''
    fw_magicks = {
            'fs3': b'\x4D\x54\x46\x57\x8C\xDF\xD0\x00\xDE\xAD\x92\x70\x41\x54\xBE\xEF\x14\x18\x54\x11\xD6',
            'fs4': b'\x4D\x54\x46\x57\xAB\xCD\xEF\x00\xFA\xDE\x12\x34\x56\x78\xDE\xAD\x01\x00\x01\x00\xFF\xFF\xFF\xFF',
            'fs5': b'\x4D\x54\x46\x57\xAB\xCD\xEF\x00\xFA\xDE\x12\x34\x56\x78\xDE\xAD\x01\x01\x01\x00\xFF\xFF\xFF\xFF',
             }
    order = ['fs4', 'fs5', 'fs3']
    with open(srcs_mfa, 'rb') as f:
        data = f.read()

    # Find the XZ header (0xFD 0x37 0x7A 0x58 0x5A)
    xz_starts = [m.start() for m in re.finditer(b'\xFD\x37\x7A\x58\x5A', data)]
    for i, xz_start in enumerate(xz_starts):
        # Write the XZ data to a temporary file
        print(f"XZ data found at offset {xz_start}. Searching for firmwares...")
        temp_xz_file = os.path.join(output_dir, f'temp_{i}.xz')
        end = -1
        if i < len(xz_starts) - 1:
            end = xz_starts[i + 1]
            print(f'size= {xz_starts[i + 1] - xz_start}')
            if xz_starts[i + 1] - xz_start < 4096:
                print(f"XZ data is too small, skipping...")
                continue
        with open(temp_xz_file, 'wb') as temp_file:
            temp_file.write(data[xz_start:end])

        # Decompress the XZ file
        try:
            chunks = []
            decompressed_data = lzma.LZMADecompressor().decompress(data[xz_start:])
            for fw_type in order:
                print(f"Trying {fw_type}...")
                fw_hdr = fw_magicks[fw_type]
                chunks = re.split(fw_hdr, decompressed_data)
                print(f'chunks found: {len(chunks)}')
                if len(chunks) > 1:
                    break
            found = True
            if len(chunks) == 1:
                print(f'Unsupported format, saving raw mfa file instead...')
                with open(os.path.join(output_dir, f'srcs_mfa_{i}.bin'), 'wb') as f:
                    f.write(data)
                with open(os.path.join(output_dir, f'srcs_mfa_{i}.bin.decompressed'), 'wb') as f:
                    f.write(decompressed_data)
 
                continue
            for j, chunk in enumerate(chunks):
                if not chunk or len(chunk) < 0x10000:
                    continue

                print(f'Found firmware. Saving to firmware_{i}_{j}.bin...')

                with open(os.path.join(output_dir, f'firmware_{i}_{j}.bin'), 'wb') as f:
                    f.write(fw_hdr)
                    f.write(chunk)
        except lzma.LZMAError as e:
            print(f"Failed to decompress XZ file at offset {xz_start}: {e}")
        finally:
            if os.path.exists(temp_xz_file):
                os.remove(temp_xz_file)

    if not found:
        print("No XZ data found in srcs.mfa.")
    return found


def extract_firmware(binary_file: str, output_dir: str) -> bool:
    # binary file is basically a custom SFX zip archive with multiple zip files in it
    # The one that contains firmwares have srcs.mfa file.
    # mfa file is a bunch of xz compressed concatenated firmware blobs
    mfa_path = os.path.join(output_dir, 'srcs.mfa')
    with open(binary_file, 'rb') as f:
        data = f.read()

    # Find all potential ZIP file headers (PK\x03\x04)
    zip_starts = [m.start() for m in re.finditer(b'\x50\x4b\x03\x04', data)]

    for i, start in enumerate(zip_starts):
        try:
            # Attempt to read the ZIP file from the start position
            with open(f'temp_{i}.zip', 'wb') as temp_zip:
                temp_zip.write(data[start:])

            # Check if the ZIP file contains srcs.mfa
            with zipfile.ZipFile(f'temp_{i}.zip', 'r') as zf:
                if 'srcs.mfa' in zf.namelist():
                    print(f"'srcs.mfa' found in ZIP file at offset {start}. Extracting...")
                    zf.extract('srcs.mfa', output_dir)
                    extract_xz(mfa_path, output_dir)
                    return True
        except zipfile.BadZipFile:
            pass
        finally:
            if os.path.exists(f'temp_{i}.zip'):
                os.remove(f'temp_{i}.zip')
            if os.path.exists(mfa_path):
                os.remove(mfa_path)

    print("No ZIP file containing 'srcs.mfa' was found.")
    return False


if __name__ == "__main__":
    os.makedirs(args.output, exist_ok=True)
    extract_firmware(args.file, args.output)
