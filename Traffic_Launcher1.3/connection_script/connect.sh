wl down
wl up
wl PM 0
wl amsdu 1
wl ampdu 1
wl rx_amsdu_in_ampdu 0
wl ampdu_rx_ba_wsize 3
wl join PTS_11AX_5G_20
sleep 10
wl status
wl scansuppress 1
wl roam_off 1
ifconfig wlan0 192.168.50.22
ping 192.168.50.1 -c 5
sh -x tuning.sh
