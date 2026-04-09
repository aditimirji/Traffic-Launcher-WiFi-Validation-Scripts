sudo service NetworkManager stop
#systemctl status NetworkManager.service

rmmod inffmac.ko

rmmod infutil.ko

rmmod cfg80211.ko

rmmod compat.ko

rmmod sdhci-pci.ko

rmmod cqhci.ko

rmmod sdhci.ko

rmmod mmc_block

rmmod btsdio 

rmmod mmc_core.ko

sleep 5

modprobe rfkill

#insmod ./sdmmc/mmc_core.ko sd_uhsimode=$1
insmod ./mmc_core.ko sd_uhsimode=4
sleep 2
insmod ./sdhci.ko
sleep 2
insmod ./cqhci.ko
sleep 2
insmod ./sdhci-pci.ko
sleep 2
insmod ./compat.ko
sleep 2
insmod ./cfg80211.ko
sleep 2
insmod ./infutil.ko
sleep 2
#insmod ./brcmfmac.ko disable_hw_reset=1 sdio_idleclk_disable=1
#insmod ./brcmfmac.ko disable_hw_reset=1
#insmod brcmfmac.ko disable_hw_reset=1 fcmode=2 wmm_war=1

# FOR CSI
#insmod inffmac.ko debug=0xD5f506

#CPUSS Console
#insmod inffmac.ko debug=0x01FFFFFF

# SRAM binary load
#Working
#insmod inffmac.ko debug=0x1FFFFFF
insmod inffmac.ko debug=0x0 auto_kso_disable=1
sleep 10
ifconfig wlan0 up
sleep 2
#wl wd_disable 1
sleep 2
wl mpc 0
#insmod inffmac.ko debug=0x40000F
#insmod inffmac.ko debug=0x40000F inff_ram_app_logic_path="/root/diamond/inffmac/cyapp_trims_signed_0_pkg.bin"
#insmod inffmac.ko debug=0xFFFFFF inff_ram_app_logic_path="/root/diamond/inffmac/cyapp_rram_wifiss_fw_update_pkg.bin" inff_ram_app_payload_path="/root/diamond/inffmac/rtecdc_rram.trx"


# RRAM binary load
#Working
#insmod inffmac.ko debug=0xFFFFFF inff_ram_app_logic_path="/root/TC1_ES10_1/cyapp_rram_wifiss_fw_update_pkg.bin" inff_ram_app_payload_path="/root/TC1_ES10_1/rtecdc_rram.trxse"
#insmod inffmac.ko debug=0xFFFFFF inff_ram_app_logic_path="/root/TAG37/rtecdc_rram_DVT.trxse" inff_ram_app_payload_path="/root/TAG37/rtecdc_sram_DVT.trxse"

