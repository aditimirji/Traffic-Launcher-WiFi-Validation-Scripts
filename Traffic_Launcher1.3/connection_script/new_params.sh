./wl -i wlan0 apsta 0
./wl -i wlan0 ap 0
./wl -i wlan0 mpc 0

./wl -i wlan0 band auto

ifconfig wlan0 up
sleep 1
./wl -i wlan0 down
sleep 1
./wl -i wlan0 wd_disable 1
./wl amsdu 1
./wl ampdu 1
./wl -i wlan0 up
sleep 1
./wl -i wlan0 isup
./wl memuse
./wl rx_amsdu_in_ampdu 0
./wl ampdu_rx_ba_wsize 3   
./wl -i wlan0 join PTS_11AX_5G_20
./wl -i wlan0 scansuppress 1
./wl -i wlan0 roam_off 1
./wl status

