#!/bin/bash

set -e

FW_EXTRACT=$(type mlx_fwextract.py | awk '{print $3}')
if [[ ${?} -ne 0 ]]; then
	echo "mlx_fwextract.py must be in PATH"
	exit 1
fi

FLINT=$(type mstflint | awk '{print $3}')
if [[ ${?} -ne 0 ]]; then
	echo "mstflint must be in the path"
	exit 1
fi

# Provide exact URL
# https://linux.mellanox.com/public/repo/doca/latest-2.9-LTS/debian12.5/arm64-sbsa/mlnx-fw-updater_24.10-2.1.8.0_arm64.deb
URL="${1}"

if [[ -z ${URL} ]]; then
	echo "No URL provided as first argument, example: https://linux.mellanox.com/public/repo/doca/latest-2.9-LTS/debian12.5/arm64-sbsa/mlnx-fw-updater_24.10-2.1.8.0_arm64.deb"
	exit 1
fi
FILE="$(rev <<< "${URL}" | cut -d/ -f 1 | rev)"
VER="$(cut -d_ -f 2 <<< "${FILE}")"
if [[ ${VER} == "${FILE}" ]]; then
  VER=$(rev <<< "${FILE}" | cut -d. -f 3- | rev | sed 's/mlnx-fw-updater-//')
fi

[[ ! -f "${FILE}" ]] && wget "${URL}"

OUTPUT="$(pwd)/fw_ofed_${VER}"
mkdir -p "${OUTPUT}"

mkdir -p unpack
pushd unpack
DATA=""
if [[ ${FILE} == *rpm ]]; then
	echo "Unpacking file ${FILE} as rpm..."
	rpm2archive ../"${FILE}"
	DATA="../${FILE}.tgz"
elif [[ ${FILE} == *deb ]]; then
	DATA=$(ar t ../${FILE}  | grep data)
	ar x ../"${FILE}" "${DATA}"
else
	echo "Unsupported file format: ${FILE}!"
	exit 1
fi

tar -xvf "${DATA}" --wildcards '*/mlxfwmanager_sriov_dis_*'
rm -rf "${DATA}"
for f in $(find ./opt -type f -name 'mlxfwmanager_sriov_dis*'); do
    d=$(rev <<< "${f}" | cut -d_ -f 1 | rev)
    ${FW_EXTRACT} -f "${f}" -o "${OUTPUT}/output_${d}/" ||:

    for f in "${OUTPUT}/output_${d}"/*.bin; do
      SIZE=$(du -b "${f}" | awk '{print $1}')
      if [[ ${SIZE} -gt 33554433 ]]; then
        echo "Filesize of ${f} (${SIZE}) is larger than 33554432 (known max size of firmware), probably splitting script doesn't support that firmware format and failed, leaving it as-is"
        continue
      fi
      INFO=$(${FLINT} -i "${f}" query full)
      PSID=$(grep '^PSID' <<< "${INFO}" | awk '{print $2}')
      MODEL=$(grep '^Part Number' <<< "${INFO}" | sed -E 's/Part Number:\s+//')
      VER=$(grep '^FW Version' <<< "${INFO}" | sed -E 's/FW Version:\s+/rel-/;s/\./_/')
      FILE_NAME="${MODEL}_${PSID}_${VER}"
      NEW_NAME_BASE="${OUTPUT}/output_${d}/${FILE_NAME}"
      NEW_NAME="${NEW_NAME_BASE}"
      xz "${f}" ||:

      cnt=0
      same=0
      while [[ -f "${NEW_NAME}.bin.xz" ]]; do
        CUR=$(sha256sum "${NEW_NAME}.bin.xz" | awk '{print $1}')
        NEW=$(sha256sum "${f}.xz" | awk '{print $1}')
        if [[ "${CUR}" == "${NEW}" ]]; then
          same=1
          echo "File ${f}.xz from ${FILE} and ${NEW_NAME}.bin.xz are the same, skipping..."
          break
        fi
        cnt=$((cnt+1))
        echo "Filename ${NEW_NAME}.bin.xz seems to already exist, but checksum is different, will try to add a prefix ${cnt}"
        NEW_NAME="${NEW_NAME_BASE}_${cnt}"
      done
      if [[ ${same} == 1 ]]; then
        continue
      fi

      echo "Changing name of firmware to ${FILE_NAME}"
      mv "${f}" "${NEW_NAME}.bin.xz"
      echo -e "FILENAME=${NEW_NAME}.bin\n${INFO}\n" > "${NEW_NAME}.desc"
      echo "${VER}" > "${NEW_NAME}.ver"
    done
    echo "Firmware extracted to ${OUTPUT}"
done
popd
rm -rf unpack
