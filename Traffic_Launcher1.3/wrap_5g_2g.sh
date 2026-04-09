scp -r connection_script 172.16.10.23:/root/connection_script
echo "=== 5G_SL connection load started at $(date) ===" | tee load_connection_5G_SL.txt
plink -ssh -pw hrun*10 root@172.16.10.25 sudo sh -x /root/connection_script/5g_sl_connect.sh 2>&1 | tee -a load_connection_5G_SL.txt
echo "=== 5G_SL connection load finished at $(date) ===" | tee -a load_connection_5G_SL.txt
python3 main.py /root/connection_script/5g_sl_connect.sh
# Auto-read OUTPUT_NAME from main.py
FOLDER=$(grep '"OUTPUT_NAME"' main.py 2>/dev/null | sed -n 's/.*"OUTPUT_NAME":[[:space:]]*"\([^"]*\)".*/\1/p')
if [ -z "$FOLDER" ]; then
    FOLDER="hello_1"
fi
# Use DD-MM-YYYY_HH-MM-SS format
if [ -d "$FOLDER" ]; then
    TIMESTAMP=$(date +"%d-%m-%Y_%H-%M-%S")
    NEW_NAME="${FOLDER}_${TIMESTAMP}_5G_SL"
    mv "$FOLDER" "$NEW_NAME"
    echo "Folder renamed to: $NEW_NAME"
    mv load_connection_5G_SL.txt "$NEW_NAME/" 2>/dev/null || true
else
    # Only look for candidates that don't already have _5G or _2G suffix
    candidate=$(ls -td "${FOLDER}"* 2>/dev/null | grep -v '_5G$\|_2G$' | head -n1 || true)
    if [ -n "$candidate" ] && [ -d "$candidate" ]; then
        TIMESTAMP=$(date +"%d-%m-%Y_%H-%M-%S")
        NEW_NAME="${FOLDER}_${TIMESTAMP}_5G"
        mv "$candidate" "$NEW_NAME"
        echo "Moved $candidate to: $NEW_NAME"
        mv load_connection_5G_SL.txt "$NEW_NAME/" 2>/dev/null || true
    else
        echo "Warning: folder '$FOLDER' not found for 5G phase, skipping rename"
    fi
fi
# scp sl_connect.sh 172.16.10.23:/root/TC1_ES10_1
# scp 2G_connect.sh 172.16.10.23:/root/TC1_ES10_1
echo "=== 2G_SL connection load started at $(date) ===" | tee load_connection_2G_SL.txt
plink -ssh -pw hrun*10 root@172.16.10.25 sudo sh -x /root/connection_script/2g_sl_connect.sh 2>&1 | tee -a load_connection_2G_SL.txt
echo "=== 2G_SL connection load finished at $(date) ===" | tee -a load_connection_2G_SL.txt
python3 main.py /root/connection_script/2g_sl_connect.sh
# Auto-read OUTPUT_NAME from main.py
FOLDER=$(grep '"OUTPUT_NAME"' main.py 2>/dev/null | sed -n 's/.*"OUTPUT_NAME":[[:space:]]*"\([^"]*\)".*/\1/p')
if [ -z "$FOLDER" ]; then
    FOLDER="hello_1"
fi
# Use DD-MM-YYYY_HH-MM-SS format
if [ -d "$FOLDER" ]; then
    TIMESTAMP=$(date +"%d-%m-%Y_%H-%M-%S")
    NEW_NAME="${FOLDER}_${TIMESTAMP}_2G"
    mv "$FOLDER" "$NEW_NAME"
    echo "Folder renamed to: $NEW_NAME"
    mv load_connection_2G_SL.txt "$NEW_NAME/" 2>/dev/null || true
else
    # Only look for candidates that don't already have _5G or _2G suffix
    candidate=$(ls -td "${FOLDER}"* 2>/dev/null | grep -v '_5G$\|_2G$' | head -n1 || true)
    if [ -n "$candidate" ] && [ -d "$candidate" ]; then
        TIMESTAMP=$(date +"%d-%m-%Y_%H-%M-%S")
        NEW_NAME="${FOLDER}_${TIMESTAMP}_2G_SL"
        mv "$candidate" "$NEW_NAME"
        echo "Moved $candidate to: $NEW_NAME"
        mv load_connection_2G_SL.txt "$NEW_NAME/" 2>/dev/null || true
    else
        echo "Warning: folder '$FOLDER' not found for 2G phase, skipping rename (5G results preserved)"
    fi
fi
