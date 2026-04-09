./wl down
./wl up
./wl PM 0
./wl amsdu 1
./wl ampdu 1
./wl rx_amsdu_in_ampdu 0
./wl ampdu_rx_ba_wsize 3
./wl sup_wpa 1
./wl wsec 4
./wl mfp 2
./wl wpa_auth 0x40000
./wl sae_password 1234567890
./wl join ASUS_BE9700 imode bss amode wpa3
sleep 10
./wl status
./wl scansuppress 1
./wl roam_off 1
ifconfig wlan0 192.168.50.25
ping 192.168.50.1 -c 5
