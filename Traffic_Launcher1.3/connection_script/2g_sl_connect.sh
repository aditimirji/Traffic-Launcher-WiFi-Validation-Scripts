ifconfig wlan0 192.168.50.25
wl down
#wl wd_disable 1
wl up
wl scansuppress 0
wl rx_amsdu_in_ampdu 0
wl ampdu_rx_ba_wsize 3
#wl -i wlan0 down
wl -i wlan0  sup_wpa 1
wl -i wlan0  wsec 4
wl -i wlan0  mfp 2
wl -i wlan0 wpa_auth 0x40000
wl -i wlan0 sae_password 1234567890
#wl -i wlan0 up
wl -i wlan0 scan
sleep 10
wl -i wlan0  scanresults
wl -i wlan0  join Asus_2G_test imode bss amode wpa3
sleep 10
wl txpwr1 -o -d 8 
sleep 5
wl scansuppress 1
wl -i wlan0 db1timer 1
wl roam_off 1
ping 192.168.50.1 -c 5


