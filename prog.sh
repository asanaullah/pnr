export XRAY_DIR="<insert_path>/PRJXRAY/prjxray"
source "${XRAY_DIR}/utils/environment.sh"
${XRAY_UTILS_DIR}/fasm2frames.py --part xc7a35tcsg324-1 --db-root ${XRAY_UTILS_DIR}/../database/artix7 top.fasm > top.frames
${XRAY_TOOLS_DIR}/xc7frames2bit --part_file ${XRAY_UTILS_DIR}/../database/artix7/xc7a35tcsg324-1/part.yaml --part_name xc7a35tcsg324-1  --frm_file top.frames --output_file top.bit
sudo openocd -f board-digilent-arty.cfg  -c "init; pld load 0 top.bit; exit"
