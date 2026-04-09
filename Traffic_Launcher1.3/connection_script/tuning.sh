sysctl -w net.ipv4.tcp_congestion_control=bic
echo 41943040 > /proc/sys/net/core/rmem_max
echo 41943040 > /proc/sys/net/core/wmem_max
echo 41943040 > /proc/sys/net/core/rmem_default
echo 41943040 > /proc/sys/net/core/wmem_default
echo '10240 41943040 41943040' > /proc/sys/net/ipv4/tcp_rmem
echo '10240 41943040 41943040' > /proc/sys/net/ipv4/tcp_wmem
echo '41943040 41943040 41943040' > /proc/sys/net/ipv4/tcp_mem
echo '41943040 41943040 41943040' > /proc/sys/net/ipv4/udp_mem
echo 1310720 > /proc/sys/net/ipv4/tcp_limit_output_bytes
echo bic > /proc/sys/net/ipv4/tcp_congestion_control
echo 1 > /proc/sys/net/ipv4/route/flush
echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
