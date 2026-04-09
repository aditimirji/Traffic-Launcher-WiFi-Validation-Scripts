ifconfig wlan0 192.168.50.25
wl down
sleep 1
wl up
wl scansuppress 0
wl roam_off 0
sleep 1
wl rx_amsdu_in_ampdu 0
wl ampdu_rx_ba_wsize 3
sleep 1
wl ver
sleep 1
wl memuse
sleep 1
wl apsta 0
sleep 1
wl ap 0
sleep 1
wl mpc 0
sleep 1
wl band auto
sleep 1
wl oce enable 0
sleep 1
wl up
sleep 1
#wl join_pref 0302000201020000     #2G
wl join_pref 0302000101020000     #5G
sleep 1
wl sup_wpa 1
sleep 1
wl wsec 4
sleep 1
wl mfp 2
sleep 1
wl wpa_auth 0x40000
sleep 1
wl sae_password 1234567890
sleep 1
ifconfig wlan0 192.168.50.25
sleep 1
wl join MLO_2 imode bss amode wpa3
sleep 15
wl txpwr1 -o -d 8
sleep 5
wl status
sleep 10
wl -i wlan0 db1timer 1
ping 192.168.50.1 -c 5
wl scansuppress 1
wl roam_off 1

