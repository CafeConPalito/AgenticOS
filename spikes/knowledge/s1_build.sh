#!/bin/bash
cd /d/agentic_os/spikes/knowledge
COMMON="--noconfirm --onefile --console --distpath out/dist --workpath out/work --specpath out/work probe_worker.py"
ALL="--collect-all markitdown --collect-all magika --collect-all rapidocr --collect-data pptx --collect-data docx --collect-data pdfminer --collect-all pypdfium2 --collect-all pypdfium2_raw --hidden-import openpyxl --hidden-import pandas"
echo "== all"; uv run pyinstaller --name probe_all $ALL $COMMON 2>&1 | tail -3
echo "== noocr"; uv run pyinstaller --name probe_noocr $ALL --exclude-module rapidocr --exclude-module cv2 $COMMON 2>&1 | tail -3
echo "== none"; uv run pyinstaller --name probe_none --exclude-module markitdown --exclude-module pypdfium2 --exclude-module onnxruntime --exclude-module tokenizers --exclude-module numpy --exclude-module rapidocr --exclude-module cv2 --exclude-module pandas --exclude-module magika $COMMON 2>&1 | tail -3
ls -la out/dist
echo BUILD-DONE
