wl down
sleep 2
wl up
sleep 2
wl scansuppress 0
sleep 2
wl roam_off 0
sleep 2
wl -i wlan0 ver
sleep 1
wl -i wlan0 memuse
sleep 1
wl -i wlan0 apsta 0
sleep 1
wl -i wlan0 ap 0
sleep 1
wl -i wlan0 mpc 0
sleep 1
wl -i wlan0 band auto
sleep 1
wl -i wlan0 oce enable 0
sleep 1
wl -i wlan0 up
sleep 1
#./wl -i wlan0 join_pref 0302000201020000     #2G
wl -i wlan0 join_pref 0302000101020000     #5G
sleep 1
wl -i wlan0 sup_wpa 1
sleep 1
wl -i wlan0 wsec 4
sleep 1
wl -i wlan0 mfp 2
sleep 1
wl -i wlan0 wpa_auth 0x40000
sleep 1
wl -i wlan0 sae_password 1234567890
sleep 1
ifconfig wlan0 192.168.50.25
sleep 1
wl -i wlan0 join MLO_2 imode bss amode wpa3
sleep 15
wl -i wlan0 status 
sleep 10
wl txpwr1 -o -d 8 
sleep 5
wl scansuppress 1
sleep 5
wl roam_off 1
sleep 5
ping 192.168.50.1 -c 5
wl ampdu 0
