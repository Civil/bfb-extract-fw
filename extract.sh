#!/usr/bin/env bash

set -e

BFB_OS="Ubuntu22.04"
BFB_DISTRO="ubuntu"
BFB_VER="2.9.2-31_25.02_${BFB_DISTRO}-22.04"
DOCA_FILE_NAME="bf-bundle-${BFB_VER}_prod.bfb"

#BFB_OS="Ubuntu20.04"
#DOCA_FILE_NAME="DOCA_v1.1_BlueField_OS_Ubuntu_20.04-5.4.0-1017.17.gf565efa-bluefield-5.4-2.4.1.3-3.7.1.11866-2.signed-aarch64.bfb"
#URL_OVERRIDE="https://developer.nvidia.com/networking/secure/doca-sdk/doca_1.11/doca_111_b19/doca_v1.1_bluefield_os_ubuntu_20.04-5.4.0-1017.17.gf565efa-bluefield-5.4-2.4.1.3-3.7.1.11866-2.signed-aarch64.bfb"

FW_EXTRACT=$(type mlx_fwextract.py | awk '{print $3}')
if [[ ${?} -ne 0 ]]; then
	echo "mlx_fwextract.py must be in PATH"
	exit 1
fi

type mlx-mkbfb > /dev/null 2>&1
if [[ ${?} -ne 0 ]]; then
  echo "Please download https://github.com/Mellanox/bfscripts/blob/master/mlx-mkbfb and put in your path"
	exit 1
fi

if [[ ! -f "${DOCA_FILE_NAME}" ]]; then
  if [[ -z ${URL_OVERRIDE} ]]; then
    wget "https://content.mellanox.com/BlueField/BFBs/${BFB_OS}/${DOCA_FILE_NAME}"
  else
    wget "${URL_OVERRIDE}"
  fi
fi
mkdir -p fwextract

pushd fwextract || exit 1
  OUTPUT=$(pwd)

  mlx-mkbfb -x ../${DOCA_FILE_NAME}
  mkdir -p initramfs
  pushd initramfs || exit 1
    zcat ../dump-initramfs-v0 | cpio -idmv --no-absolute-filenames "${BFB_DISTRO}"/image.tar.xz

    rm ../dump-*

    cd "${BFB_DISTRO}" || exit 1
    tar -xvf image.tar.xz --wildcards '*/mlxfwmanager_sriov_dis_aarch64_*'
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
  popd  || exit 1
  rm -rf initramfs
popd  || exit 1