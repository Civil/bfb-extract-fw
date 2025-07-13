#!/usr/bin/env python3

import os
import sys
import zipfile
import argparse
import re
import struct
import lzma
import zlib
from typing import Dict, List, Tuple, Optional, BinaryIO

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
parser.add_argument(
    "-v",
    "--verbose",
    action="store_true",
    help="Verbose output",
)

args = parser.parse_args()

# Firmware magic signatures
FW_MAGICS = {
    'fs3': bytes.fromhex('4D544657 8CDFD000 DEAD9270 4154BEEF 14185411 D6'),
    'fs4': bytes.fromhex('4D544657 ABCDEF00 FADE1234 5678DEAD 01000100 FFFFFFFF'),
    'fs5': bytes.fromhex('4D544657 ABCDEF00 FADE1234 5678DEAD 01010100 FFFFFFFF'),
    'cx8': bytes.fromhex('4D544657 ABCDEF00 FADE1234 5678DEAD 02000100 FFFFFFFF'),  # ConnectX-8
}

# MFA constants
MFA_MAGIC = b'MFAR'
MFA_VERSION = 0x00000001
MFA_HEADER_SIZE = 16

# Section types
SECTION_MAP = 1
SECTION_TOC = 2
SECTION_DATA = 3

# Section flags
FLAG_XZ_COMPRESSED = 1

class MFAParser:
    def __init__(self, data: bytes, verbose: bool = False):
        self.data = data
        self.verbose = verbose
        self.sections = {}
        
    def log(self, msg: str):
        if self.verbose:
            print(f"[MFA] {msg}")
    
    def parse(self) -> bool:
        """Parse MFA file structure"""
        # Check header
        if len(self.data) < MFA_HEADER_SIZE:
            self.log("File too small for MFA header")
            return False
            
        if self.data[0:4] != MFA_MAGIC:
            self.log("Invalid MFA magic")
            return False
            
        version = struct.unpack('>I', self.data[4:8])[0]
        if version != MFA_VERSION:
            self.log(f"Unsupported MFA version: 0x{version:08x}")
            return False
            
        self.log("Valid MFA header found")
        
        # Parse sections
        offset = MFA_HEADER_SIZE
        while offset < len(self.data) - 4:  # Leave room for CRC32
            if offset + 8 > len(self.data):
                break
                
            section_type = self.data[offset]
            flags = self.data[offset + 3]
            size = struct.unpack('>I', self.data[offset + 4:offset + 8])[0]
            
            self.log(f"Section at 0x{offset:x}: type={section_type}, flags=0x{flags:02x}, size={size}")
            
            if offset + 8 + size > len(self.data):
                self.log("Section extends beyond file end")
                break
                
            section_data = self.data[offset + 8:offset + 8 + size]
            
            # Decompress if needed
            if flags & FLAG_XZ_COMPRESSED:
                try:
                    section_data = lzma.decompress(section_data)
                    self.log(f"Decompressed section from {size} to {len(section_data)} bytes")
                except Exception as e:
                    self.log(f"Failed to decompress section: {e}")
                    return False
                    
            self.sections[section_type] = section_data
            offset += 8 + size
            
        # Verify CRC32
        if len(self.data) >= 4:
            crc_stored = struct.unpack('<I', self.data[-4:])[0]
            crc_calc = zlib.crc32(self.data[:-4]) & 0xffffffff
            if crc_stored != crc_calc:
                self.log(f"CRC32 mismatch: stored=0x{crc_stored:08x}, calculated=0x{crc_calc:08x}")
                # Don't fail on CRC mismatch, just warn
                
        return True
        
    def extract_firmwares(self, output_dir: str) -> List[str]:
        """Extract firmware images from parsed MFA"""
        extracted = []
        
        if SECTION_DATA not in self.sections:
            self.log("No DATA section found")
            return extracted
            
        data_section = self.sections[SECTION_DATA]
        
        # Try to find firmware images by magic signatures
        for fw_type, magic in FW_MAGICS.items():
            chunks = data_section.split(magic)
            if len(chunks) > 1:
                self.log(f"Found {len(chunks) - 1} {fw_type} firmware(s)")
                for i, chunk in enumerate(chunks[1:]):
                    if len(chunk) < 0x10000:  # Min firmware size
                        continue
                    fw_path = os.path.join(output_dir, f'firmware_{fw_type}_{i}.bin')
                    with open(fw_path, 'wb') as f:
                        f.write(magic + chunk)
                    extracted.append(fw_path)
                    self.log(f"Extracted {fw_type} firmware {i} ({len(chunk) + len(magic)} bytes)")
                    
        return extracted

def extract_xz_direct(data: bytes, output_dir: str, verbose: bool = False) -> List[str]:
    """Extract firmware from XZ streams directly (for old format)"""
    extracted = []
    xz_magic = b'\xFD\x37\x7A\x58\x5A'
    fw_order = ['cx8', 'fs5', 'fs4', 'fs3']  # Order to try magic signatures
    
    # Find all XZ streams
    xz_starts = [m.start() for m in re.finditer(xz_magic, data)]
    
    for idx, start in enumerate(xz_starts):
        end = xz_starts[idx + 1] if idx + 1 < len(xz_starts) else len(data)
        size = end - start
        
        if verbose:
            print(f"[XZ] Found XZ stream at offset 0x{start:x}, size {size} bytes")
            
        if size < 1000:  # Too small for firmware
            if verbose:
                print(f"[XZ] Stream {idx} too small, skipping")
            continue
            
        try:
            # Use decompressor to handle concatenated streams properly
            decompressor = lzma.LZMADecompressor()
            decompressed = decompressor.decompress(data[start:])
            
            # Check if this is metadata (first stream in old format)
            if idx == 0 and b'MT_00000' in decompressed[:1000]:
                # This is metadata, save it separately
                meta_path = os.path.join(output_dir, 'metadata.bin')
                with open(meta_path, 'wb') as f:
                    f.write(decompressed)
                if verbose:
                    print(f"[XZ] Saved metadata ({len(decompressed)} bytes)")
                continue
                
            # Try to find firmware in decompressed data
            found_fw = False
            fw_count = 0
            
            # Try magic signatures in order
            for fw_type in fw_order:
                magic = FW_MAGICS[fw_type]
                chunks = decompressed.split(magic)
                
                if verbose and len(chunks) > 1:
                    print(f"[XZ] Found {len(chunks) - 1} {fw_type} firmware(s) in stream {idx}")
                    
                for i, chunk in enumerate(chunks[1:]):
                    if len(chunk) < 0x10000:
                        continue
                    fw_path = os.path.join(output_dir, f'firmware_{idx}_{fw_count}.bin')
                    with open(fw_path, 'wb') as f:
                        f.write(magic + chunk)
                    extracted.append(fw_path)
                    found_fw = True
                    fw_count += 1
                    if verbose:
                        print(f"[XZ] Extracted {fw_type} firmware {i} from stream {idx} ({len(chunk) + len(magic)} bytes)")
                        
                if found_fw:
                    break  # Don't try other magic signatures if we found firmware
                            
            if not found_fw and len(decompressed) > 1000:
                # Save raw decompressed data
                raw_path = os.path.join(output_dir, f'xz_stream_{idx}_decompressed.bin')
                with open(raw_path, 'wb') as f:
                    f.write(decompressed)
                if verbose:
                    print(f"[XZ] No firmware found in stream {idx}, saved raw data ({len(decompressed)} bytes)")
                    
        except Exception as e:
            if verbose:
                print(f"[XZ] Failed to decompress stream {idx}: {e}")
                
    return extracted

def extract_firmware_from_zip(zip_data: bytes, output_dir: str, verbose: bool = False) -> bool:
    """Extract firmware from ZIP containing srcs.mfa"""
    try:
        # Save ZIP temporarily
        temp_zip = os.path.join(output_dir, 'temp.zip')
        with open(temp_zip, 'wb') as f:
            f.write(zip_data)
            
        # Check if valid ZIP
        with zipfile.ZipFile(temp_zip, 'r') as zf:
            if 'srcs.mfa' in zf.namelist():
                if verbose:
                    print("[ZIP] Found srcs.mfa in ZIP archive")
                    
                # Extract srcs.mfa
                mfa_data = zf.read('srcs.mfa')
                
                # Check if this is old format (has XZ magic near start)
                if b'\xFD\x37\x7A\x58\x5A' in mfa_data[:100]:
                    if verbose:
                        print("[ZIP] Detected old MFA format, using direct XZ extraction")
                    extracted = extract_xz_direct(mfa_data, output_dir, verbose)
                    os.remove(temp_zip)
                    return len(extracted) > 0
                
                # Try to parse as standard MFA
                parser = MFAParser(mfa_data, verbose)
                if parser.parse() and parser.sections:
                    # Extract using MFA structure
                    extracted = parser.extract_firmwares(output_dir)
                    if extracted:
                        os.remove(temp_zip)
                        return True
                        
                # Fallback: try direct XZ extraction
                if verbose:
                    print("[ZIP] Falling back to direct XZ extraction")
                extracted = extract_xz_direct(mfa_data, output_dir, verbose)
                
                os.remove(temp_zip)
                return len(extracted) > 0
                
    except Exception as e:
        if verbose:
            print(f"[ZIP] Error processing ZIP: {e}")
            
    # Cleanup
    if os.path.exists(temp_zip):
        os.remove(temp_zip)
        
    return False

def extract_firmware(binary_file: str, output_dir: str, verbose: bool = False) -> bool:
    """Main extraction function"""
    with open(binary_file, 'rb') as f:
        data = f.read()
        
    # Find all ZIP archives in the binary
    zip_magic = b'PK\x03\x04'
    zip_starts = [m.start() for m in re.finditer(zip_magic, data)]
    
    if verbose:
        print(f"Found {len(zip_starts)} potential ZIP archive(s)")
        
    for idx, start in enumerate(zip_starts):
        if verbose:
            print(f"\nProcessing ZIP at offset 0x{start:x}")
            
        # Try to extract from this position
        if extract_firmware_from_zip(data[start:], output_dir, verbose):
            if verbose:
                print(f"Successfully extracted firmware from ZIP at offset 0x{start:x}")
            return True
            
    print("No firmware extracted")
    return False

if __name__ == "__main__":
    os.makedirs(args.output, exist_ok=True)
    success = extract_firmware(args.file, args.output, args.verbose)
    sys.exit(0 if success else 1)

