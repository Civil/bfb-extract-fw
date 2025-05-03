# bfb-extract-fw

Sample script to extract firmwares from bf-bundles.

It is not very well tested, quick & dirty, use at your own risk.

It would consume few gigabytes of RAM as most of uncompressed files are stored there.

## Usage

1. Download https://github.com/Mellanox/bfscripts/blob/master/mlx-mkbfb and put it in your PATH (e.x. /usr/local/bin)
2. Put mlx_fwextract.py in your path
3. Edit extract.sh and point it to correct URL for bf-bundle you want to extract
4. Run extract.sh

extract_pkg.sh is the same but for a deb file of fwmanager.
extract_ofed would download OFED and extract firmware from there
